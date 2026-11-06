"""Emisor RTSP/H.264 de loopback para pruebas del piloto, sin servicios externos."""

import argparse
import base64
from pathlib import Path
import re
import socket
from struct import pack
from time import monotonic, sleep

import cv2


def load_units(path):
    cap = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG)
    if not cap.set(cv2.CAP_PROP_FORMAT, -1):
        raise ValueError("Se requiere MP4 H.264 con acceso a paquetes Annex B")
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        units = []
        while True:
            ok, data = cap.read()
            if not ok:
                break
            units.append([nal for nal in re.split(b"\\x00\\x00(?:\\x00)?\\x01", data.tobytes()) if nal])
    finally:
        cap.release()
    sps, pps = (next(nal for nal in units[0] if nal[0] & 31 == kind) for kind in (7, 8))
    return fps, units, sps, pps


def packets(nal):
    if len(nal) <= 1200:
        yield nal
        return
    header = nal[0]
    for offset in range(1, len(nal), 1198):
        stop = min(len(nal), offset + 1198)
        flags = (128 if offset == 1 else 0) | (64 if stop == len(nal) else 0)
        yield bytes(((header & 0xe0) | 28, (header & 31) | flags)) + nal[offset:stop]


def serve(client, url, fixture, cutoff, damage_at):
    fps, units, sps, pps = fixture
    file = client.makefile("rb")
    try:
        while line := file.readline(8192):
            method = line.decode("ascii").split()[0]
            headers = {}
            while (header := file.readline(8192)) not in (b"\r\n", b""):
                key, value = header.decode("ascii").split(":", 1)
                headers[key.lower()] = value.strip()
            response = [f"CSeq: {headers['cseq']}"]
            content = b""
            if method == "OPTIONS":
                response.append("Public: OPTIONS, DESCRIBE, SETUP, PLAY, TEARDOWN")
            elif method == "DESCRIBE":
                parameter_sets = ",".join(base64.b64encode(nal).decode() for nal in (sps, pps))
                content = (f"v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\ns=Operix fixture\r\nt=0 0\r\n"
                           f"a=control:*\r\nm=video 0 RTP/AVP 96\r\na=rtpmap:96 H264/90000\r\n"
                           f"a=framerate:{fps}\r\na=fmtp:96 packetization-mode=1;sprop-parameter-sets={parameter_sets}\r\n"
                           f"a=control:trackID=0\r\n").encode()
                response.extend(["Content-Type: application/sdp", f"Content-Base: {url}/",
                                 f"Content-Length: {len(content)}"])
            elif method == "SETUP":
                response.extend(["Transport: RTP/AVP/TCP;unicast;interleaved=0-1", "Session: 1"])
            elif method == "PLAY":
                response.extend(["Session: 1", f"RTP-Info: url={url}/trackID=0;seq=1;rtptime=0"])
            client.sendall(("RTSP/1.0 200 OK\r\n" + "\r\n".join(response) + "\r\n\r\n").encode() + content)
            if method == "PLAY":
                break
        started = monotonic()
        seq = 1
        for index in range(cutoff or len(units)):
            sleep(max(0, started + index / fps - monotonic()))
            nals = [b"\x65\x00"] if index == damage_at else units[index % len(units)]
            chunks = [chunk for nal in nals for chunk in packets(nal)]
            for i, chunk in enumerate(chunks):
                header = pack("!BBHII", 128, 96 | (128 if i == len(chunks)-1 else 0),
                              seq % 65536, round(index * 90000 / fps) % 2**32, 1)
                client.sendall(pack("!BBH", 36, 0, len(header) + len(chunk)) + header + chunk)
                seq += 1
    finally:
        file.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("--port", type=int, default=18554)
    parser.add_argument("--cut-first", type=int, default=0)
    parser.add_argument("--damage-first-at", type=int)
    args = parser.parse_args()
    fixture = load_units(args.video)
    with socket.create_server(("127.0.0.1", args.port)) as server:
        url = f"rtsp://127.0.0.1:{args.port}/fixture"
        print("Emisor RTSP local listo", flush=True)
        first = True
        while True:
            client, _ = server.accept()
            with client:
                client.settimeout(3)
                try:
                    serve(client, url, fixture, args.cut_first if first else 0,
                          args.damage_first_at if first else None)
                except (OSError, ValueError):
                    pass
            first = False


if __name__ == "__main__":
    main()
