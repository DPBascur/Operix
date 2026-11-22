"""Decode the pinned local RTSP lab clips without starting any services.

Run with the Windows or Linux Python and FFmpeg executables on that host.
Default: FFmpeg CPU. --opencv also compares 1 vs 2 OpenCV decoder threads.
After GPU coordination, --nvdec adds CUDA decode with a required device-to-host
transfer and compares decoded BGR frame hashes and timestamps against CPU.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import re
from statistics import median
import subprocess
from time import perf_counter, process_time


def approved_clips(media):
    manifest = Path(__file__).with_name("approved-media.json")
    for clip in json.loads(manifest.read_text(encoding="utf-8"))["clips"]:
        path = (media / clip["filename"]).resolve(strict=True)
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != clip["sha256"]:
            raise ValueError(f"Approved clip hash mismatch: {path}")
        yield path, clip


def p95(samples):
    return sorted(samples)[math.ceil(len(samples) * .95) - 1]


def ffmpeg_cmd(executable, path, hardware):
    decoder = ["-hwaccel", "none"]
    convert = "format=nv12,format=bgr24"
    if hardware:
        decoder = ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
        convert = "hwdownload,format=nv12,format=bgr24"
    return [
        executable, "-hide_banner", "-nostdin", "-loglevel", "info", "-xerror",
        "-benchmark", "-filter_threads", "1", *decoder, "-threads", "1",
        "-c:v", "h264", "-i", str(path), "-map", "0:v:0", "-fps_mode", "passthrough",
        "-vf", convert, "-c:v", "rawvideo", "-threads:v", "1",
    ]


def ffmpeg_decode(command, expected, *, hashes=False):
    output = ["-f", "framehash", "-hash", "sha256", "-"] if hashes else [
        "-progress", "pipe:1", "-nostats", "-f", "null", "-",
    ]
    started = perf_counter()
    run = subprocess.run(command + output, capture_output=True, text=True, timeout=60)
    wall = perf_counter() - started
    if run.returncode:
        raise RuntimeError(run.stderr.strip())
    if hashes:
        rows = [tuple(part.strip() for part in line.split(","))
                for line in run.stdout.splitlines() if line and not line.startswith("#")]
        time_base = next((line for line in run.stdout.splitlines() if line.startswith("#tb ")), None)
        if time_base is None or len(rows) != expected or any(len(row) != 6 for row in rows):
            raise RuntimeError(f"Invalid framehash output: expected {expected} frame records, got {len(rows)}")
        return time_base, rows
    counts = re.findall(r"^frame=(\d+)\s*$", run.stdout, re.MULTILINE)
    if not counts or int(counts[-1]) != expected or "progress=end" not in run.stdout:
        raise RuntimeError(f"Expected {expected} decoded frames\n{run.stdout}\n{run.stderr}")
    times = re.search(r"utime=([\d.]+)s stime=([\d.]+)s rtime=([\d.]+)s", run.stderr)
    memory = re.search(r"maxrss=(\d+)KiB", run.stderr)
    if times is None:
        raise RuntimeError(f"FFmpeg omitted its benchmark timings\n{run.stderr}")
    user, system, elapsed = map(float, times.groups())
    return {"frames": expected, "process_wall_s": wall, "ffmpeg_wall_s": elapsed,
            "fps_including_startup": expected / wall, "cpu_s": user + system,
            "peak_rss_kib": (int(memory[1]) or None) if memory else None}


def opencv_decode(cv2, path, clip, threads, *, verify=False):
    cap = cv2.VideoCapture()
    started, cpu_start = perf_counter(), process_time()
    timings, pts = [], []
    content = hashlib.sha256()
    try:
        if not cap.open(str(path), cv2.CAP_FFMPEG, [
            cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_NONE,
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 2500, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 1500,
            cv2.CAP_PROP_N_THREADS, threads,
        ]):
            raise RuntimeError("OpenCV could not open the clip")
        open_ms = (perf_counter() - started) * 1000
        if cap.get(cv2.CAP_PROP_N_THREADS) != threads:
            raise RuntimeError(f"OpenCV did not apply {threads} decoder threads")
        fps = cap.get(cv2.CAP_PROP_FPS)
        while True:
            before = perf_counter()
            ok, frame = cap.read()
            if not ok:
                break
            if frame.shape != (clip["height"], clip["width"], 3):
                raise RuntimeError(f"Unexpected decoded shape {frame.shape}")
            tick = cap.get(cv2.CAP_PROP_PTS)
            timings.append((perf_counter() - before) * 1000)
            if verify:
                content.update(memoryview(frame))
                pts.append(tick)
    finally:
        cap.release()
    wall, cpu = perf_counter() - started, process_time() - cpu_start
    count = clip["frame_count"]
    if len(timings) != count:
        raise RuntimeError(f"Expected {count} OpenCV frames, got {len(timings)}")
    if verify:
        return {"bgr_sequence_sha256": content.hexdigest(), "fps": fps, "pts_ticks": pts}
    return {"frames": count, "process_wall_s": wall, "fps_including_startup": count / wall,
            "cpu_s": cpu, "open_ms": open_ms, "read_p50_ms": median(timings),
            "read_p95_ms": p95(timings), "first_read_ms": timings[0]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media", type=Path, required=True)
    parser.add_argument("--ffmpeg", default="ffmpeg", help="Native FFmpeg executable for this OS")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--opencv", action="store_true", help="Use the installed engine OpenCV")
    parser.add_argument("--nvdec", action="store_true", help="Start GPU decoding after coordination")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    if args.opencv:
        import cv2
        cv2.setNumThreads(1)
        cv2.ocl.setUseOpenCL(False)
    build = subprocess.run([args.ffmpeg, "-version"], capture_output=True, text=True,
                           check=True, timeout=10).stdout.splitlines()[0]
    report = {"platform": platform.platform(), "ffmpeg": build, "opencv": cv2.__version__ if args.opencv else None,
              "repeats": args.repeats, "clips": []}
    passed = True
    for path, clip in approved_clips(args.media):
        count = clip["frame_count"]
        row = {"clip": clip["filename"], "sha256": clip["sha256"], "width": clip["width"],
               "height": clip["height"], "source_fps": clip["average_fps"], "runs": {}}
        cpu = ffmpeg_cmd(args.ffmpeg, path, False)
        gpu = ffmpeg_cmd(args.ffmpeg, path, True)
        paths = {"ffmpeg_cpu": lambda: ffmpeg_decode(cpu, count)}
        if args.nvdec:
            paths["ffmpeg_nvdec"] = lambda: ffmpeg_decode(gpu, count)
        if args.opencv:
            paths["opencv_cpu_1"] = lambda: opencv_decode(cv2, path, clip, 1)
            paths["opencv_cpu_2"] = lambda: opencv_decode(cv2, path, clip, 2)

        # One unmeasured decode per path, then alternate ordering across repeats.
        for repeat in range(-1, args.repeats):
            order = list(paths) if repeat % 2 == 0 else list(reversed(paths))
            for name in order:
                if name in row.get("errors", {}):
                    continue
                try:
                    sample = paths[name]()
                except (RuntimeError, subprocess.TimeoutExpired) as exc:
                    row.setdefault("errors", {})[name] = str(exc)
                    passed = False
                else:
                    if repeat >= 0:
                        row["runs"].setdefault(name, []).append(sample)
        if args.nvdec and {"ffmpeg_cpu", "ffmpeg_nvdec"}.isdisjoint(row.get("errors", {})):
            try:
                cpu_tb, cpu_frames = ffmpeg_decode(cpu, count, hashes=True)
                gpu_tb, gpu_frames = ffmpeg_decode(gpu, count, hashes=True)
                bgr_mismatches = sum(a[-2:] != b[-2:] for a, b in zip(cpu_frames, gpu_frames))
                timestamp_mismatches = sum(a[:4] != b[:4] for a, b in zip(cpu_frames, gpu_frames))
                row["nvdec_parity"] = {"bgr_mismatches": bgr_mismatches,
                                       "timestamp_mismatches": timestamp_mismatches,
                                       "time_base_equal": cpu_tb == gpu_tb}
                passed &= cpu_tb == gpu_tb and bgr_mismatches == timestamp_mismatches == 0
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                row.setdefault("errors", {})["nvdec_parity"] = str(exc)
                passed = False
        if args.opencv and {"opencv_cpu_1", "opencv_cpu_2"}.isdisjoint(row.get("errors", {})):
            one = opencv_decode(cv2, path, clip, 1, verify=True)
            two = opencv_decode(cv2, path, clip, 2, verify=True)
            row["opencv_bgr_and_pts_equal"] = one == two
            row["opencv_bgr_sequence_sha256"] = one["bgr_sequence_sha256"]
            passed &= row["opencv_bgr_and_pts_equal"]
        report["clips"].append(row)
    print(json.dumps(report, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
