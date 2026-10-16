import ast
import unittest
from pathlib import Path
from unittest.mock import Mock


def method(path, name):
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    ns = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), ns)
    return ns[name]


class ActivityNavigationTest(unittest.TestCase):
    def test_layer_check_has_one_explicit_timeout_and_checks_full_hud(self):
        check = method("src/core/BaseGfTask.py", "is_free_layer")
        task = Mock()
        task.box.top = "top"
        task.ocr.return_value = [object()] * 4
        task.wait_until.side_effect = lambda predicate, **kw: predicate()
        self.assertFalse(check(task, time_out=1))
        task.wait_ocr.assert_not_called()
        task.wait_until.assert_called_once()
        self.assertEqual(1, task.wait_until.call_args.kwargs["time_out"])
        task.ocr.return_value = [object()] * 5
        self.assertTrue(check(task, time_out=1))

    def test_failed_layer_entry_finishes_without_running_food_or_rewards(self):
        run = method("src/tasks/daily/daily_activity_mixin.py", "free_time_layer")
        task = Mock()
        task._enter_free_time_layer.return_value = False
        task.is_free_layer.return_value = False
        self.assertFalse(run(task))
        task.do_food_flow.assert_not_called()
        task.water_flowers.assert_not_called()
        task._ensure_activity_panel.assert_not_called()
        task.ensure_main.assert_called_once()

    def test_entry_retries_click_only_until_hud_is_confirmed(self):
        enter = method("src/tasks/daily/daily_activity_mixin.py", "_enter_free_time_layer")
        task = Mock()
        task.is_free_layer.side_effect = [False, True]
        task.ocr.return_value = [object(), object()]
        self.assertTrue(enter(task))
        self.assertEqual(2, task.wait_click_ocr.call_count)

    def test_entry_failure_is_bounded_and_screenshotted(self):
        enter = method("src/tasks/daily/daily_activity_mixin.py", "_enter_free_time_layer")
        task = Mock()
        task.is_free_layer.return_value = False
        task.ocr.return_value = [object(), object()]
        self.assertFalse(enter(task))
        self.assertEqual(3, task.wait_click_ocr.call_count)
        task.screenshot.assert_called_once()

    def test_entry_retries_when_only_activity_and_public_home_markers_are_readable(self):
        enter = method("src/tasks/daily/daily_activity_mixin.py", "_enter_free_time_layer")
        task = Mock()
        task.is_free_layer.side_effect = [False, False, True]
        visible_labels = ["活动层", "公共区"]
        task.ocr.side_effect = lambda **kw: [label for label in visible_labels if label in kw["match"]]
        self.assertTrue(enter(task))
        self.assertEqual(3, task.wait_click_ocr.call_count)
        task.screenshot.assert_not_called()

    def test_failed_activity_entry_does_not_prevent_guild_task(self):
        from src.tasks.DailyTaskRunner import DailyTaskRunner
        from tests.TestDailyTaskRunner import StubTask

        run = method("src/tasks/daily/daily_activity_mixin.py", "free_time_layer")
        task = Mock()
        task._enter_free_time_layer.return_value = False
        daily = StubTask({"活动层": True, "班组": True})
        guild = Mock(return_value=True)
        runner = DailyTaskRunner(daily, [("活动层", lambda: run(task)), ("班组", guild)])
        runner.run()
        self.assertEqual(["活动层"], runner.task_status["failed"])
        guild.assert_called_once()
