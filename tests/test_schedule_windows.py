"""Regression checks for best-effort GitHub Actions schedule delays."""
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from a_share_monitor.collection import session_collection_window
import a_share_monitor.main as monitor_main
import run_snapshot as runner


def sample(day, session, started, ended, status="ok"):
    return {"meta": {
        "date": day,
        "session": session,
        "is_trading_day": True,
        "status": status,
        "collection_started_at": f"{day}T{started}+08:00",
        "collection_completed_at": f"{day}T{ended}+08:00",
    }}


class ScheduleWindowsTests(unittest.TestCase):
    def test_valid_collection_windows(self):
        self.assertTrue(session_collection_window(sample("2026-10-30", "noon", "11:31:00", "11:32:30")["meta"], "noon"))
        self.assertTrue(session_collection_window(sample("2026-10-30", "close", "14:40:00", "14:41:00")["meta"], "close"))

    def test_late_collection_rejected_even_if_provider_data_is_valid(self):
        self.assertFalse(session_collection_window(sample("2026-10-30", "noon", "17:07:00", "17:08:00")["meta"], "noon"))
        self.assertFalse(session_collection_window(sample("2026-10-30", "close", "19:41:00", "19:42:00")["meta"], "close"))
        self.assertFalse(session_collection_window(sample("2026-10-30", "close", "14:47:40", "14:49:00")["meta"], "close"))

    def test_wrong_or_missing_timestamp_rejected(self):
        m = sample("2026-10-30", "noon", "11:31:00", "11:32:00")["meta"]
        m["date"] = "2026-10-29"
        self.assertFalse(session_collection_window(m, "noon"))
        m["date"] = "2026-10-30"
        del m["collection_completed_at"]
        self.assertFalse(session_collection_window(m, "noon"))

    def test_deadline_enforced_before_provider_calls(self):
        beijing = ZoneInfo("Asia/Shanghai")
        with self.assertRaises(SystemExit) as late_close:
            runner._window_guard("close", datetime(2026, 10, 30, 19, 41, tzinfo=beijing))
        self.assertEqual(late_close.exception.code, 4)
        with self.assertRaises(SystemExit) as late_noon:
            runner._window_guard("noon", datetime(2026, 10, 30, 17, 8, tzinfo=beijing))
        self.assertEqual(late_noon.exception.code, 4)
        runner._window_guard("close", datetime(2026, 10, 30, 14, 40, tzinfo=beijing))
        runner._window_guard("noon", datetime(2026, 10, 30, 11, 31, tzinfo=beijing))

    def test_latest_bad_noon_is_not_used_as_prior_volume_baseline(self):
        with tempfile.TemporaryDirectory() as td:
            h = Path(td) / "data" / "history"
            h.mkdir(parents=True)
            (h / "2026-10-29_noon.json").write_text(
                json.dumps(sample("2026-10-29", "noon", "11:31:00", "11:32:00")), encoding="utf-8"
            )
            (h / "2026-10-30_noon.json").write_text(
                json.dumps(sample("2026-10-30", "noon", "17:07:00", "17:08:00")), encoding="utf-8"
            )
            with patch.object(monitor_main, "ROOT", Path(td)):
                self.assertIsNone(monitor_main._previous_snapshot("noon", "2026-11-02"))

    def test_backup_attempt_skips_only_valid_complete_existing_snapshot(self):
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        with tempfile.TemporaryDirectory() as td:
            h = Path(td) / "data" / "history"
            h.mkdir(parents=True)
            p = h / f"{today}_close.json"
            p.write_text(json.dumps(sample(today, "close", "14:40:00", "14:41:00")), encoding="utf-8")
            with patch.object(runner, "ROOT", Path(td)):
                self.assertTrue(runner._already_collected("close"))
                p.write_text(json.dumps(sample(today, "close", "19:41:00", "19:42:00")), encoding="utf-8")
                self.assertFalse(runner._already_collected("close"))
                p.write_text(json.dumps(sample(today, "close", "14:40:00", "14:41:00", status="partial")), encoding="utf-8")
                self.assertFalse(runner._already_collected("close"))


if __name__ == "__main__":
    unittest.main()
