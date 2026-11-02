import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
import a_share_monitor.main as monitor
import run_snapshot as runner
from check_snapshot import check


class RuntimeSafetyTests(unittest.TestCase):
    def test_diagnostic_never_persists_official_output(self):
        with tempfile.TemporaryDirectory() as td, patch.object(runner, 'ROOT', Path(td)), patch.object(runner, 'run', return_value={'meta': {'status': 'ok'}}) as run, patch.object(sys, 'argv', ['run_snapshot', '--session', 'close', '--skip-wait']):
            runner.main()
            run.assert_called_once_with('close', require_window=False, persist=False)
            self.assertTrue((Path(td) / 'diagnostics/latest_close.json').exists())
            self.assertFalse((Path(td) / 'data').exists())

    def test_missing_core_fails_cli(self):
        with tempfile.TemporaryDirectory() as td, patch.object(runner, 'ROOT', Path(td)), patch.object(runner, 'run', return_value={'meta': {'status': 'core_data_missing'}}), patch.object(sys, 'argv', ['run_snapshot', '--session', 'close', '--skip-wait']), self.assertRaises(SystemExit) as result:
            runner.main()
        self.assertEqual(result.exception.code, 2)

    def test_non_trading_day_does_not_replace_latest(self):
        with patch.object(monitor, 'is_trading_day', return_value=(False, 'exchange_calendars:XSHG')), patch.object(monitor, '_write_outputs') as write:
            self.assertEqual(monitor.run()['meta']['status'], 'skipped_non_trading_day')
            write.assert_not_called()

    def test_missing_previous_exchange_session_cannot_use_older_file(self):
        with tempfile.TemporaryDirectory() as td, patch.object(monitor, 'ROOT', Path(td)):
            h = Path(td) / 'data/history'
            h.mkdir(parents=True)
            (h / '2026-10-29_close.json').write_text(json.dumps({'meta': {
                'date': '2026-10-29', 'is_trading_day': True, 'status': 'ok',
                'collection_started_at': '2026-10-29T14:40:00+08:00',
                'collection_completed_at': '2026-10-29T14:41:00+08:00',
                'source_status': {'a_share_spot': {'ok': True}},
            }}))
            self.assertIsNone(monitor._previous_snapshot('close', '2026-11-02'))

    def test_consumer_rechecks_date_and_delivery_time(self):
        m = {'date': '2026-11-02', 'session': 'close', 'status': 'partial', 'is_trading_day': True,
             'calendar_source': 'exchange_calendars:XSHG', 'delivery_eligible': True,
             'collection_started_at': '2026-11-02T14:40:00+08:00',
             'collection_completed_at': '2026-11-02T14:41:00+08:00',
             'source_status': {k: {'ok': True} for k in ('a_share_spot', 'indices')}}
        self.assertTrue(check({'meta': m}, 'close', datetime.fromisoformat('2026-11-02T14:42:00+08:00'), True)[0])
        self.assertFalse(check({'meta': m}, 'close', datetime.fromisoformat('2026-11-02T16:00:00+08:00'), True)[0])
        self.assertFalse(check({'meta': m}, 'close', datetime.fromisoformat('2026-11-03T14:42:00+08:00'))[0])


if __name__ == '__main__':
    unittest.main()
