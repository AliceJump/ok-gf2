# Test case
import unittest

from src.config import config
from ok.test.TaskTestCase import TaskTestCase
from src.core.BaseGfTask import BaseGfTask


class TestBattleBaseSerialization(TaskTestCase):
    task_class = BaseGfTask

    config = config

    def test_base(self):
        # Create a BattleReport object
        self.set_image('tests/images/main.png')
        self.task.ensure_main()


if __name__ == '__main__':
    unittest.main()
