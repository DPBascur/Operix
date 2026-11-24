# Copyright (C) 2026 Daniel Felipe Peña Bascur
# SPDX-License-Identifier: AGPL-3.0-or-later
import unittest
from unittest.mock import Mock

from benchmark_readiness import LabReadinessError, check_lab_readiness


class BenchmarkReadinessTests(unittest.TestCase):
    def setUp(self):
        self.control = {"status": "disabled", "cameras": []}
        self.direct = Mock(return_value=(200, self.control))
        self.sleep = Mock()

    def test_proxy_reset_then_recovery(self):
        proxy = Mock(side_effect=[(500, None), (200, self.control)])
        self.assertEqual(
            check_lab_readiness(self.direct, proxy, sleep=self.sleep),
            (self.control, [500, 200]),
        )
        self.direct.assert_called_once_with()
        self.sleep.assert_called_once_with(1)

    def test_service_error_and_active_lab_fail_before_calling_proxy(self):
        proxy = Mock()
        for response in ((500, None), (200, {"status": "active"})):
            self.direct.return_value = response
            with self.assertRaises(LabReadinessError):
                check_lab_readiness(self.direct, proxy, sleep=self.sleep)
        proxy.assert_not_called()
        self.sleep.assert_not_called()

    def test_proxy_auth_failure_is_not_retried(self):
        proxy = Mock(return_value=(403, None))
        with self.assertRaises(LabReadinessError):
            check_lab_readiness(self.direct, proxy, sleep=self.sleep)
        proxy.assert_called_once_with()
        self.sleep.assert_not_called()

    def test_proxy_availability_retries_are_bounded(self):
        proxy = Mock(side_effect=[(None, None), (502, None), (503, None)])
        with self.assertRaisesRegex(LabReadinessError, r"\[None, 502, 503\]"):
            check_lab_readiness(self.direct, proxy, sleep=self.sleep)
        self.assertEqual(proxy.call_count, 3)
        self.assertEqual(self.sleep.call_count, 2)

    def test_proxy_must_report_the_same_control_state(self):
        proxy = Mock(return_value=(200, {"status": "active"}))
        with self.assertRaises(LabReadinessError):
            check_lab_readiness(self.direct, proxy, sleep=self.sleep)
        proxy.assert_called_once_with()
        self.sleep.assert_not_called()
