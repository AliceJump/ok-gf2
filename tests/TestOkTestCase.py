import unittest
from unittest.mock import Mock

from tests.OkTestCase import _wait_for_ocr_init


class OcrInitWaitTest(unittest.TestCase):
    def test_waits_for_default_ocr_thread(self):
        thread = Mock(is_alive=Mock(return_value=False))
        executor = Mock(_ocr_init_thread=thread)

        _wait_for_ocr_init(executor)

        thread.join.assert_called_once_with(timeout=60)

    def test_ignores_missing_ocr_thread(self):
        _wait_for_ocr_init(Mock(_ocr_init_thread=None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
