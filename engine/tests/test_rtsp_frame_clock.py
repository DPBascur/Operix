from types import SimpleNamespace
from unittest import TestCase

from operix_engine.rtsp_frame_clock import ClockedReader, SEI_ID, read_ordinal


class SideData(bytes):
    type = SimpleNamespace(name="SEI_UNREGISTERED")

    @property
    def buffer_size(self):
        return len(self)


class FrameClockTests(TestCase):
    def test_only_one_matching_source_marker_is_valid(self):
        stream = "a" * 32
        tag = SideData(SEI_ID.bytes + f"ox1:{stream}:0".encode())
        unrelated = SideData(b"x" * 32)
        self.assertEqual(read_ordinal([unrelated, tag], stream), 0)
        for records, expected in (([tag, tag], stream), ([tag], "b" * 32), ([unrelated], stream)):
            with self.subTest(records=records, expected=expected), self.assertRaises(OSError):
                read_ordinal(records, expected)

    def test_malformed_payload_is_never_associated_with_a_picture(self):
        stream = "a" * 32
        invalid = SideData(SEI_ID.bytes + f"ox1:{stream}:01".encode())
        with self.assertRaises(OSError):
            read_ordinal([invalid], stream)

    def test_cfr_ticks_agree_with_the_source_ordinal_even_after_a_dropped_picture(self):
        stream = "c" * 32
        reader = ClockedReader.__new__(ClockedReader)
        reader.av = SimpleNamespace(FFmpegError=RuntimeError)
        reader.source_ordinal = reader.last_pts = None
        reader.dimensions, reader.fps, reader.stream_id = (960, 540), 30, stream
        reader.frames = iter(SimpleNamespace(
            width=960, height=540, time=pts,
            side_data=[SideData(SEI_ID.bytes + f"ox1:{stream}:{ordinal}".encode())],
            to_ndarray=lambda format: format,
        ) for ordinal, pts in ((10, 3.), (12, 3. + 2 / 30), (13, 103.)))
        self.assertEqual(reader.read(), ("bgr24", 3.))
        self.assertEqual(reader.read(), ("bgr24", 3. + 2 / 30))
        with self.assertRaisesRegex(OSError, "PTS RTSP"):
            reader.read()
