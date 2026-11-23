import threading
import unittest

from operix_engine.rtsp_pilot import Capture, Epoch, Frame


class EpochTests(unittest.TestCase):
    def test_queue_gap_and_reconnect_restart_timeline(self):
        epoch = Epoch(12)
        sequence = [
            Frame(0, 1, 10, 5, None),
            Frame(1, 1, 10.08, 5.08, None),
            Frame(3, 1, 10.25, 5.25, None),
            Frame(4, 2, 12, 1, None),
        ]
        results, preserved = [], []
        for frame in sequence:
            results.append(epoch.advance(frame))
            preserved.append(epoch.preserve_tracking)
        self.assertEqual([reason for reason, _ in results], ["initial", None, "queue_gap", "reconnect"])
        self.assertEqual([results[i][1] for i in (0, 2, 3)], [0, 0, 0])
        self.assertEqual(epoch.number, 3)
        self.assertEqual(preserved, [False, False, True, False])

    def test_ambiguous_or_repeated_gaps_do_not_preserve_tracking(self):
        for frame in (
            Frame(4, 1, 10.25, 5.25, None),             # más de un cuadro
            Frame(3, 1, 10.25, None, None),             # reloj perdido
            Frame(3, 1, 10.25, 5.08, None),             # PTS repetido
            Frame(3, 1, 10.25, 5.16, None),             # PTS no respalda el salto
            Frame(3, 1, 10.8, 5.25, None),              # llegada demasiado tardía
            Frame(3, 1, 10.07, 5.25, None),             # llegada fuera de orden
            Frame(3, 2, 10.25, 5.25, None),             # otra conexión
        ):
            with self.subTest(frame=frame):
                epoch = Epoch(12)
                epoch.advance(Frame(0, 1, 10, 5, None))
                epoch.advance(Frame(1, 1, 10.08, 5.08, None))
                self.assertIsNotNone(epoch.advance(frame)[0])
                self.assertFalse(epoch.preserve_tracking)

        epoch = Epoch(12)
        for index in (0, 1, 3):
            epoch.advance(Frame(index, 1, 10 + index / 12, index / 12, None))
        self.assertTrue(epoch.preserve_tracking)
        self.assertEqual(epoch.advance(Frame(5, 1, 10 + 5 / 12, 5 / 12, None))[0], "queue_gap")
        self.assertFalse(epoch.preserve_tracking)

    def test_pts_gap_without_decoded_index_gap(self):
        epoch = Epoch(12)
        epoch.advance(Frame(10, 1, 10, 5, None))
        self.assertEqual(epoch.advance(Frame(11, 1, 10.2, 5.25, None)), ("source_pts_gap", 0))
        self.assertFalse(epoch.preserve_tracking)

    def test_clock_basis_change_starts_an_epoch(self):
        epoch = Epoch(12)
        epoch.advance(Frame(0, 1, 10, None, None))
        self.assertEqual(epoch.advance(Frame(1, 1, 10.08, 5, None)), ("pts_available", 0))
        self.assertEqual(epoch.advance(Frame(2, 1, 10.16, None, None)), ("missing_pts", 0))


class CaptureTests(unittest.TestCase):
    def test_a_failed_connection_invalidates_an_inflight_frame_before_reopening(self):
        fail = threading.Event()
        closing = threading.Event()
        release = threading.Event()

        class Reader:
            delivered = False

            def read(self):
                if not self.delivered:
                    self.delivered = True
                    return object(), 0.
                fail.wait(2)
                raise OSError

            def close(self):
                closing.set()
                release.wait(2)

        capture = Capture(Reader, fps=12)
        with capture:
            try:
                frame = capture.next(timeout=2)
                self.assertIsNotNone(frame)
                self.assertTrue(capture.is_current(frame))
                fail.set()
                self.assertTrue(closing.wait(2))
                self.assertEqual(capture.connection, frame.connection)
                self.assertFalse(capture.is_current(frame))
            finally:
                capture.stop.set()
                fail.set()
                release.set()

    def test_saturation_is_counted_and_shutdown_closes_reader(self):
        filled = threading.Event()
        closed = threading.Event()
        stop = threading.Event()

        class Reader:
            index = 0
            def read(self):
                self.index += 1
                if self.index > 10:
                    filled.set()
                    stop.wait(2)
                    raise OSError
                return object(), None

            def close(self):
                closed.set()

        capture = Capture(Reader, fps=12, capacity=3, startup_seconds=0)
        with capture:
            self.assertTrue(filled.wait(2))
            self.assertEqual(capture.next().index, 7)
            self.assertEqual(capture.counts["queue_drop"], 7)
            capture.stop.set()
            stop.set()
        self.assertTrue(closed.is_set())
        self.assertFalse(capture.thread.is_alive())
        self.assertEqual(capture.counts["decoded"], 10)
        self.assertEqual(capture.counts["shutdown_drop"], 2)

    def test_startup_backpressure_preserves_buffered_frames_and_stop_wakes_reader(self):
        filled = threading.Event()

        class Reader:
            index = 0

            def read(self):
                self.index += 1
                if self.index == 2:
                    filled.set()
                return object(), self.index / 12

            def close(self):
                pass

        capture = Capture(Reader, fps=12, capacity=2)
        with capture:
            self.assertTrue(filled.wait(1))
            frames = [capture.next() for _ in range(5)]
            self.assertEqual([f.index for f in frames], list(range(5)))
            self.assertEqual([f.pts for f in frames], [n / 12 for n in range(1, 6)])
            self.assertEqual(capture.counts["queue_drop"], 0)
        self.assertFalse(capture.thread.is_alive())

    def test_persistent_saturation_falls_back_after_startup_window(self):
        discarded = threading.Event()
        capture = None

        class Reader:
            def read(self):
                return object(), None

            def close(self):
                pass

        def trace(kind, *_args, **_fields):
            if kind == "queue_drop":
                capture.stop.set()
                discarded.set()

        capture = Capture(Reader, fps=12, capacity=2, startup_seconds=.05, trace=trace)
        with capture:
            self.assertTrue(discarded.wait(2))
        self.assertEqual(capture.depth, 2)
        self.assertEqual(capture.counts["decoded"], 3)
        self.assertEqual(capture.counts["queue_drop"], 1)
        self.assertEqual(capture.counts["shutdown_drop"], 2)

    def test_open_and_read_errors_reconnect_with_new_connection(self):
        ready = threading.Event()
        release = threading.Event()
        attempts = []

        class Reader:
            def __init__(self, number):
                self.number = number
                self.delivered = False

            def read(self):
                if self.number == 2:
                    raise OSError
                if self.delivered:
                    ready.set()
                    release.wait(2)
                    raise OSError
                self.delivered = True
                return object(), 0.0

            def close(self):
                pass

        def open_source():
            attempts.append(1)
            if len(attempts) == 1:
                raise OSError
            return Reader(len(attempts))

        capture = Capture(open_source, fps=12)
        with capture:
            try:
                self.assertTrue(ready.wait(3))
                self.assertEqual(capture.next().connection, 2)
                self.assertEqual(capture.counts["open_failure"], 1)
                self.assertEqual(capture.counts["read_failure"], 1)
            finally:
                capture.stop.set()
                release.set()
