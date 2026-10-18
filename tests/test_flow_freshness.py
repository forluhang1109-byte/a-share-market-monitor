import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from a_share_monitor.providers import validate_market_flow_date

class FlowFreshnessTests(unittest.TestCase):
    def test_today(self):
        self.assertTrue(validate_market_flow_date({'日期': '2026-10-16'}, '2026-10-16'))

    def test_old_unknown_or_invalid(self):
        for row in ({'日期': '2026-10-15'}, {}, {'日期': 'not-a-date'}):
            self.assertFalse(validate_market_flow_date(row, '2026-10-16'))
