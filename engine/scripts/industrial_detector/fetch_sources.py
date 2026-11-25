# SPDX-License-Identifier: AGPL-3.0-or-later
"""Download the exact, licensed public archives used by the experiment."""
import argparse
import urllib.request
from pathlib import Path

from prepare import PINNED, digest

MAX_ARCHIVE_BYTES = 650_000_000


def fetch(root):
    root.mkdir(parents=True, exist_ok=True)
    for name, (url, expected) in PINNED.items():
        destination = root / name
        if destination.exists():
            if digest(destination) != expected:
                raise ValueError(f"Existing archive does not match the published experiment: {name}")
            continue
        part = root / (name + ".part")
        request = urllib.request.Request(url, headers={"User-Agent": "Operix-Industrial-Detector-Lab"})
        total = 0
        with urllib.request.urlopen(request, timeout=30) as reply, part.open("xb") as stream:
            while block := reply.read(1024 * 1024):
                total += len(block)
                if total > MAX_ARCHIVE_BYTES:
                    raise ValueError(f"Download exceeds the archive budget: {name}")
                stream.write(block)
        if digest(part) != expected:
            raise ValueError(f"Downloaded archive did not match pinned bytes: {name}")
        part.rename(destination)
        print(f"{name} {total} bytes {expected}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", type=Path)
    fetch(parser.parse_args().archives)
