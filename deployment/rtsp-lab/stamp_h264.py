"""Attach a versioned source ordinal to each picture in a lab H.264 stream."""

import re
import sys
from uuid import UUID


SEI_ID = UUID("2dcd53fa-e376-4a1b-81c9-90511ff6dc2f")
START = re.compile(rb"\x00\x00\x01")
MAX_NAL = 8 * 1024 * 1024


def stamp(stream_id, ordinal):
    body = SEI_ID.bytes + f"ox1:{stream_id}:{ordinal}".encode("ascii")
    rbsp = bytes((5, len(body))) + body + b"\x80"
    return b"\x00\x00\x00\x01\x06" + re.sub(rb"\x00\x00(?=[\x00-\x03])", b"\x00\x00\x03", rbsp)


def nals(source):
    pending = bytearray()
    search_at = 0
    while chunk := source.read1(65536):
        pending.extend(chunk)
        start = START.search(pending, search_at)
        while start:
            boundary = start.start()
            if boundary and pending[boundary - 1] == 0:
                boundary -= 1
            if boundary:
                yield pending[:boundary]
                del pending[:boundary]
            start = START.search(pending, 4)
        if len(pending) > MAX_NAL:
            raise ValueError("H.264 NAL exceeded the lab size bound")
        search_at = max(4, len(pending) - 3) if len(pending) >= 4 else 0
    if pending:
        yield pending


def mark(source, target, stream_id):
    ordinal = 0
    aud = False
    picture = False
    for nal in nals(source):
        header = START.match(nal, 1) or START.match(nal)
        if not header or header.end() >= len(nal):
            raise ValueError("Invalid Annex B unit")
        kind = nal[header.end()] & 31
        if kind == 9:
            if aud and not picture:
                raise ValueError("H.264 access unit had no picture")
            aud, picture = True, False
        elif kind in (1, 5) and not picture:
            if not aud:
                raise ValueError("H.264 source must provide an access unit delimiter")
            target.write(stamp(stream_id, ordinal))
            ordinal += 1
            picture = True
        target.write(nal)
        if kind in (1, 5):
            target.flush()
    if ordinal == 0 or not picture:
        raise ValueError("H.264 ended without a complete picture")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not re.fullmatch("[a-f0-9]{32}", sys.argv[1]):
        raise SystemExit("Invalid public stream identifier")
    mark(sys.stdin.buffer, sys.stdout.buffer, sys.argv[1])
