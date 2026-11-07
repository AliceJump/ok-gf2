"""班组入口点击与实际切页分别建模，不让主页文字冒充班组内容。"""

import unittest
from types import SimpleNamespace

from src.tasks.DailyTaskRunner import DailyTaskRunner
from tests.TestChenyanEntry import ChenyanDevice


class GuildScreen(ChenyanDevice):
    def __init__(self, dropped=0, unknown=False):
        super().__init__(ready=False, opens_in="6天21小时后开启")
        self.config["班组"] = True
        self.page = "home"
        self.dropped = dropped
        self.unknown = unknown
        self.entry_clicks = 0
        self.duty_clicks = 0

    def wait_ocr(self, *args, match=None, **kwargs):
        if match == ["班组"]:
            return [SimpleNamespace(name="班组")] if self.page == "home" else []
        if match == ["要务"]:
            return [SimpleNamespace(name="要务")] if self.page == "guild" else []
        if isinstance(match, list) and "每日要务已完成" in match and self.page != "guild":
            raise TimeoutError("主页上没有每日要务")
        return super().wait_ocr(*args, match=match, **kwargs)

    def click_box_by_match_position(self, *args, **kwargs):
        self.entry_clicks += 1
        if self.unknown:
            self.page = "unknown"
        elif self.entry_clicks > self.dropped:
            self.page = "guild"

    def wait_click_ocr(self, *args, match=None, **kwargs):
        if match == ["要务"]:
            if self.page != "guild":
                return False
            self.duty_clicks += 1
        return super().wait_click_ocr(*args, match=match, **kwargs)

    def run_guild(self):
        self.daily_runner = DailyTaskRunner(self, [("班组", self.guild)])
        self.daily_runner.run()
        return self.daily_runner.task_status


class GuildEntryTest(unittest.TestCase):
    def test_dropped_entry_is_retried_before_daily_duties(self):
        task = GuildScreen(dropped=1)
        self.assertEqual(["班组"], task.run_guild()["success"])
        self.assertEqual(2, task.entry_clicks)
        self.assertEqual(1, task.duty_clicks)
        self.assertIn(["补给"], task.clicked)

    def test_stuck_entry_records_specific_failure_and_recovers_home(self):
        task = GuildScreen(dropped=100)
        self.assertEqual(["班组"], task.run_guild()["failed"])
        self.assertEqual(3, task.entry_clicks)
        self.assertEqual(0, task.duty_clicks)
        self.assertIn("班组入口", task.daily_runner.failure_details[""]["班组"])
        self.assertTrue(task.home)
        self.assertTrue(task.shots)

    def test_unknown_page_does_not_receive_more_entry_clicks(self):
        task = GuildScreen(unknown=True)
        self.assertEqual(["班组"], task.run_guild()["failed"])
        self.assertEqual(1, task.entry_clicks)
        self.assertEqual(0, task.duty_clicks)


if __name__ == "__main__":
    unittest.main()
