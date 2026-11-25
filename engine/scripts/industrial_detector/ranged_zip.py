# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read bounded public ZIP members without downloading an entire archive."""
import io
import os
import zipfile
from urllib.request import Request, urlopen


class RangedZip(io.RawIOBase):
    def __init__(self, url, size, *, budget=200_000_000):
        self.url, self.size, self.budget = url, size, budget
        self.position = 0
        self.transferred = 0

    def seek(self, offset, whence=os.SEEK_SET):
        origin = {os.SEEK_SET:0, os.SEEK_CUR:self.position, os.SEEK_END:self.size}[whence]
        self.position = origin + offset
        if self.position < 0:
            raise ValueError("negative offset")
        return self.position

    def tell(self):
        return self.position

    def read(self, n=-1):
        remaining = max(0, self.size-self.position)
        length = remaining if n < 0 else min(n,remaining)
        if not length:
            return b""
        if self.transferred + length > self.budget:
            raise ValueError("range budget exceeded")
        if length > 262144:
            return b"".join(self.read(min(262144, length - offset)) for offset in range(0, length, 262144))
        first, last = self.position, self.position + length - 1
        query = "&" if "?" in self.url else "?"
        request = Request(f"{self.url}{query}operixrange={first}-{last}",
                          headers={"Range":f"bytes={first}-{last}", "Accept-Encoding":"identity"})
        with urlopen(request, timeout=25) as response:
            if response.status != 206 or response.headers["Content-Range"] != f"bytes {first}-{last}/{self.size}":
                raise OSError("publisher did not honor exact byte range")
            data = response.read(length+1)
        if len(data) != length:
            raise OSError("range length mismatch")
        self.position += length
        self.transferred += length
        return data


def inspect(url, size):
    with zipfile.ZipFile(RangedZip(url,size)) as archive:
        members = archive.infolist()
        print(len(members), [(i.filename,i.file_size) for i in members[:15]])
        print([(i.filename,i.file_size) for i in members if i.filename.lower().endswith((".json",".csv",".txt"))][:35])


if __name__=="__main__":
    import sys
    inspect(sys.argv[1], int(sys.argv[2]))
