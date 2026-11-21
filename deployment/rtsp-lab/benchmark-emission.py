"""Time marked laboratory frames from RTSP publisher egress to the event list."""

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import secrets
import socket
import struct
import subprocess
import sys
import time
from urllib.parse import urlsplit
from uuid import UUID

import requests
from PIL import Image


WIDTH, HEIGHT, FPS = 960, 540, 12
MARK_X, MARK_Y, MARK_W, MARK_H = 816, 460, 128, 64
RTP_HZ = 90_000
MAX_PAYLOAD = 1200


def clock_anchor():
    before = time.monotonic_ns()
    utc = time.time_ns()
    return {"mono_before_ns": before, "utc_ns": utc, "mono_after_ns": time.monotonic_ns()}


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def marker_filter(token):
    # Two complementary copies of 0xA6 | 40-bit token | 16-bit frame ordinal.
    position = "(16*floor(Y/8)+floor(X/8))"
    bit = f"mod({position},64)"
    high = f"mod(floor({(0xA6 << 40) | token}/pow(2,47-{bit})),2)"
    low = f"mod(floor(N/pow(2,63-{bit})),2)"
    value = f"mod(if(lt({bit},48),{high},{low})+floor({position}/64),2)"
    return (
        f"[0:v]fps={FPS},scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease:"
        f"force_divisible_by=2,pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1[clip];"
        f"nullsrc=s={MARK_W}x{MARK_H}:r={FPS},format=yuv420p,geq=lum='32+192*{value}':cb=128:cr=128[mark];"
        f"[clip][mark]overlay={MARK_X}:{MARK_Y}:shortest=1[out]"
    )


def frame_marker(image, token):
    gray = image.convert("L")
    if abs(gray.width * HEIGHT - gray.height * WIDTH) > WIDTH:
        raise ValueError("Unexpected evidence aspect ratio")
    if gray.size != (WIDTH, HEIGHT):
        gray = gray.resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR)
    patch = gray.crop((MARK_X, MARK_Y, MARK_X + MARK_W, MARK_Y + MARK_H))
    return marker_ordinal(patch.resize((16, 8), Image.Resampling.BOX).tobytes(), token)


def marker_ordinal(cells, token):
    if len(cells) != 128 or any(85 < value < 170 for value in cells):
        raise ValueError("Indeterminate marker cells")
    word = 0
    for value, inverse in zip(cells[:64], cells[64:]):
        bit = value >= 170
        if bit == (inverse >= 170):
            raise ValueError("Marker copies disagree")
        word = (word << 1) | bit
    if word >> 16 != (0xA6 << 40) | token:
        raise ValueError("Marker belongs to another replay or is obscured")
    return word & 0xFFFF


def access_units(path):
    units = []
    for nal in re.split(rb"\x00{2,}\x01", path.read_bytes()):
        if not nal:
            continue
        if nal[0] & 31 == 9:  # x264 emits an access unit delimiter before each picture.
            units.append([])
        if not units:
            raise ValueError("H.264 stream is missing its initial access unit delimiter")
        units[-1].append(nal)
    if not 0 < len(units) <= 65536 or any(
        sum((nal[0] & 31) in (1, 5) for nal in unit) != 1 for unit in units
    ):
        raise ValueError("Expected one H.264 picture slice per access unit")
    return units


