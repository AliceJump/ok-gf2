"""Run installed daily orchestration with an injected supply failure."""

import unittest
from types import SimpleNamespace

from ok.task.exceptions import CaptureException, FinishedException, HotkeyConfigException, TaskDisabledException

from src.core.BaseGfTask import BaseGfTask
from src.tasks.daily.daily_activity_mixin import DailyActivityMixin
from src.tasks.DailyTaskRunner import DailyTaskRunner
from tests.TestFoodFlow import FoodScreen


class Task:
    def __init__(self):
        self.config = {"情报和战前补给": True, "活动自律": True, "领任务": True}
        self.events = []
        self.info = {}
        self.screenshot_error = None
        self.home_calls = 0

    def tr(self, value):
        return value

    def log_info(self, message, **kwargs):
        self.events.append(("log", message))

    log_warning = log_info
    log_error = log_info

    def info_set(self, key, value):
        self.info[key] = value

    def ensure_main(self, **kwargs):
        self.home_calls += 1
        self.events.append(("home", self.home_calls))

    def screenshot(self, name):
        self.events.append(("screenshot", name))
        if self.screenshot_error:
            raise self.screenshot_error


class DailyRecoveryTest(unittest.TestCase):
    def test_meal_result_left_by_failed_item_recovers_home_before_next_item(self):
        """真实主页恢复须关闭用餐结果页，再允许下一项执行。"""

        class MealRecoveryTask(Task, FoodScreen):
            ensure_main = BaseGfTask.ensure_main
            is_main = BaseGfTask.is_main

            def __init__(self):
                Task.__init__(self)
                FoodScreen.__init__(self)
                self.config = {"活动层": True, "领任务": True}
                self.state = "home"
                self.box.center = "center"
                self.box.top = "top"
                self.find_one = lambda *args, **kwargs: None
                self.find_feature = lambda **kwargs: None
                self.next_frame = lambda: None

            def visible(self):
                if self.state == "home":
                    return ["整备室", "公共区", "活动层", "招募"]
                if self.state == "exit":
                    return ["是否离开活动层", "确认"]
                return super().visible()

            def back(self, **kwargs):
                if self.state == "finished":
                    self.state = "exit"

            def wait_click_ocr(self, **kwargs):
                if self.state == "exit" and kwargs["match"] == "确认":
                    self.state = "home"
                    return True
                return super().wait_click_ocr(**kwargs)

        for raises in (False, True):
            with self.subTest(raises=raises):
                task = MealRecoveryTask()
                calls = []

                def meal(task=task, raises=raises):
                    task.state = "result"
                    task.result_clicks_dropped = 1
                    if raises:
                        raise RuntimeError("用餐确认未关闭")
                    return False

                def rewards(task=task, calls=calls):
                    self.assertEqual("home", task.state)
                    calls.append("领任务")
                    return True

                runner = DailyTaskRunner(task, [("活动层", meal), ("领任务", rewards)])
                runner.run()
                self.assertEqual(["领任务"], calls)
                self.assertEqual(["活动层"], runner.final_summary["per_round"][0]["failed"])
                self.assertEqual(["领任务"], runner.final_summary["per_round"][0]["success"])

    def make_runner(self, error=None):
        self.task = Task()
        self.calls = []

        def supply():
            self.calls.append("supply")
            if error:
                raise error
            return False

        def activity():
            self.calls.append("activity")
            return True

        def rewards():
            self.calls.append("rewards")
            return True

        return DailyTaskRunner(self.task, [("情报和战前补给", supply), ("活动自律", activity), ("领任务", rewards)])

    def test_supply_exception_continues_and_preserves_failure_summary(self):
        runner = self.make_runner(RuntimeError("补给列表滚动失败：游戏未进入前台"))
        try:
            runner.run()
        except RuntimeError as error:
            self.fail(f"Item error aborted later daily tasks: {error}")
        self.assertEqual(self.calls, ["supply", "activity", "rewards"])
        self.assertEqual(self.task.home_calls, 3)
        self.assertEqual(runner.final_summary["status"], "部分失败")
        summary = runner.final_summary["per_round"][0]
        self.assertEqual(summary["failed"], ["情报和战前补给"])
        self.assertEqual(summary["success"], ["活动自律", "领任务"])
        self.assertEqual(summary["all"], [])
        self.assertIn("游戏未进入前台", runner.failure_details[""]["情报和战前补给"])

    def test_false_result_keeps_existing_continuation(self):
        runner = self.make_runner()
        runner.run()
        self.assertEqual(self.calls, ["supply", "activity", "rewards"])
        self.assertEqual(runner.final_summary["status"], "部分失败")

    def test_real_supply_flow_recovers_home_and_continues_after_wheel_failure(self):
        runner = self.make_runner()

        class SupplyTask(Task, DailyActivityMixin):
            box = SimpleNamespace(_activities=None)

            def wait_click_ocr(self, **kwargs):
                return True

            def _ensure_supply_menu(self):
                return True

            def _open_supply_activity(self, name):
                raise RuntimeError("wheel delivery failed")

        self.task = SupplyTask()
        runner.task = self.task
        runner.task_items[0] = ("情报和战前补给", self.task.activities)
        runner.run()
        self.assertEqual(self.calls, ["activity", "rewards"])
        self.assertEqual(self.task.home_calls, 4)
        self.assertEqual(runner.final_summary["status"], "部分失败")
        self.assertIn("wheel delivery failed", runner.failure_details[""]["情报和战前补给"])

    def test_later_item_failure_keeps_remaining_items_and_round_summaries(self):
        runner = self.make_runner(ValueError("bad item"))
        runner.run(repeat_times=2)
        self.assertEqual(self.calls, ["supply", "activity", "rewards"] * 2)
        self.assertEqual(len(runner.final_summary["per_round"]), 2)
        self.assertEqual(runner.final_summary["actual_repeat_total"], 2)
        self.assertEqual(runner.final_summary["all_fail_tasks"], [(1, ["情报和战前补给"]), (2, ["情报和战前补给"])])

    def test_failure_screenshot_error_does_not_abort_later_tasks(self):
        runner = self.make_runner(RuntimeError("wheel failed"))
        self.task.screenshot_error = OSError("screenshot file unavailable")
        try:
            runner.run()
        except Exception as error:
            self.fail(f"Failure screenshot aborted later daily tasks: {error}")
        self.assertEqual(self.calls, ["supply", "activity", "rewards"])
        self.assertEqual(runner.final_summary["status"], "部分失败")

    def test_control_and_device_errors_still_stop(self):
        for error in (
            TaskDisabledException(),
            FinishedException(),
            CaptureException("capture lost"),
            HotkeyConfigException("bad"),
        ):
            with self.subTest(error=type(error).__name__):
                runner = self.make_runner(error)
                with self.assertRaises(type(error)):
                    runner.run()
                self.assertEqual(self.calls, ["supply"])

    def test_explicit_home_item_failure_stops_later_tasks(self):
        runner = self.make_runner()

        def home_item():
            raise RuntimeError("explicit home failed")

        runner.task_items.insert(0, ("ensure_main", home_item))
        with self.assertRaisesRegex(RuntimeError, "explicit home failed"):
            runner.run()
        self.assertEqual(self.calls, [])

    def test_failed_home_recovery_does_not_run_next_task_on_wrong_screen(self):
        runner = self.make_runner(RuntimeError("wheel failed"))
        home = self.task.ensure_main

        def ensure_home(**kwargs):
            if self.task.home_calls:
                raise RuntimeError("home recovery failed")
            home(**kwargs)

        self.task.ensure_main = ensure_home
        with self.assertRaisesRegex(RuntimeError, "home recovery failed"):
            runner.run()
        self.assertEqual(self.calls, ["supply"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
