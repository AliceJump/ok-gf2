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


class TestMenuLabelFilter(unittest.TestCase):
    """Guards the home-screen check against text that merely mentions the menu entries.

    Every string here came out of a real run's OCR, not from imagination.
    """

    def test_real_menu_entries_are_kept(self):
        base = importlib.import_module('src.global.BaseGlobalTask')
        for name in ('Campaign', 'Refitting', 'Room', 'Refitting Room', 'Crew Deck', 'Recruitment', 'Shop', 'Public Area'):
            self.assertTrue(base.is_menu_label(name), f'{name!r} is a real home-screen entry and must count')

    def test_loading_screen_prose_is_rejected(self):
        """A loading screen describing the ship once satisfied the home check and stopped the bot early."""
        base = importlib.import_module('src.global.BaseGlobalTask')
        for name in ('gine Room, Refitting Room,', 'a Crew Deck, Lounge and other', 'Do you wish to leave the Crew Deck?'):
            self.assertFalse(base.is_menu_label(name), f'{name!r} is prose, not a menu entry')


class TestGlobalFlowWiring(unittest.TestCase):
    """Static checks on the flow tables. No game, no OCR - these guard the wiring only."""

    def test_every_flow_names_a_real_method(self):
        """A typo in a FLOWS method name would only surface when that flow ran, so check it here."""
        for module_name, class_name in (('GlobalDailyTask', 'GlobalDailyTask'), ('GlobalWeeklyTask', 'GlobalWeeklyTask')):
            module = importlib.import_module(f'src.global.{module_name}')
            task_class = getattr(module, class_name)
            for key, method, description in module.FLOWS:
                self.assertTrue(hasattr(task_class, method), f'{class_name}.{method} is missing, referenced by {key!r}')
                self.assertTrue(description.strip(), f'{key!r} has no settings description')

    def test_single_flow_tasks_cover_every_flow(self):
        """Every composed flow should be individually runnable, so a new flow is not left unverifiable."""
        verify = importlib.import_module('src.global.VerifyTasks')
        daily = importlib.import_module('src.global.GlobalDailyTask')
        weekly = importlib.import_module('src.global.GlobalWeeklyTask')

        wrapped = {task_class.flow for task_class in vars(verify).values()
                   if isinstance(task_class, type) and getattr(task_class, 'flow', None)}
        for _, method, _ in daily.FLOWS + weekly.FLOWS:
            self.assertIn(method, wrapped, f'{method} has no single-flow task in VerifyTasks')

    def test_single_flow_tasks_are_registered(self):
        """A task that is not in the task list never appears as a button."""
        import src.region as region

        registered = {class_name for module_path, class_name in region.GLOBAL_TASKS if 'VerifyTasks' in module_path}
        verify = importlib.import_module('src.global.VerifyTasks')
        expected = {name for name, value in vars(verify).items()
                    if isinstance(value, type) and getattr(value, 'flow', None) and not name.startswith('_')}
        self.assertEqual(expected, registered)


if __name__ == '__main__':
    unittest.main()