def prepare(args, clip, source):
    original = args.media_dir / clip["filename"]
    if sha256(original) != clip["sha256"]:
        raise ValueError("Approved source checksum mismatch")
    token = secrets.randbits(40)
    path = args.output / "marked.h264"
    ffmpeg = [args.ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error"]
    subprocess.run([
        *ffmpeg, "-protocol_whitelist", "file", "-stream_loop", str(args.passes - 1),
        "-i", str(original), "-filter_complex_threads", "1",
        "-filter_complex", marker_filter(token), "-map", "[out]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-threads", "2", "-preset", "veryfast",
        "-tune", "zerolatency", "-g", str(FPS), "-bf", "0",
        "-x264-params", "aud=1:repeat-headers=1:sliced-threads=0:slices=1",
        "-f", "h264", "-n", str(path),
    ], check=True, timeout=180)
    units = access_units(path)
    # Independently decode the marked clip and confirm marker N is in access unit N.
    cells = subprocess.run([
        *ffmpeg, "-f", "h264", "-i", str(path), "-vf",
        f"crop={MARK_W}:{MARK_H}:{MARK_X}:{MARK_Y},scale=16:8:flags=area,format=gray",
        "-fps_mode", "passthrough", "-f", "rawvideo", "pipe:1",
    ], check=True, timeout=180, stdout=subprocess.PIPE).stdout
    if len(cells) != len(units) * 128 or any(
        marker_ordinal(cells[i * 128:(i + 1) * 128], token) != i for i in range(len(units))
    ):
        raise ValueError("Decoded frame markers failed ordinal verification")
    write_json(args.output / "media.json", {
        "source": source, "clip": clip, "token_hex": f"{token:010x}",
        "changes": "Repeated approved footage, normalized to 960x540 at 12 fps, overlaid a frame marker, encoded H.264.",
        "width": WIDTH, "height": HEIGHT, "fps": FPS, "passes": args.passes,
        "frames": len(units), "marked_sha256": sha256(path),
        "ffmpeg": subprocess.check_output([args.ffmpeg, "-version"], text=True).splitlines()[0],
    })
    return units, token


def rtp_payloads(nal):
    if len(nal) <= MAX_PAYLOAD:
        yield nal
        return
    indicator = (nal[0] & 0xE0) | 28
    nal_type = nal[0] & 31
    for offset in range(1, len(nal), MAX_PAYLOAD - 2):
        end = offset + MAX_PAYLOAD - 2
        flags = (0x80 if offset == 1 else 0) | (0x40 if end >= len(nal) else 0)
        yield bytes((indicator, flags | nal_type)) + nal[offset:end]


def interleaved(channel, data):
    return struct.pack("!BBH", 36, channel, len(data)) + data


class RtspPublisher:
    def __init__(self, sock, url):
        self.sock = sock
        self.url = url
        self.cseq = 0
        self.session = None
        self.reader = sock.makefile("rb")

    def request(self, method, suffix="", headers=None, body=b""):
        self.cseq += 1
        fields = {"CSeq": self.cseq, **(headers or {})}
        if self.session:
            fields["Session"] = self.session
        if body:
            fields["Content-Length"] = len(body)
        message = f"{method} {self.url}{suffix} RTSP/1.0\r\n"
        message += "".join(f"{key}: {value}\r\n" for key, value in fields.items())
        self.sock.sendall(message.encode("ascii") + b"\r\n" + body)
        first = self.reader.read(1)
        while first == b"$":  # The server can send an interleaved RTCP report.
            channel, size = struct.unpack("!BH", self.reader.read(3))
            if channel != 1 or len(self.reader.read(size)) != size:
                raise ValueError("Unexpected server interleaved frame")
            first = self.reader.read(1)
        status = (first + self.reader.readline(8192)).split()
        if status[:2] != [b"RTSP/1.0", b"200"]:
            raise ValueError(f"RTSP {method} rejected or disconnected ({status[:2]!r})")
        response = {}
        for _ in range(50):
            line = self.reader.readline(8192)
            if line == b"\r\n":
                break
            field, value = line.decode("ascii").split(":", 1)
            response[field.lower()] = value.strip()
        else:
            raise ValueError("RTSP response headers exceeded limit")
        size = int(response.get("content-length", "0"))
        if response.get("cseq") != str(self.cseq) or not 0 <= size <= 65_536:
            raise ValueError("Unexpected RTSP response headers")
        if len(self.reader.read(size)) != size:
            raise ValueError("Truncated RTSP response")
        return response

    def start(self, first_unit):
        sps = next(nal for nal in first_unit if nal[0] & 31 == 7)
        pps = next(nal for nal in first_unit if nal[0] & 31 == 8)
        parameters = ",".join(base64.b64encode(nal).decode("ascii") for nal in (sps, pps))
        sdp = "\r\n".join((
            "v=0", "o=- 0 0 IN IP4 127.0.0.1", "s=Operix emission benchmark",
            "c=IN IP4 0.0.0.0", "t=0 0", "m=video 0 RTP/AVP 96",
            "a=rtpmap:96 H264/90000",
            f"a=fmtp:96 packetization-mode=1;profile-level-id={sps[1:4].hex()};sprop-parameter-sets={parameters}",
            "a=control:trackID=0", "",
        ))
        self.request("ANNOUNCE", headers={"Content-Type": "application/sdp"}, body=sdp.encode("ascii"))
        setup = self.request("SETUP", "/trackID=0", {"Transport": "RTP/AVP/TCP;unicast;interleaved=0-1;mode=record"})
        transport = [field.strip() for field in setup.get("transport", "").lower().split(";")]
        if "rtp/avp/tcp" not in transport or "interleaved=0-1" not in transport:
            raise ValueError("RTSP server did not grant channels 0–1")
        self.session = setup.get("session", "").split(";")[0]
        if not self.session:
            raise ValueError("RTSP SETUP returned no session")
        self.request("RECORD", headers={"Range": "npt=0.000-"})


def publish(url, units, emissions):
    server = urlsplit(url)
    with socket.create_connection((server.hostname, server.port or 554), timeout=5) as sock:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        publisher = RtspPublisher(sock, url)
        with publisher.reader:
            publisher.start(units[0])
            ssrc, initial_timestamp, sequence = secrets.randbits(32), secrets.randbits(32), secrets.randbits(16)
            origin = time.monotonic_ns()
            packet_count = octets = 0
            for index, unit in enumerate(units):
                payloads = [payload for nal in unit for payload in rtp_payloads(nal)]
                scheduled = origin + index * 1_000_000_000 // FPS
                remaining = scheduled - time.monotonic_ns()
                if remaining > 0:
                    time.sleep(remaining / 1e9)
                stamp = (initial_timestamp + index * (RTP_HZ // FPS)) & 0xFFFFFFFF
                for offset, payload in enumerate(payloads, 1):
                    last = offset == len(payloads)
                    wire = interleaved(0, struct.pack("!BBHII", 0x80, 96 | (0x80 if last else 0),
                                                      sequence, stamp, ssrc) + payload)
                    if last:
                        before = time.monotonic_ns()
                        sock.sendall(wire)
                        after = time.monotonic_ns()
                        emissions.append({
                            "ordinal": index, "rtp_timestamp": stamp, "ssrc": ssrc,
                            "marker_sequence": sequence, "packet_count": len(payloads),
                            "scheduled_mono_ns": scheduled,
                            "send_before_ns": before, "send_after_ns": after,
                        })
                    else:
                        sock.sendall(wire)
                    sequence = (sequence + 1) & 0xFFFF
                    packet_count += 1
                    octets += len(payload)
                if index % FPS == 0:
                    # RTCP SR for the receiver. Civil time is never used for latency.
                    utc_ns = time.time_ns()
                    ntp_s, remainder = divmod(utc_ns, 1_000_000_000)
                    sr = struct.pack("!BBHIIIIII", 0x80, 200, 6, ssrc, (ntp_s + 2_208_988_800) & 0xFFFFFFFF,
                                     (remainder << 32) // 1_000_000_000, stamp, packet_count, octets)
                    sock.sendall(interleaved(1, sr))
            # Signal replay EOF after the kernel drains the TCP send buffer.
            sock.shutdown(socket.SHUT_WR)


def api_session(base):
    client = requests.Session()
    client.trust_env = False
    client.headers.update({"Cache-Control": "no-cache, no-store", "Pragma": "no-cache"})
    session_url = base + "/api/v1/auth/session/"
    try:
        info = api_get(client, session_url).json()
        credentials = {
            "username": os.environ["OPERIX_LAB_TEST_SAFETY_LEAD_USER"],
            "password": os.environ["OPERIX_LAB_TEST_SAFETY_LEAD_PASSWORD"],
        }
        response = client.post(base + "/api/v1/auth/login/", json=credentials,
                               headers={"Origin": base, "X-CSRFToken": info["csrf_token"]},
                               timeout=5, allow_redirects=False)
        if response.status_code != 200 or response.json()["user"]["role"] != "safety_lead":
            raise ValueError("Event API login did not grant safety_lead access")
    except BaseException:
        client.close()
        raise
    return client


def api_get(client, url):
    response = client.get(url, timeout=5, allow_redirects=False)
    if response.status_code != 200:
        raise ValueError(f"Event API GET returned HTTP {response.status_code}")
    return response


def observe(client, url, run_id, clip, state):
    started = time.monotonic_ns()
    response = api_get(client, url)
    finished = time.monotonic_ns()  # Requests has read the entire body.
    rows = response.json()
    if not isinstance(rows, list):
        raise ValueError("Expected the complete unpaginated Operix event list")
    poll = {"start_ns": started, "finish_ns": finished, "run_events": []}
    current = {}
    for row in rows:
        source = row.get("source", {})
        if row.get("analysis_run_id") != run_id:
            continue
        if (source.get("kind"), source.get("camera_id"), source.get("video_sha256"),
                source.get("timestamp_basis"), row.get("view_id")) != (
            "lab", clip["camera_id"], clip["sha256"], "LAB_RECEPTION_UTC", clip["camera_id"],
        ):
            raise ValueError("Analysis run contains unexpected source provenance")
        event_id = str(UUID(row["id"]))
        current[event_id] = row
        poll["run_events"].append(event_id)
    if state["events"].keys() - current.keys():
        raise ValueError("Events disappeared from the list during polling")
    for event_id, row in current.items():
        first = state["events"].setdefault(event_id, {
            "first_poll": len(state["polls"]), "row": row,
        })
        if row.get("evidence_url"):
            first["row"] = row
    state["polls"].append(poll)


def correlate(client, base, state, emissions, token):
    result = []
    for event_id, observation in state["events"].items():
        event = observation["row"]
        selected = {key: event.get(key) for key in (
            "id", "analysis_run_id", "view_id", "event_type", "rule_id", "rule_version",
            "frame_index", "video_timestamp_s", "created_at", "occurred_at", "episode",
            "zone_id", "track_id", "class_name", "pair_key",
        )}
        source = event["source"]
        selected.update({"capture": source.get("capture"), "epoch": source.get("epoch"),
                         "config_sha256": source.get("config_sha256"),
                         "video_sha256": source["video_sha256"], "camera_id": source["camera_id"]})
        item = {"event": selected, "first_poll": observation["first_poll"]}
        result.append(item)
        if observation["first_poll"] == 0:
            item["unmatched"] = "Already present in the pre-replay list"
            continue
        evidence = f"/api/v1/events/{event_id}/evidence/"
        if event.get("evidence_url") != evidence:
            item["unmatched"] = "Same-origin candidate evidence URL unavailable"
            continue
        try:
            png = api_get(client, base + evidence).content
            with Image.open(io.BytesIO(png), formats=["PNG"]) as image:
                ordinal = frame_marker(image, token)
            emission = emissions[ordinal]
        except (OSError, IndexError, ValueError, requests.RequestException) as error:
            item["unmatched"] = str(error)
            continue
        present = state["polls"][observation["first_poll"]]["finish_ns"]
        absent = state["polls"][observation["first_poll"] - 1]["start_ns"]
        if present < emission["send_before_ns"]:
            item["unmatched"] = "HTTP observation predates marked frame egress"
            continue
        item.update({
            "emission_ordinal": ordinal,
            "candidate_png_sha256": hashlib.sha256(png).hexdigest(),
            "latency_ms": {
                "min": max(0, absent - emission["send_after_ns"]) / 1e6,
                "max": (present - emission["send_before_ns"]) / 1e6,
            },
            "first_response_after_send_return_ms": (present - emission["send_after_ns"]) / 1e6,
        })
    return result


def measure(args, clip, units, token):
    state = {"polls": [], "events": {}}
    emissions = []
    report = {
        "schema_version": 1, "status": "incomplete", "run_id": str(args.run_id), "camera_id": args.camera,
        "monitor_clock": vars(time.get_clock_info("monotonic")),
        "source_boundary": "Local TCP sendall of the full RTP marker packet, bracketed by calls to the observer clock",
        "availability_boundary": "First authenticated complete HTTP GET event-list response containing the event",
        "poll_target_s": args.poll, "post_replay_s": args.tail,
        "clock_start": clock_anchor(),
    }
    try:
        with api_session(args.base_url) as client:
            listing = args.base_url + f"/api/v1/events/?camera_id={args.camera}&source_sha256={clip['sha256']}"
            def poll():
                observe(client, listing, str(args.run_id), clip, state)

            poll()
            with ThreadPoolExecutor(max_workers=1) as pool:
                replay = pool.submit(publish, args.rtsp_url, units, emissions)
                while not replay.done():
                    poll()
                    time.sleep(args.poll)
                replay.result()
            deadline = time.monotonic() + args.tail
            while True:
                poll()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(args.poll, remaining))
            report["results"] = correlate(client, args.base_url, state, emissions, token)
        report["matched"] = sum("latency_ms" in item for item in report["results"])
        report["status"] = "matched" if report["matched"] else "no_verified_matches"
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        report["clock_end"] = clock_anchor()
        report["polls"] = state["polls"]
        report["emissions"] = emissions
        write_json(args.output / "report.json", report)
    print(f"{report['status']} ({report['matched']} matched events) — {args.output / 'report.json'}")
    return 0 if report["matched"] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "measure"))
    parser.add_argument("--media-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New directory for marked media and reports")
    parser.add_argument("--camera", required=True, choices=("lab-cam-01", "lab-cam-02"))
    parser.add_argument("--ffmpeg", default="ffmpeg", help="FFmpeg executable with libx264")
    parser.add_argument("--passes", type=int, choices=range(1, 5), default=3)
    parser.add_argument("--rtsp-url", help="Reachable unauthenticated MediaMTX publish URL for the selected camera")
    parser.add_argument("--base-url", default="http://127.0.0.1:13000", help="Operix HTTP(S) origin")
    parser.add_argument("--run-id", type=UUID, help="UUID of the camera analysis run already armed for replay")
    parser.add_argument("--poll", type=float, default=.15)
    parser.add_argument("--tail", type=float, default=8)
    args = parser.parse_args()
    if args.mode == "measure":
        url = urlsplit(args.rtsp_url or "")
        origin = urlsplit(args.base_url)
        if (url.scheme != "rtsp" or not url.hostname or url.username is not None
                or url.query or url.fragment or url.path != "/" + args.camera
                or not args.rtsp_url.isascii() or re.search(r"\s", args.rtsp_url) or url.port == 0):
            parser.error("--rtsp-url must be a plain RTSP URL ending in the selected camera ID")
        if (origin.scheme not in ("http", "https") or not origin.hostname or origin.path
                or origin.username is not None or origin.query or origin.fragment or origin.port == 0):
            parser.error("--base-url must be an HTTP(S) origin")
        if (not args.run_id or not .02 <= args.poll <= 5
                or not math.isfinite(args.tail) or not 0 <= args.tail <= 120):
            parser.error("measure requires --run-id, --poll in 0.02–5 s and --tail in 0–120 s")
    manifest = json.loads(Path(__file__).with_name("approved-media.json").read_text(encoding="utf-8"))
    clip = next(clip for clip in manifest["clips"] if clip["camera_id"] == args.camera)
    args.output.mkdir(parents=True, exist_ok=False)
    units, token = prepare(args, clip, manifest["source"])
    if args.mode == "measure":
        return measure(args, clip, units, token)
    print(f"Verified {len(units)} marked frames — {args.output / 'media.json'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, requests.RequestException) as error:
        sys.exit(f"Benchmark failed: {error}")
