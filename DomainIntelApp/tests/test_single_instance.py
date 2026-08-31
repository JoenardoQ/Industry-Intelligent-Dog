from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from runtime.single_instance import SingleInstanceLock
except ModuleNotFoundError:
    SingleInstanceLock = None


class SingleInstanceTests(unittest.TestCase):
    def test_second_process_lock_is_rejected_until_first_releases(self):
        self.assertIsNotNone(SingleInstanceLock, "single-instance lock is not implemented")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "intdog.lock"
            first = SingleInstanceLock(path)
            second = SingleInstanceLock(path)
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            first.release()
            self.assertTrue(second.acquire())
            second.release()


if __name__ == "__main__":
    unittest.main()
