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
        results = [epoch.advance(frame) for frame in sequence]
        self.assertEqual([reason for reason, _ in results], ["initial", None, "queue_gap", "reconnect"])
        self.assertEqual([results[i][1] for i in (0, 2, 3)], [0, 0, 0])
        self.assertEqual(epoch.number, 3)

    def test_pts_gap_without_decoded_index_gap(self):
        epoch = Epoch(12)
        epoch.advance(Frame(10, 1, 10, 5, None))
        self.assertEqual(epoch.advance(Frame(11, 1, 10.2, 5.25, None)), ("source_pts_gap", 0))

    def test_clock_basis_change_starts_an_epoch(self):
        epoch = Epoch(12)
        epoch.advance(Frame(0, 1, 10, None, None))
        self.assertEqual(epoch.advance(Frame(1, 1, 10.08, 5, None)), ("pts_available", 0))
        self.assertEqual(epoch.advance(Frame(2, 1, 10.16, None, None)), ("missing_pts", 0))


class CaptureTests(unittest.TestCase):
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

        capture = Capture(Reader, fps=12, capacity=3)
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
