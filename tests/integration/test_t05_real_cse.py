"""Run explicitly against an actual CSE; no skip or mock substitution."""
import unittest

from backend.config import Settings
from backend.p0 import run


class ActualCSEIntegration(unittest.TestCase):
    def test_t05_actual_subscription_round_trip(self):
        summary, evidence = run(Settings.load())
        self.assertEqual(summary["state"], "PASS", f"{summary['state']}: evidence at {evidence}; {summary.get('reason', '')}")
