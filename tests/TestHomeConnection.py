"""断线弹窗后方可见主页，不代表当前会话仍可继续执行日常。"""

import re
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from src.tasks.DailyTaskRunner import DailyTaskRunner
from tests.TestActivityNavigation import method
from tests.TestDailyRecovery import Task


class HomeConnectionTest(unittest.TestCase):
    def home_screen(self, dialog=""):
        """保留主页背景标识，并独立控制中央连接提示的可见性。"""
        check = method("src/core/BaseGfTask.py", "is_main")
        check.__globals__["fL"] = SimpleNamespace(dog_icon="dog", message_icon="message")
        task = Mock()
        task.find_one.return_value = None

        def read(*, match, **kwargs):
            """将主页导航和中央断线提示作为不同识别结果。"""
            if isinstance(match, list):
                return [SimpleNamespace(name=name) for name in ("整备室", "活动层", "招募")]
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
        with self.assertRaisesRegex(RuntimeError, "重连失败"):
            ensure_main(task)
        task.click.assert_not_called()
        task.back.assert_not_called()

    def test_normal_home_is_still_accepted(self):
        """没有断线提示的主页继续通过识别。"""
        self.assertTrue(self.home_screen().is_main())

    def test_disconnect_before_task_is_counted_as_failure_and_stops_later_tasks(self):
        """任务前断线仍计入失败及总数，后续任务保持未处理且不执行。"""
        screen = self.home_screen("重连失败，即将返回登录界面")
        ensure_main = method("src/core/BaseGfTask.py", "ensure_main")
        task = Task()
        task.config = {"班组": True, "领任务": True}
        task.ensure_main = lambda **kwargs: ensure_main(screen, **kwargs)
        guild, rewards = Mock(), Mock()
        runner = DailyTaskRunner(task, [("班组", guild), ("领任务", rewards)])

        with self.assertRaisesRegex(RuntimeError, "重连失败"):
            runner.run()

        summary = runner.final_summary["per_round"][0]
        self.assertEqual(["班组"], summary["failed"])
        self.assertEqual(["领任务"], summary["all"])
        self.assertEqual(2, sum(len(summary[key]) for key in ("success", "failed", "uncertain", "skipped", "all")))
        self.assertEqual([(1, ["班组"])], runner.final_summary["all_fail_tasks"])
        self.assertIn("重连失败", runner.failure_details[""]["班组"])
        guild.assert_not_called()
        rewards.assert_not_called()


if __name__ == "__main__":
    unittest.main()
