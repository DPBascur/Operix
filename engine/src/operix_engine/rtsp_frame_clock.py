"""Read the managed publisher's in-band frame identity alongside decoded pixels."""

import math
import re
from uuid import UUID


SEI_ID = UUID("2dcd53fa-e376-4a1b-81c9-90511ff6dc2f")
PAYLOAD = re.compile(rb"ox1:([0-9a-f]{32}):(0|[1-9][0-9]{0,8})")


def read_ordinal(side_data, stream_id):
    ordinals = []
    for item in side_data:
        if item.type.name != "SEI_UNREGISTERED" or not 16 < item.buffer_size <= 80:
            continue
        data = bytes(item)
        if not data.startswith(SEI_ID.bytes):
            continue
        match = PAYLOAD.fullmatch(data[16:])
        if not match or match[1] != stream_id.encode("ascii"):
            raise OSError("Marca de origen RTSP incompatible")
        ordinals.append(int(match[2]))
    if len(ordinals) != 1:
        raise OSError("Marca de origen RTSP ausente o ambigua")
    return ordinals[0]


class ClockedReader:
    def __init__(self, url, fps, dimensions, stream_id):
        import av

        self.av = av
        self.container = None
        self.dimensions = dimensions
        self.stream_id = stream_id
        self.fps = fps
        self.source_ordinal = None
        self.last_pts = None
        try:
            self.container = av.open(url, timeout=(2.5, 1.5), options={
                "rtsp_transport": "tcp", "probesize": "65536", "analyzeduration": "250000",
            })
            video = self.container.streams.video[0]
            video.codec_context.thread_count = 1
            if video.average_rate and not math.isclose(float(video.average_rate), fps, abs_tol=.2):
                raise OSError("Cadencia RTSP inválida")
            self.frames = iter(self.container.decode(video))
        except (IndexError, OSError, av.FFmpegError):
            self.close()
            raise OSError("Apertura RTSP sincronizada fallida") from None

    def read(self):
        frame, pts = self.read_native()
        return self.to_image(frame), pts

    @staticmethod
    def to_image(frame):
        return frame.to_ndarray(format="bgr24")

    def read_native(self):
        try:
            frame = next(self.frames)
            if (frame.width, frame.height) != self.dimensions:
                raise OSError("Dimensiones RTSP inválidas")
            ordinal = read_ordinal(frame.side_data[:], self.stream_id)
            pts = frame.time
            if self.source_ordinal is not None:
                count = ordinal - self.source_ordinal
                if count <= 0:
                    raise OSError("Ordinal RTSP repetido o invertido")
                if self.last_pts is not None and pts is not None and not math.isclose(
                    pts - self.last_pts, count / self.fps, rel_tol=0, abs_tol=.006,
                ):
                    raise OSError("PTS RTSP incompatible con la cadencia de origen")
            self.source_ordinal = ordinal
            self.last_pts = pts
            return frame, pts
        except (StopIteration, self.av.FFmpegError):
            raise OSError("Decodificación RTSP sincronizada fallida") from None

    def close(self):
        if self.container is not None:
            self.container.close()
