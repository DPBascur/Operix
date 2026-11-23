"""Controlled RTSP load on an isolated Docker network, using trusted lab media.

Default invocation prints a plan. Coordinate Docker/GPU usage before --execute.
--candidate-root snapshots trusted engine scripts and source, then mounts them
read-only for the optimized and shared stages in the frozen baseline image.
Alternatively use a locally built --candidate-image containing those files.
The optimized stage runs dedicated detectors. The shared stage starts the
candidate inference broker on a private Unix socket. Stages run sequentially
against the same continuously publishing feeds.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from threading import Event, Thread
import time
from uuid import uuid4


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
WIDTH, HEIGHT, FPS = 960, 540, 12
WORKER = "/app/engine/scripts/run_rtsp_lab.py"
BROKER = "/app/engine/scripts/run_rtsp_inference.py"
BROKER_SOCKET = Path("/var/lib/operix/sessions/inference-private/worker.sock")
DEFAULT_WORKER_IMAGE = "operix-backend:rtsp-baseline-7c2bdbd"
POLL = 1
MAX_STATUS_AGE = 4
INPUTS = (
    ("lab-cam-01.mp4", "e1625075af049a642505e815cbf3243499fcdc136422c2ecf5725cab5c4bc9eb"),
    ("lab-cam-02.mp4", "47deef759545ae785cf9e9c028f89b91bc665abf095c512e9a369ba51cf54696"),
)


def json_file(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def digest(path):
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def mount(source, target, *, writable=False):
    options = f"type=bind,source={source},target={target}"
    if "," in str(source):
        raise ValueError("Docker bind paths cannot contain commas")
    return ["--mount", options if writable else options + ",readonly"]


class CleanupError(RuntimeError):
    pass


def docker(*argv, timeout=25):
    result = subprocess.run(
        ["docker", *argv], capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"docker {argv[0]} failed: {result.stderr.strip() or result.stdout.strip()}")
    if argv[0] == "logs":
        return (result.stdout + result.stderr).strip()
    return result.stdout.strip()


@contextmanager
def containers(log_dir):
    names = []

    def run(name, image, entrypoint, *command, options=()):
        names.append(name)
        entry = ["--entrypoint", entrypoint] if entrypoint else []
        docker("run", "-d", "--pull=never", "--init", "--name", name,
               "--cap-drop=ALL", "--security-opt=no-new-privileges",
               *options, *entry, image, *command)

    try:
        yield run
    finally:
        failed = []
        for name in reversed(names):
            try:
                (log_dir / f"{name}.log").write_text(
                    docker("logs", "--tail", "200", name), encoding="utf-8",
                )
            except (OSError, RuntimeError, subprocess.TimeoutExpired):
                pass
            try:
                docker("rm", "-f", name)
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                if "No such container" not in str(error):
                    failed.append(f"{name}: {error}")
        if failed:
            raise CleanupError("Container cleanup failed: " + "; ".join(failed))


def running(*names):
    states = docker("inspect", "--format", "{{.Name}} {{.State.Status}}", *names)
    if any(line.split()[-1] != "running" for line in states.splitlines()):
        raise RuntimeError(f"An RTSP benchmark container stopped: {states}")


def wait_for(predicate, seconds, description):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(POLL)
    raise RuntimeError(f"Timed out waiting for {description}")


def media_image():
    compose = (ROOT / "compose.rtsp-lab.yaml").read_text(encoding="utf-8")
    return re.search(r"^\s*image: (bluenviron/mediamtx:[^\s]+@sha256:[a-f0-9]{64})$", compose, re.M)[1]


def prepare_media(args, image, prefix):
    folder = args.output / "normalized"
    folder.mkdir()
    cadence = {}
    fit = f"scale={args.width}:{args.height}:force_original_aspect_ratio=decrease:force_divisible_by=2"
    video_filter = f"fps={args.fps},{fit},pad={args.width}:{args.height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    with containers(args.output) as run:
        for index, (filename, _) in enumerate(INPUTS, 1):
            name = f"{prefix}-prep-{index}"
            run(name, image, "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "verbose",
                "-xerror", "-protocol_whitelist", "file", "-f", "mov", "-i", f"/source/{filename}",
                "-map", "0:v:0", "-vf", video_filter, "-c:v", "libx264", "-threads", "2",
                "-preset", "veryfast", "-pix_fmt", "yuv420p", "-bf", "0",
                "-g", str(args.fps), "-sc_threshold", "0", "-video_track_timescale", "12000",
                f"/normalized/{filename}", options=[
                    "--network=none", *mount(args.media_dir / filename, f"/source/{filename}"),
                    *mount(folder, "/normalized", writable=True),
                ])
            if docker("wait", name, timeout=120) != "0":
                raise RuntimeError(f"FFmpeg preparation failed for {filename}. See {name}.log")
            logs = docker("logs", "--tail", "200", name, timeout=10)
            counts = re.findall(r"(\d+) frames in, (\d+) frames out; (\d+) frames dropped, (\d+) frames duplicated",
                                logs)
            totals = [sum(map(int, column)) for column in zip(*counts, strict=True)]
            if not totals or totals[0] <= 0 or totals[1] <= 0 or totals[0] - totals[2] + totals[3] != totals[1]:
                raise RuntimeError(f"FFmpeg cadence counts missing for {filename}. See {name}.log")
            cadence[filename] = dict(zip(("input_frames", "output_frames", "dropped_frames", "duplicated_frames"),
                                         totals, strict=True))
    return folder, cadence


def server_config(aliases):
    lines = [
        "logLevel: warn", "api: true", "apiAddress: 127.0.0.1:9997",
        "rtsp: true", "rtspAddress: :8554", "rtspTransports: [tcp]",
        "rtmp: false", "hls: false", "webrtc: false", "srt: false", "moq: false",
        "authInternalUsers:", "  - user: any", "    ips: [127.0.0.1]",
        "    permissions:", "      - action: api",
        "  - user: any", "    permissions:",
    ]
    for alias in aliases:
        for action in ("publish", "read"):
            lines += [f"      - action: {action}", f"        path: {alias}"]
    return "\n".join(lines + ["pathDefaults:", "  overridePublisher: false", "paths:"]
                     + [f"  {alias}: {{}}" for alias in aliases]) + "\n"


def ready_paths(server, aliases=()):
    try:
        response = json.loads(docker(
            "exec", server, "wget", "-qO-", "-T", "2",
            "http://127.0.0.1:9997/v3/paths/list", timeout=5,
        ))
    except (RuntimeError, subprocess.TimeoutExpired):
        running(server)
        return False
    paths = {item["name"] for item in response["items"] or [] if item["ready"]}
    return set(aliases) <= paths


def status_snapshot(folder, feeds):
    rows = {}
    for feed in feeds:
        alias = feed["alias"]
        status_path = folder / alias / "status.json"
        for attempt in range(3):
            try:
                row = json.loads(status_path.read_text(encoding="utf-8"))
                break
            except (FileNotFoundError, PermissionError, json.JSONDecodeError):
                # A Docker bind mount can briefly hide a replacement from the host reader.
                if attempt < 2:
                    time.sleep(.02)
        else:
            continue
        if row["state"] in ("error", "stopped", "completed"):
            raise RuntimeError(f"{alias} ended early: {row.get('termination_reason')}")
        if row["analysis_run_id"] is None and row["state"] == "starting":
            continue
        if row["analysis_run_id"] != feed["analysis_run_id"]:
            raise RuntimeError(f"{alias} returned the wrong analysis_run_id")
        rows[alias] = row
    return rows


def worker_age(timestamp):
    return (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp)).total_seconds()


def healthy(row, profile):
    metrics = row["metrics"]
    return (row["state"] == "processing" and row["last_frame_at"]
            and worker_age(row["updated_at"]) < MAX_STATUS_AGE
            and worker_age(row["last_frame_at"]) < MAX_STATUS_AGE
            and metrics["frames_processed"] > 0
            and (metrics["width"], metrics["height"], metrics["source_fps"]) == profile
            and metrics["capture"].get("connections", 0) > 0)


def counter_deltas(start, end):
    deltas = {key: end.get(key, 0) - start.get(key, 0) for key in sorted(start.keys() | end.keys())}
    if any(delta < 0 for delta in deltas.values()):
        raise RuntimeError("A cumulative worker counter went backwards")
    return deltas


def event_counters(metrics):
    return {key: value for key, value in metrics.items()
            if isinstance(value, int) and (key == "candidates" or key.startswith(("events_", "clips_", "evidence_")))}


def summarize(samples, aliases, window_seconds, fps):
    results = {}
    issues = []
    capacity_issues = []
    for alias in aliases:
        rows = [sample["feeds"].get(alias) for sample in samples]
        if not healthy_at_sample(rows):
            issues.append(f"{alias}: missing, stale or non-processing status during window")
        if rows[0] is None or rows[-1] is None:
            continue
        start, end = rows[0]["metrics"], rows[-1]["metrics"]
        elapsed = end["elapsed_s"] - start["elapsed_s"]
        if elapsed <= 0 or abs(elapsed - window_seconds) > 2:
            issues.append(f"{alias}: worker status timestamps do not span the measurement window")
        frames = end["frames_processed"] - start["frames_processed"]
        if frames < 0:
            raise RuntimeError(f"{alias}: processed counter went backwards")
        capture = counter_deltas(start["capture"], end["capture"])
        epochs = counter_deltas(start["epochs"], end["epochs"])
        inference_drops = counter_deltas(start.get("inference_drops", {}), end.get("inference_drops", {}))
        drops = sum(value for key, value in capture.items() if key.endswith("_drop")) + sum(inference_drops.values())
        remainder = capture.get("decoded", 0) - frames - drops
        queue_change = end.get("queue_depth", 0) - start.get("queue_depth", 0)
        unexplained = remainder - queue_change
        local_tail = end.get("p95_arrival_to_result_ms")
        if drops:
            capacity_issues.append(f"{alias}: {drops} known frame drops")
        if local_tail is None or local_tail >= 500:
            capacity_issues.append(f"{alias}: local result p95 does not meet the 500 ms budget")
        if abs(unexplained) > 1:
            capacity_issues.append(f"{alias}: decoded frames do not reconcile with results, queue and known drops")
        decoded_fps = capture.get("decoded", 0) / elapsed if elapsed > 0 else None
        if decoded_fps is None or abs(decoded_fps - fps) > 0.5:
            issues.append(f"{alias}: decoded rate outside {fps} ± 0.5 FPS")
        if any(capture.get(key, 0) for key in ("connections", "open_failure", "read_failure")):
            issues.append(f"{alias}: RTSP connection changed or failed during window")
        if epochs.get("source_pts_gap", 0):
            issues.append(f"{alias}: worker detected source PTS gaps during window")
        results[alias] = {
            "observer_window_s": round(window_seconds, 3), "worker_counter_window_s": round(elapsed, 3),
            "processed": frames, "processed_fps": frames / elapsed if elapsed > 0 else None,
            "decoded_fps": decoded_fps, "capture_deltas": capture, "epoch_deltas": epochs,
            "inference_drops": inference_drops, "known_frame_drops": drops,
            "decoded_minus_processed_and_dropped": remainder, "capture_queue_change": queue_change,
            "unaccounted_frames_after_queue": unexplained,
            "tracking_deltas": counter_deltas(
                {key: start[key] for key in ("tracking_resets", "tracking_preserved_gaps") if key in start},
                {key: end[key] for key in ("tracking_resets", "tracking_preserved_gaps") if key in end},
            ),
            "event_deltas": counter_deltas(event_counters(start), event_counters(end)),
            "rolling_p95_at_window_end_ms": {
                key[4:-3]: value for key, value in end.items() if key.startswith("p95_") and key.endswith("_ms")
            },
            "rolling_p50_at_window_end_ms": {
                key[4:-3]: value for key, value in end.items() if key.startswith("p50_") and key.endswith("_ms")
            },
            "peak_sampled_capture_queue": max((row["metrics"].get("queue_depth", 0) for row in rows if row), default=0)
            if "queue_depth" in end else None,
            "batch_result_deltas": counter_deltas(
                start.get("inference_batch_sizes", {}), end.get("inference_batch_sizes", {}),
            ),
        }
    rates = [result["processed_fps"] for result in results.values()]
    return {
        "feeds": results, "valid": not issues, "issues": issues,
        "meets_capacity_gate": not issues and not capacity_issues, "capacity_issues": capacity_issues,
        "aggregate_processed_fps": math.fsum(rates) if len(rates) == len(aliases) and None not in rates else None,
    }


def healthy_at_sample(rows):
    return all(row is not None and row["healthy_at_poll"] for row in rows)


@contextmanager
def observe_resources(active, container, folder):
    stop = Event()

    def sample():
        with (folder / "resources.jsonl").open("w", encoding="utf-8") as output:
            while not stop.is_set():
                now = datetime.now(timezone.utc)
                try:
                    cpu = json.loads(docker("stats", "--no-stream", "--format", "{{json .}}", container, timeout=7))
                    gpu = docker("exec", container, "nvidia-smi",
                                 "--query-gpu=utilization.gpu,memory.used",
                                 "--format=csv,noheader,nounits", timeout=7)
                    row = {"at": now.isoformat(), "cpu": cpu["CPUPerc"], "ram": cpu["MemUsage"],
                           "gpu_host_total_pct_and_mib": gpu.splitlines()}
                except (OSError, RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired):
                    row = {"at": now.isoformat(), "unavailable": True}
                output.write(json.dumps(row) + "\n")
                output.flush()
                stop.wait(5)

    observer = Thread(target=sample, name="rtsp-benchmark-resources") if active else None
    if observer:
        observer.start()
    try:
        yield
    finally:
        if observer:
            stop.set()
            observer.join()


def stage(args, case, network, server, publishers, feeds, mode, image_ids):
    folder = case / mode
    folder.mkdir()
    config = json.loads(args.config.read_bytes())
    stage_feeds = []
    for feed in feeds:
        alias = feed["alias"]
        output = folder / alias
        output.mkdir()
        analysis_id = str(uuid4())
        feed_config = {**config, "view_id": alias}
        json_file(output / "config.json", feed_config)
        json_file(output / "context.json", {
            "analysis_run_id": analysis_id, "analysis_started_at": datetime.now(timezone.utc).isoformat(),
            "source": {
                "kind": "lab", "camera_id": alias, "timestamp_basis": "LAB_RECEPTION_UTC",
                "filename": feed["filename"], "video_sha256": feed["normalized_sha256"],
                "config_sha256": digest(output / "config.json"), "spatial_configuration": feed_config,
                "session_id": analysis_id, "session_run": 1,
            },
        })
        stage_feeds.append({
            **feed, "analysis_run_id": analysis_id, "output": f"/run-data/{alias}",
            "config": f"/run-data/{alias}/config.json",
        })
    env = {
        "OPERIX_EVENT_API_BASE_URL": "http://127.0.0.1:18081/api/v1",
        "OPERIX_EVENT_PUBLISH_TOKEN": "benchmark-local",
        "OPERIX_MEDIA_ROOT": "/var/lib/operix/media",
        "OPENCV_FFMPEG_CAPTURE_OPTIONS": "rtsp_transport;tcp|probesize;65536|analyzeduration;250000",
        "PYTHONPATH": "/app/engine/scripts:/app/engine/src",
    }
    manifest = {
        "schema_version": 1, "mode": mode, "feeds": stage_feeds, "env": env,
        "width": args.width, "height": args.height, "fps": args.fps,
        "person_weights": "/weights/person.pt", "forklift_weights": "/weights/forklift.pt",
        "seconds": args.startup + args.warmup + args.seconds + 15,
        "startup_s": args.startup, "batch_cap": args.batch_cap, "batch_wait_ms": args.batch_wait_ms,
    }
    json_file(folder / "feeds.json", manifest)
    name = f"{network}-{mode}"
    print(f"{case.name} {mode}: waiting for {len(feeds)} active readers", flush=True)
    options = [
        "--network", network, "--gpus", args.gpus,
        *mount(Path(__file__).resolve(), "/benchmark-live.py"),
        *mount(folder, "/run-data", writable=True),
        *mount(args.person_weights, manifest["person_weights"]),
        *mount(args.forklift_weights, manifest["forklift_weights"]),
    ]
    if mode != "regular" and args.candidate_root:
        for directory in ("scripts", "src"):
            options += mount(args.output / "candidate-engine" / directory, f"/app/engine/{directory}")
    aliases = [feed["alias"] for feed in stage_feeds]
    samples = []

    def poll():
        running(name, server, *publishers)
        rows = status_snapshot(folder, stage_feeds)
        for alias, row in rows.items():
            row["healthy_at_poll"] = bool(healthy(row, (args.width, args.height, args.fps)))
            if row["healthy_at_poll"] and mode == "shared" and row["metrics"].get("inference_mode") != "shared":
                raise RuntimeError(f"{alias} is processing without the shared broker")
        return rows

    def all_ready():
        rows = poll()
        return len(rows) == len(aliases) and healthy_at_sample(rows.values())

    with containers(folder) as run:
        image = image_ids["worker" if mode == "regular" else "candidate"]
        run(name, image, "python", "/benchmark-live.py", "_workers", options=options)
        try:
            warm_since = None

            def warmed():
                nonlocal warm_since
                if not all_ready():
                    warm_since = None
                    return False
                now = time.monotonic()
                if warm_since is None:
                    warm_since = now
                return now - warm_since >= args.warmup

            wait_for(warmed, args.startup + args.warmup, "all workers to warm up continuously")
            print(f"{case.name} {mode}: measuring for {args.seconds}s", flush=True)
            with (observe_resources(args.resources, name, folder),
                  (folder / "samples.jsonl").open("w", encoding="utf-8") as trace):
                started = time.monotonic()
                while True:
                    elapsed = time.monotonic() - started
                    sample = {"wall_s": elapsed, "feeds": poll()}
                    samples.append(sample)
                    trace.write(json.dumps(sample, allow_nan=False) + "\n")
                    trace.flush()
                    if elapsed >= args.seconds:
                        break
                    time.sleep(min(POLL, max(0, args.seconds - (time.monotonic() - started))))
            result = summarize(samples, aliases, samples[-1]["wall_s"] - samples[0]["wall_s"], args.fps)
            json_file(folder / "summary.json", result)
        finally:
            for feed in stage_feeds:
                (folder / feed["alias"] / "stop").touch()
        if docker("wait", name, timeout=20) != "0":
            raise RuntimeError(f"{mode} worker group failed. See {name}.log")
    return result


def run_case(args, case, count, modes, normalized, image_ids):
    network = f"{args.prefix}-{case.name}"
    server = f"{network}-rtsp"
    aliases = [f"bench-feed-{index:02d}" for index in range(1, count + 1)]
    config = case / "mediamtx.yml"
    config.write_text(server_config(aliases), encoding="utf-8")
    docker("network", "create", "--internal", network)
    try:
        with containers(case) as run:
            run(server, image_ids["media"], None, "/benchmark.yml", options=[
                "--network", network, "--network-alias", "benchmark-rtsp",
                "--user", "65534:65534", "--read-only", *mount(config, "/benchmark.yml"),
            ])
            wait_for(lambda: ready_paths(server), 20, "the private MediaMTX control API")
            ip = str(ipaddress.IPv4Address(docker(
                "inspect", "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", server,
            )))
            publishers = []
            feeds = []
            for index, alias in enumerate(aliases):
                media = normalized[index % len(normalized)]
                name = f"{network}-{alias}"
                run(name, image_ids["media"], "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "warning",
                    "-xerror", "-stream_loop", "-1", "-re", "-protocol_whitelist", "file",
                    "-i", f"/clips/{media['filename']}", "-map", "0:v:0", "-c:v", "copy",
                    "-f", "rtsp", "-rtsp_transport", "tcp", f"rtsp://benchmark-rtsp:8554/{alias}",
                    options=[
                        "--network", network, "--user", "65534:65534", "--read-only",
                        *mount(args.output / "normalized", "/clips"),
                    ])
                publishers.append(name)
                feeds.append({**media, "alias": alias, "url": f"rtsp://{ip}:8554/{alias}", "allowed_ip": ip})

            def sources_ready():
                running(*publishers)
                return ready_paths(server, aliases)

            wait_for(sources_ready, 30, "all independent RTSP publishers")
            results = {}
            for mode in modes:
                try:
                    if not sources_ready():
                        raise RuntimeError("All RTSP paths must be ready before each stage")
                    results[mode] = stage(args, case, network, server, publishers, feeds, mode, image_ids)
                except CleanupError:
                    raise
                except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
                    print(f"{case.name} {mode}: {error}", file=sys.stderr, flush=True)
                    results[mode] = {"valid": False, "issues": [str(error)], "feeds": {},
                                     "aggregate_processed_fps": None}
                    if (case / mode).is_dir():
                        json_file(case / mode / "summary.json", results[mode])
            differences = {}
            for left, right in (("optimized", "regular"), ("shared", "regular"), ("shared", "optimized")):
                if all(mode in results and results[mode]["valid"] for mode in (left, right)):
                    differences[f"{left}_minus_{right}"] = (
                        results[left]["aggregate_processed_fps"] - results[right]["aggregate_processed_fps"]
                    )
            return {"feeds": count, "stage_order": modes, "stages": results, "aggregate_fps_differences": differences}
    finally:
        docker("network", "rm", network)


class LocalEvents(BaseHTTPRequestHandler):
    """Acknowledge worker event and evidence requests without storing their contents."""

    def do_POST(self):
        length = self.headers.get("Content-Length", "")
        if (self.headers.get("Authorization") != "Bearer benchmark-local"
                or not length.isdecimal() or len(length) > 8 or int(length) > 3 * 1024 * 1024):
            self.send_error(400)
            return
        if self.path == "/api/v1/events/":
            body = json.dumps({"id": str(uuid4())}).encode("ascii")
        elif re.fullmatch(r"/api/v1/events/[0-9a-f-]{36}/evidence/", self.path):
            body = b"{}"
        elif re.fullmatch(r"/api/v1/events/[0-9a-f-]{36}/evidence-status/", self.path):
            body = b""
        else:
            self.send_error(404)
            return
        if len(self.rfile.read(int(length))) != int(length):
            return
        self.send_response(201 if body else 204)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


def worker_group():
    manifest = json.loads(Path("/run-data/feeds.json").read_text(encoding="utf-8"))
    processes = []
    broker = None
    env = {**os.environ, **manifest["env"]}
    env.pop("OPERIX_RTSP_INFERENCE_SOCKET", None)
    with ThreadingHTTPServer(("127.0.0.1", 18081), LocalEvents) as receiver:
        Thread(target=receiver.serve_forever, daemon=True).start()
        try:
            if manifest["mode"] == "shared":
                command = [sys.executable, BROKER, "--socket", str(BROKER_SOCKET), "--max-clients", "8"]
                for key in ("width", "height", "person_weights", "forklift_weights", "batch_cap", "batch_wait_ms"):
                    command += ["--" + key.replace("_", "-"), str(manifest[key])]
                broker = subprocess.Popen(command, env={**env, "OPERIX_RTSP_INFERENCE": "1"})

                def broker_ready():
                    if broker.poll() is not None:
                        raise RuntimeError("The shared inference broker exited during startup")
                    return BROKER_SOCKET.is_socket()

                wait_for(broker_ready, manifest["startup_s"], "the shared inference broker socket")
                env["OPERIX_RTSP_INFERENCE_SOCKET"] = str(BROKER_SOCKET)
            for feed in manifest["feeds"]:
                worker_env = {
                    **env, "OPERIX_RTSP_URL": feed["url"], "OPERIX_RTSP_ALLOWED_IP": feed["allowed_ip"],
                    "OPERIX_RTSP_LAB_CAMERA_ID": feed["alias"],
                }
                command = [sys.executable, WORKER, "--output", feed["output"], "--config", feed["config"]]
                for key in ("width", "height", "fps", "person_weights", "forklift_weights", "seconds"):
                    command += ["--" + key.replace("_", "-"), str(manifest[key])]
                processes.append(subprocess.Popen(command, env=worker_env))
            while True:
                codes = [process.poll() for process in processes]
                if (broker is not None and broker.poll() is not None
                        or any(code not in (None, 0) for code in codes)):
                    return 1
                stopping = all((Path(feed["output"]) / "stop").is_file() for feed in manifest["feeds"])
                if any(code == 0 for code in codes) and not stopping:
                    return 1
                if all(code == 0 for code in codes):
                    return 0
                time.sleep(.2)
        finally:
            if broker is not None:
                processes.append(broker)
            for process in processes:
                if process.poll() is None:
                    process.terminate()
            deadline = time.monotonic() + 5
            for process in processes:
                try:
                    process.wait(timeout=max(0, deadline - time.monotonic()))
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            receiver.shutdown()


def execute(args, cases, image):
    for path in (args.config, args.person_weights, args.forklift_weights):
        if not path.is_file():
            raise ValueError(f"Missing file: {path}")
    for filename, expected in INPUTS:
        path = args.media_dir / filename
        if path.is_symlink() or digest(path) != expected:
            raise ValueError(f"Expected the exact approved lab clip: {path}")
    json.loads(args.config.read_bytes())
    args.output.mkdir(parents=True, exist_ok=False)
    args.prefix = f"operix-bench-{uuid4().hex[:10]}"
    candidate_source = None
    if args.candidate_root:
        source = args.candidate_root / "engine"
        snapshot = args.output / "candidate-engine"
        for directory in ("scripts", "src"):
            shutil.copytree(source / directory, snapshot / directory,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"))
        candidate_source = {path.relative_to(snapshot).as_posix(): digest(path)
                            for path in sorted(snapshot.rglob("*")) if path.is_file()}
    image_ids = {
        kind: docker("image", "inspect", "--format", "{{.Id}}", reference)
        for kind, reference in (("media", image), ("worker", args.worker_image))
    }
    if args.candidate_image:
        image_ids["candidate"] = docker("image", "inspect", "--format", "{{.Id}}", args.candidate_image)
    elif args.candidate_root:
        image_ids["candidate"] = image_ids["worker"]
    print(f"Benchmark resources use prefix {args.prefix}", flush=True)
    folder, cadence = prepare_media(args, image_ids["media"], args.prefix)
    normalized = [
        {"filename": filename, "input_sha256": checksum, "normalized_sha256": digest(folder / filename),
         "replay_cadence": cadence[filename]}
        for filename, checksum in INPUTS
    ]
    report = {
        "schema_version": 1, "prefix": args.prefix, "images": image_ids,
        "width": args.width, "height": args.height, "fps": args.fps, "warmup_s": args.warmup,
        "requested_window_s": args.seconds, "gpu_selection": args.gpus,
        "config_sha256": digest(args.config), "weights_sha256": {
            "person": digest(args.person_weights), "forklift": digest(args.forklift_weights),
        },
        "candidate_files_sha256": candidate_source,
        "broker": {"batch_cap": args.batch_cap, "batch_wait_ms": args.batch_wait_ms},
        "media": normalized, "cases": {},
    }
    summary = args.output / "summary.json"
    json_file(summary, report)
    for case_name, count, modes in cases:
        case = args.output / case_name
        case.mkdir()
        report["cases"][case_name] = run_case(args, case, count, modes, normalized, image_ids)
        json_file(summary, report)
    return 0 if all(stage["valid"] for case in report["cases"].values()
                    for stage in case["stages"].values()) else 1


def main():
    if sys.argv[1:] == ["_workers"] and Path("/run-data/feeds.json").is_file():
        return worker_group()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--feeds", nargs="+", type=int, choices=(1, 2, 3, 4), default=[2, 3, 4])
    parser.add_argument("--media-dir", type=Path, required=True, help="directory with the two approved MP4s")
    parser.add_argument("--output", type=Path, required=True, help="new results directory outside the repository")
    parser.add_argument("--width", type=int, default=WIDTH)
    parser.add_argument("--height", type=int, default=HEIGHT)
    parser.add_argument("--fps", type=int, choices=(12, 15, 20, 24, 30), default=FPS)
    parser.add_argument("--worker-image", default=DEFAULT_WORKER_IMAGE, help="existing local baseline image")
    parser.add_argument("--person-weights", type=Path)
    parser.add_argument("--forklift-weights", type=Path)
    parser.add_argument("--config", type=Path, default=ROOT / "engine/config/examples/op30-zone-rule.json")
    candidate = parser.add_mutually_exclusive_group()
    candidate.add_argument("--candidate-root", type=Path, help="checkout with optimized engine scripts and source")
    candidate.add_argument("--candidate-image", help="existing local image with the optimized engine and broker")
    parser.add_argument("--stages", nargs="+", choices=("regular", "optimized", "shared"),
                        help="defaults to regular, or all three with candidate code")
    parser.add_argument("--batch-cap", type=int, choices=(1, 2, 4), default=1, help="shared broker batch limit")
    parser.add_argument("--batch-wait-ms", type=float, default=3, help="shared broker maximum batch wait")
    parser.add_argument("--warmup", type=int, default=15, help="seconds after every feed is processing")
    parser.add_argument("--seconds", type=int, default=60, help="steady-state seconds per stage")
    parser.add_argument("--startup", type=int, default=90, help="seconds allowed for worker readiness")
    parser.add_argument("--repeats", type=int, default=1, help="repeat each feed count and alternate stage order")
    parser.add_argument("--resources", action="store_true", help="sample Docker CPU/RAM and host GPU/VRAM")
    parser.add_argument("--gpus", default="device=0", help="Docker GPU selector for the coordinated run")
    parser.add_argument("--execute", action="store_true", help="explicitly start isolated Docker/GPU workloads")
    args = parser.parse_args()
    if not (16 <= args.width <= 1920 and 16 <= args.height <= 1080
            and args.width % 2 == args.height % 2 == 0):
        parser.error("require even dimensions between 16×16 and 1920×1080")
    if len(set(args.feeds)) != len(args.feeds) or args.stages and len(set(args.stages)) != len(args.stages):
        parser.error("--feeds and --stages must contain distinct values. Use --repeats for repetitions.")
    if not 0 <= args.batch_wait_ms <= 20:
        parser.error("--batch-wait-ms must be between 0 and 20")
    if (args.warmup < 5 or args.seconds < 10 or args.startup < 5 or args.repeats < 1
            or args.warmup + args.seconds + args.startup + 15 > 1800):
        parser.error("Require warmup >= 5s, seconds >= 10s, startup >= 5s, repeats >= 1, worker budget <= 1800s")
    for key in ("media_dir", "output", "config", "candidate_root", "person_weights", "forklift_weights"):
        path = getattr(args, key)
        if path is not None:
            setattr(args, key, path.expanduser().resolve())
    has_candidate = bool(args.candidate_root or args.candidate_image)
    modes = args.stages or (["regular", "optimized", "shared"] if has_candidate else ["regular"])
    if not has_candidate and any(mode != "regular" for mode in modes):
        parser.error("Candidate stages require --candidate-root or --candidate-image")
    cases = [
        (f"{count}feeds-r{repeat:02d}", count, modes[offset:] + modes[:offset])
        for repeat in range(1, args.repeats + 1) for count in args.feeds
        for offset in [(repeat - 1) % len(modes)]
    ]
    try:
        image = media_image()
        if not args.execute:
            print(json.dumps({
                "execute": False, "profile": {"width": args.width, "height": args.height, "fps": args.fps},
                "warmup_s": args.warmup, "window_s": args.seconds,
                "media_image": image, "worker_image": args.worker_image,
                "candidate_root": str(args.candidate_root) if args.candidate_root else None,
                "candidate_image": args.candidate_image,
                "broker": {"batch_cap": args.batch_cap, "batch_wait_ms": args.batch_wait_ms},
                "media_dir": str(args.media_dir), "output": str(args.output),
                "approved_media": dict(INPUTS),
                "alias_sources": {f"bench-feed-{n:02d}": INPUTS[(n - 1) % len(INPUTS)][0]
                                  for n in range(1, max(args.feeds) + 1)},
                "cases": [{"case": name, "feeds": count, "stage_order": order} for name, count, order in cases],
            }, indent=2))
            return 0
        if args.person_weights is None or args.forklift_weights is None:
            parser.error("--execute requires --person-weights and --forklift-weights")
        if args.output.is_relative_to(ROOT):
            parser.error("--output must be outside the Operix repository")
        return execute(args, cases, image)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"Benchmark failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
