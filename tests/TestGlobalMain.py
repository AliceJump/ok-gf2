import importlib
import re
import unittest

from ok.gui.common.config import Language
from ok.test.TaskTestCase import TaskTestCase
from src.config import config

# src/global/ cannot be imported statically because `global` is a Python keyword, so the class is
# resolved the same way the framework resolves it - by name, through importlib.
GlobalDailyTask = importlib.import_module('src.global.GlobalDailyTask').GlobalDailyTask


class TestGlobalMain(TaskTestCase):
    task_class = GlobalDailyTask
    lang = Language.ENGLISH
    config = config

    def test_is_main_on_english_home_screen(self):
        """The Global home screen should be recognised from its English labels plus the two home-only icons."""
        self.set_image('tests/images/english_main.png')
        self.assertTrue(self.task.is_main())

        self.set_image('tests/images/english_main2.png')
        self.assertTrue(self.task.is_main())

    def test_ocr_text_is_not_translated_to_chinese(self):
        """Global tasks must see English.

        `Recruitment` has an entry in `i18n/en_US/LC_MESSAGES/ocr.po` mapping it onto the Chinese literal the CN tasks expect. A Global task overrides
        `fix_texts`, so it should read the English straight off the screen instead.
        """
        self.set_image('tests/images/english_main.png')
        boxes = self.task.ocr(box='right')
        names = [b.name for b in boxes]
        self.assertTrue(any(re.search('Recruitment', n, re.I) for n in names), f'expected English text, got {names}')
        self.assertFalse(any('招募' in n for n in names), f'text was translated into Chinese: {names}')


if __name__ == '__main__':
    unittest.main()
