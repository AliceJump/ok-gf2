# Test case
import time
import unittest

from src.config import config
from tests.OkTestCase import OkTestCase
from src.core.BaseGfTask import BaseGfTask


class TestBattleBaseSerialization(OkTestCase):
    task_class = BaseGfTask

    config = config

    def test_paiqian(self):
        # Create a BattleReport object
        self.set_image('tests/images/paiqian.png')
        start = time.time()
        count = 1
        for i in range(count):
            paiqian = self.task.ocr(match=['再次派遣'], box='bottom', log=True)
            self.assertEqual(paiqian[0].name, "再次派遣")
        self.task.log_info(f'ocr_mean_time {(time.time() - start) / count}')


if __name__ == '__main__':
    unittest.main()
