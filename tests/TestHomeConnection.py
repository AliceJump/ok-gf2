"""断线弹窗后方可见主页，不代表当前会话仍可继续执行日常。"""

import re
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from src.core.exceptions import SessionStopException
from src.tasks.DailyTaskRunner import DailyTaskRunner
from tests.TestActivityNavigation import method
from tests.TestDailyRecovery import Task


class HomeConnectionTest(unittest.TestCase):
    def home_screen(self, dialog="", markers=None):
        """保留主页背景标识，并独立控制中央连接提示的可见性。"""
        check = method("src/core/BaseGfTask.py", "is_main")
        check.__globals__["fL"] = SimpleNamespace(dog_icon="dog", message_icon="message")
        check.__globals__["SessionStopException"] = SessionStopException
        task = Mock()
        task.find_one.return_value = None
        markers = tuple(markers or ("整备室", "活动层", "招募"))

        def read(*, match, **kwargs):
            """将主页导航和中央断线提示作为不同识别结果。"""
            if isinstance(match, list):
                return [SimpleNamespace(name=name) for name in markers]
            if isinstance(match, re.Pattern) and match.search(dialog):
                return [SimpleNamespace(name=dialog)]
            return []

        task.ocr.side_effect = read
        task.is_main = lambda **kwargs: check(task, **kwargs)
        task.wait_until.side_effect = lambda predicate, **kwargs: predicate()
        return task

    def test_disconnect_overlay_is_not_a_usable_home(self):
        """重连失败覆盖主页时中止，不点击背景入口或返回键。"""
        task = self.home_screen("重连失败，即将返回登录界面")
        ensure_main = method("src/core/BaseGfTask.py", "ensure_main")
        with self.assertRaisesRegex(SessionStopException, "重连失败"):
            ensure_main(task)
        task.click.assert_not_called()
        task.back.assert_not_called()

    def test_disconnect_overlay_is_detected_without_two_home_markers(self):
        """主页标识不足两个时，断线提示仍立即中止。"""
        task = self.home_screen("重连失败，即将返回登录界面", markers=("整备室",))
        ensure_main = method("src/core/BaseGfTask.py", "ensure_main")
        with self.assertRaisesRegex(SessionStopException, "重连失败"):
            ensure_main(task)
        task.click.assert_not_called()
        task.back.assert_not_called()

    def test_normal_home_is_still_accepted(self):
        """没有断线提示的主页继续通过识别。"""
        self.assertTrue(self.home_screen().is_main())

    def test_disconnect_before_task_preserves_unprocessed_items_and_stops_later_tasks(self):
        """任务前断线保留当前及后续未处理项，并停止后续执行。"""
        screen = self.home_screen("重连失败，即将返回登录界面")
        ensure_main = method("src/core/BaseGfTask.py", "ensure_main")
        task = Task()
        task.config = {"班组": True, "领任务": True}
        task.ensure_main = lambda **kwargs: ensure_main(screen, **kwargs)
        guild, rewards = Mock(), Mock()
        runner = DailyTaskRunner(task, [("班组", guild), ("领任务", rewards)])

        with self.assertRaisesRegex(SessionStopException, "重连失败"):
            runner.run()

        summary = runner.final_summary["per_round"][0]
        self.assertEqual([], summary["failed"])
        self.assertEqual(["班组", "领任务"], summary["all"])
        self.assertEqual(2, len(summary["all"]))
        self.assertEqual([], runner.final_summary["all_fail_tasks"])
        self.assertNotIn("班组", runner.failure_details.get("", {}))
        self.assertIn("重连失败", runner.final_summary["exception"])
        guild.assert_not_called()
        rewards.assert_not_called()


if __name__ == "__main__":
    unittest.main()
