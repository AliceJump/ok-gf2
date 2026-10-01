# Test case
import unittest

from src.config import config
from ok.gui.common.config import Language
from tests.OkTestCase import OkTestCase
from src.tasks.DailyTask import DailyTask


class TestBattleBaseSerialization(OkTestCase):
    task_class = DailyTask
    lang = Language.ENGLISH
    config = config

    def test_paiqian(self):
        # Create a BattleReport object
        self.set_image('tests/images/english_date_regex.png')
        dates = self.task.find_activities()
        self.assertEqual(len(dates), 1)

    def test_main(self):
        # Create a BattleReport object
        self.set_image('tests/images/english_main.png')
        main = self.task.is_main()
        self.assertTrue(main)

        self.set_image('tests/images/english_main2.png')
        main = self.task.is_main()
        self.assertTrue(main)


if __name__ == '__main__':
    unittest.main()
