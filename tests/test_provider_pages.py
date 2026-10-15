import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from a_share_monitor.providers import _tencent_parallel_frame


class Response:
    def __init__(self, offset, duplicate=False):
        self.offset, self.duplicate = offset, duplicate
    def raise_for_status(self):
        pass
    def json(self):
        return {'data': {'total': 1200, 'rank_list': [{'code': str(i if not self.duplicate else 1)}
                for i in range(self.offset, self.offset+200)]}}


class PageTests(unittest.TestCase):
    def test_pages_are_complete_and_requests_have_timeouts(self):
        def get(url, params, timeout):
            self.assertEqual(timeout, (3, 8))
            return Response(int(params['offset']))
        with patch('requests.get', side_effect=get) as get_mock:
            self.assertEqual(len(_tencent_parallel_frame()), 1200)
            self.assertEqual(get_mock.call_count, 6)

    def test_duplicate_pages_cannot_pass_as_full_market(self):
        with patch('requests.get', side_effect=lambda url, params, timeout: Response(0, True)):
            with self.assertRaisesRegex(ValueError, 'Incomplete'):
                _tencent_parallel_frame()


if __name__ == '__main__':
    unittest.main()
