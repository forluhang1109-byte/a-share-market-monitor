import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from a_share_monitor.providers import _tencent_indices

class IndexBatchTests(unittest.TestCase):
    def test_complete_batch_and_timeout(self):
        wanted = {'000001': '上证', '399001': '深成', '399006': '创业板', '000688': '科创50'}
        records = []
        for code in wanted:
            fields = [''] * 33
            fields[2], fields[3], fields[30], fields[32] = code, '100', '20261102144000', '1.2'
            records.append('v_x="' + '~'.join(fields) + '";')
        response = Mock(text='\n'.join(records))
        with patch('requests.get', return_value=response) as get:
            rows = _tencent_indices(wanted)
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]['pct'], 1.2)
        self.assertEqual(get.call_args.kwargs['timeout'], (3, 8))
        response.text = records[0]
        with patch('requests.get', return_value=response), self.assertRaises(RuntimeError):
            _tencent_indices(wanted)
