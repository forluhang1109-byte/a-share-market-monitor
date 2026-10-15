import sys
import time
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from a_share_monitor.collection import collect, delivery_gate


def slow_task(name, args, out):
    if name == "fetch_limit_stats":
        time.sleep(20)
    out.put((name, [], {"ok": True}))


class CollectionTests(unittest.TestCase):
    def meta(self):
        return {"is_trading_day": True, "calendar_source": "exchange_calendars:XSHG",
                "collection_started_at": "2026-10-15T14:40:00+08:00",
                "collection_completed_at": "2026-10-15T14:41:00+08:00",
                "source_status": {k: {"ok": True} for k in ("a_share_spot", "indices")}}

    def test_fresh(self):
        self.assertTrue(delivery_gate(self.meta(), datetime.fromisoformat("2026-10-15T14:45:00+08:00"))[0])

    def test_stale_wrong_day_and_missing_core(self):
        for stamp in ("2026-10-16T14:45:00+08:00", "2026-10-15T14:49:00+08:00"):
            self.assertFalse(delivery_gate(self.meta(), datetime.fromisoformat(stamp))[0])
        m = self.meta(); m["source_status"]["indices"]["ok"] = False
        self.assertFalse(delivery_gate(m, datetime.fromisoformat("2026-10-15T14:45:00+08:00"))[0])

    def test_slow_optional_is_killed_without_losing_completed_core(self):
        t = time.monotonic()
        data = collect({}, "20261015", budget_seconds=2, task_target=slow_task)
        self.assertLess(time.monotonic() - t, 5)
        self.assertTrue(data["fetch_indices"][1]["ok"])
        self.assertTrue(data["fetch_limit_stats"][1]["timed_out"])


if __name__ == "__main__":
    unittest.main()
