import unittest
from unittest.mock import Mock, patch

import tests.OkTestCase as ok_case
from tests.OkTestCase import _release_failed_setup, _wait_for_ocr_init


class OcrInitWaitTest(unittest.TestCase):
    def test_waits_for_default_ocr_thread(self):
        thread = Mock(is_alive=Mock(return_value=False))
        executor = Mock(_ocr_init_thread=thread)

        _wait_for_ocr_init(executor)

        thread.join.assert_called_once_with(timeout=60)

    def test_ignores_missing_ocr_thread(self):
        _wait_for_ocr_init(Mock(_ocr_init_thread=None))

    def test_failed_setup_releases_shared_ok_instance_and_pending_count(self):
        original_pending = ok_case._pending
        ok_case._pending = 1
        failed_class = Mock(_setup_complete=False)
        try:
            with patch.object(ok_case.ok_test, "destroy_ok") as destroy_ok:
                _release_failed_setup(failed_class)
            destroy_ok.assert_called_once_with()
            self.assertEqual(ok_case._pending, 0)
        finally:
            ok_case._pending = original_pending


if __name__ == "__main__":
    unittest.main(verbosity=2)
