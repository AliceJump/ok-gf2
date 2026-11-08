"""班组入口点击与实际切页分别建模，不让主页文字冒充班组内容。"""

import unittest
from types import SimpleNamespace

from src.tasks.DailyTaskRunner import DailyTaskRunner
from tests.TestChenyanEntry import ChenyanDevice


class GuildScreen(ChenyanDevice):
    def __init__(
        self,
        dropped=0,
        unknown=False,
        entry_misses=0,
        confirmation_misses=0,
        duty_click_drops=0,
        already_completed=False,
    ):
        """分别模拟入口丢失点击和进入未知页面。"""
        super().__init__(ready=False, opens_in="6天21小时后开启")
        self.config["班组"] = True
        self.page = "home"
        self.dropped = dropped
        self.unknown = unknown
        self.entry_misses = entry_misses
        self.entry_reads = 0
        self.confirmation_misses = confirmation_misses
        self.confirmation_reads = 0
        self.duty_click_drops = duty_click_drops
        self.already_completed = already_completed
        self.duty_page_ready = False
        self.entry_clicks = 0
        self.duty_clicks = 0

    def wait_ocr(self, *args, match=None, **kwargs):
        """主页与班组页只返回各自可见的导航文字。"""
        if match == ["班组"]:
            self.entry_reads += 1
            if self.entry_reads <= self.entry_misses:
                return []
            return [SimpleNamespace(name="班组")] if self.page == "home" else []
        if match == ["要务"]:
            return [SimpleNamespace(name="要务")] if self.page == "guild" else []
        if isinstance(match, list) and "每日要务已完成" in match:
            self.confirmation_reads += 1
            if self.page != "guild" or not self.duty_page_ready or self.confirmation_reads <= self.confirmation_misses:
                return []
            return [SimpleNamespace(name="每日要务已完成")]
        return super().wait_ocr(*args, match=match, **kwargs)

    def click_box_by_match_position(self, *args, **kwargs):
        """记录入口交互，仅在点击未丢失时推进页面。"""
        self.entry_clicks += 1
        if self.unknown:
            self.page = "unknown"
        elif self.entry_clicks > self.dropped:
            self.page = "guild"
            self.duty_page_ready = self.already_completed

    def wait_click_ocr(self, *args, match=None, **kwargs):
        """只有实际进入班组页才允许点击要务。"""
        if match == ["要务"]:
            if self.page != "guild":
                return False
            self.duty_clicks += 1
            if self.duty_clicks > self.duty_click_drops:
                self.duty_page_ready = True
        return super().wait_click_ocr(*args, match=match, **kwargs)

    def run_guild(self):
        """通过真实编排器执行班组并返回任务统计。"""
        self.daily_runner = DailyTaskRunner(self, [("班组", self.guild)])
        self.daily_runner.run()
        return self.daily_runner.task_status


class GuildEntryTest(unittest.TestCase):
    def test_duty_page_confirmation_is_retried_after_dropped_click(self):
        """要务点击未生效时，继续在班组页有界重试。"""
        task = GuildScreen(duty_click_drops=1)
        self.assertEqual(["班组"], task.run_guild()["success"])
        self.assertEqual(1, task.entry_clicks)
        self.assertEqual(2, task.duty_clicks)

    def test_delayed_duty_confirmation_is_reused_without_second_click(self):
        """要务页确认文字延迟出现时，不重复点击已进入的页面。"""
        task = GuildScreen(confirmation_misses=1)
        self.assertEqual(["班组"], task.run_guild()["success"])
        self.assertEqual(1, task.entry_clicks)
        self.assertEqual(1, task.duty_clicks)

    def test_completed_duty_page_skips_missing_duty_entry_text(self):
        """已完成页面没有要务入口文字时，直接复用页面确认继续后续任务。"""
        task = GuildScreen(already_completed=True)
        self.assertEqual(["班组"], task.run_guild()["success"])
        self.assertEqual(1, task.entry_clicks)
        self.assertEqual(0, task.duty_clicks)

    def test_delayed_entry_is_detected_before_clicking(self):
        """首次识别超时后继续等待，入口可见时才点击并执行要务。"""
        task = GuildScreen(entry_misses=1)
        self.assertEqual(["班组"], task.run_guild()["success"])
        self.assertEqual(2, task.entry_reads)
        self.assertEqual(1, task.entry_clicks)
        self.assertEqual(1, task.duty_clicks)

    def test_missing_entry_detection_retries_are_bounded_without_clicks(self):
        """入口一直缺失时最多检测三次，无点击并保留明确失败原因。"""
        task = GuildScreen(entry_misses=100)
        self.assertEqual(["班组"], task.run_guild()["failed"])
        self.assertEqual(3, task.entry_reads)
        self.assertEqual(0, task.entry_clicks)
        self.assertEqual(0, task.duty_clicks)
        self.assertIn("班组入口", task.daily_runner.failure_details[""]["班组"])

    def test_dropped_entry_is_retried_before_daily_duties(self):
        """首次点击丢失后重试入口，再执行要务及补给。"""
        task = GuildScreen(dropped=1)
        self.assertEqual(["班组"], task.run_guild()["success"])
        self.assertEqual(2, task.entry_clicks)
        self.assertEqual(1, task.duty_clicks)
        self.assertIn(["补给"], task.clicked)

    def test_stuck_entry_records_specific_failure_and_recovers_home(self):
        """三次失败后保留原因及一张现场截图，并恢复主页。"""
        task = GuildScreen(dropped=100)
        self.assertEqual(["班组"], task.run_guild()["failed"])
        self.assertEqual(3, task.entry_clicks)
        self.assertEqual(0, task.duty_clicks)
        self.assertIn("班组入口", task.daily_runner.failure_details[""]["班组"])
        self.assertTrue(task.home)
        self.assertEqual(["guild_entry_failed"], task.shots)
        self.assertIn("班组", task.daily_runner.failure_screenshot_tasks)

    def test_failed_specific_screenshot_keeps_generic_fallback(self):
        """专用截图保存异常时不能误标已截图，运行器仍尝试通用截图。"""
        task = GuildScreen(dropped=100)

        def screenshot(name):
            """只让专用截图写入失败，保留通用截图的可用性。"""
            if name == "guild_entry_failed":
                raise OSError("截图写入失败")
            task.shots.append(name)

        task.screenshot = screenshot
        self.assertEqual(["班组"], task.run_guild()["failed"])
        self.assertEqual(["DailyTask_FailTask_班组"], task.shots)
        self.assertNotIn("班组", task.daily_runner.failure_screenshot_tasks)
        self.assertIn("班组入口", task.daily_runner.failure_details[""]["班组"])

    def test_unknown_page_does_not_receive_more_entry_clicks(self):
        """切入未知页后停止入口点击并将班组计为失败。"""
        task = GuildScreen(unknown=True)
        self.assertEqual(["班组"], task.run_guild()["failed"])
        self.assertEqual(1, task.entry_clicks)
        self.assertEqual(0, task.duty_clicks)


if __name__ == "__main__":
    unittest.main()
