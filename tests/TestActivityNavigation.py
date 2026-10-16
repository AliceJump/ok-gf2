import ast
import re
import unittest
from pathlib import Path
from unittest.mock import Mock


def method(path, name):
    """Model method."""
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    ns = {"re": re}
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), ns)
    return ns[name]


class ActivityNavigationTest(unittest.TestCase):
    def test_layer_check_has_one_explicit_timeout_and_checks_full_hud(self):
        """Verify layer check has one explicit timeout and checks full hud."""
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
        """Verify failed layer entry finishes without running food or rewards."""
        run = method("src/tasks/daily/daily_activity_mixin.py", "free_time_layer")
        task = Mock()
        task._enter_free_time_layer.return_value = False
        task.is_free_layer.return_value = False
        self.assertFalse(run(task))
        task.do_food_flow.assert_not_called()
        task.water_flowers.assert_not_called()
        task._ensure_activity_panel.assert_not_called()
        self.assertEqual(3, task.ensure_main.call_count)

    def test_failed_entry_recovers_home_and_continues_later_layer_steps(self):
        """单步进入失败后恢复主页，后续喝水、吃饭或浇花仍独立尝试。"""
        run = method("src/tasks/daily/daily_activity_mixin.py", "free_time_layer")
        cases = [
            ([False, True, True], ["enter", "home", "enter", "美味烹调", "home", "enter", "water", "home"]),
            ([True, False, True], ["enter", "茶歇一刻", "home", "enter", "home", "enter", "water", "home"]),
            ([False, False, True], ["enter", "home", "enter", "home", "enter", "water", "home"]),
            ([True, True, False], ["enter", "茶歇一刻", "home", "enter", "美味烹调", "home", "enter", "home"]),
        ]
        for entries, expected in cases:
            with self.subTest(entries=entries):
                task = Mock()
                task.config = {"活动层浇花": True}
                task.is_free_layer.return_value = True
                outcomes = iter(entries)
                events = []
                task._enter_free_time_layer.side_effect = lambda: events.append("enter") or next(outcomes)
                task.ensure_main.side_effect = lambda **kw: events.append("home")
                task.do_food_flow.side_effect = lambda **kw: events.append(kw["entry_match"].pattern) or True
                task.water_flowers.side_effect = lambda: events.append("water") or True

                self.assertIs(False, run(task))
                self.assertEqual(expected, events)

    def test_failed_home_recovery_stops_before_attempting_another_step(self):
        """恢复主页失败必须向上传播，不能在未知页面继续点击。"""
        run = method("src/tasks/daily/daily_activity_mixin.py", "free_time_layer")
        task = Mock()
        task._enter_free_time_layer.return_value = False
        task.ensure_main.side_effect = RuntimeError("home recovery failed")
        with self.assertRaisesRegex(RuntimeError, "home recovery failed"):
            run(task)
        task._enter_free_time_layer.assert_called_once()
        task.do_food_flow.assert_not_called()
        task.water_flowers.assert_not_called()

    def test_lost_layer_hud_skips_food_but_still_attempts_later_steps(self):
        """入口返回成功后 HUD 再次丢失时不操作食物，但仍可恢复后继续。"""
        run = method("src/tasks/daily/daily_activity_mixin.py", "free_time_layer")
        task = Mock()
        task.config = {"活动层浇花": True}
        task._enter_free_time_layer.return_value = True
        task.is_free_layer.side_effect = [False, True, True]
        task.do_food_flow.return_value = True
        task.water_flowers.return_value = True

        self.assertIs(False, run(task))
        task.do_food_flow.assert_called_once()
        self.assertEqual("美味烹调", task.do_food_flow.call_args.kwargs["entry_match"].pattern)
        task.water_flowers.assert_called_once()
        self.assertEqual(3, task.ensure_main.call_count)

    def test_entry_retries_click_only_until_hud_is_confirmed(self):
        """Verify entry retries click only until hud is confirmed."""
        enter = method("src/tasks/daily/daily_activity_mixin.py", "_enter_free_time_layer")
        task = Mock()
        task.is_free_layer.side_effect = [False, True]
        task.ocr.return_value = [object(), object()]
        self.assertTrue(enter(task))
        self.assertEqual(2, task.wait_click_ocr.call_count)

    def test_entry_failure_is_bounded_and_screenshotted(self):
        """Verify entry failure is bounded and screenshotted."""
        enter = method("src/tasks/daily/daily_activity_mixin.py", "_enter_free_time_layer")
        task = Mock()
        task.is_free_layer.return_value = False
        task.ocr.return_value = [object(), object()]
        self.assertFalse(enter(task))
        self.assertEqual(3, task.wait_click_ocr.call_count)
        task.screenshot.assert_called_once()

    def test_entry_retries_when_only_activity_and_public_home_markers_are_readable(self):
        """Verify entry retries when only activity and public home markers are readable."""
        enter = method("src/tasks/daily/daily_activity_mixin.py", "_enter_free_time_layer")
        task = Mock()
        task.is_free_layer.side_effect = [False, False, True]
        visible_labels = ["活动层", "公共区"]
        task.ocr.side_effect = lambda **kw: [label for label in visible_labels if label in kw["match"]]
        self.assertTrue(enter(task))
        self.assertEqual(3, task.wait_click_ocr.call_count)
        task.screenshot.assert_not_called()

    def test_failed_activity_entry_does_not_prevent_guild_task(self):
        """Verify failed activity entry does not prevent guild task."""
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
