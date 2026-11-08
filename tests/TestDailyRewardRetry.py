"""覆盖日志中的领奖点击未生效和已领取提示误点击。"""

import re
import unittest
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

from src.tasks.daily.daily_reward_mixin import DailyRewardMixin


class DailyRewardRetryTest(unittest.TestCase):
    def action_task(self, remaining):
        """模拟行动页按钮在若干次点击后消失。"""
        task = Mock()
        task.box_of_screen.side_effect = lambda *bounds: bounds
        task._switch_xunlu_rewards_page.return_value = True
        task._claim_xunlu_rewards.return_value = True
        task._xunlu_no_reward_status.return_value = "当前无可领取项"
        task._record_xunlu_result.side_effect = MethodType(DailyRewardMixin._record_xunlu_result, task)
        task.action_clicks = 0

        def click(**kwargs):
            pattern = kwargs["match"][0]
            if pattern.fullmatch("开启远航巡录"):
                return False
            if pattern.fullmatch("沿途行动"):
                return True
            if kwargs["box"] == (0.50, 0.50, 1, 1):
                task.action_clicks += 1
                return True
            return True

        def read(**kwargs):
            pattern = kwargs["match"][0]
            if pattern.fullmatch("一键领取"):
                return [SimpleNamespace(name="一键领取")] if task.action_clicks < remaining else []
            return [SimpleNamespace(name="每日行动")]

        task.wait_click_ocr.side_effect = click
        task.wait_ocr.side_effect = read
        return task

    def test_ignored_first_action_click_retries_before_leaving(self):
        """首次点击丢失后仍能领取并核验按钮消失。"""
        task = self.action_task(2)
        self.assertIs(True, DailyRewardMixin.xunlu(task))
        self.assertEqual(2, task.action_clicks)
        task._record_xunlu_result.assert_any_call("每日行动", True)

    def test_action_retry_is_bounded_and_preserves_failure(self):
        """按钮始终存在时三次停止，不能冒报成功。"""
        task = self.action_task(99)
        self.assertIs(False, DailyRewardMixin.xunlu(task))
        self.assertEqual(3, task.action_clicks)
        task._record_xunlu_result.assert_any_call("每日行动", False)

    def test_action_retry_stops_when_page_is_lost(self):
        """页面丢失后不继续点击领奖。"""
        task = self.action_task(99)
        task.wait_ocr.side_effect = [True, True, False]
        self.assertEqual("待核查", DailyRewardMixin.xunlu(task))
        self.assertEqual(1, task.action_clicks)

    def test_action_button_ocr_miss_without_completion_evidence_is_uncertain(self):
        """按钮漏读不能冒充到账证据，保留行动页现场。"""
        task = self.action_task(2)
        task._xunlu_no_reward_status.return_value = "待核查"
        self.assertEqual("待核查", DailyRewardMixin.xunlu(task))
        task.screenshot.assert_called_once_with("Xunlu_Uncertain_每日行动")

    def explore_task(self, label):
        """按真实 OCR 的正则搜索方式提供探索页面文字。"""
        task = Mock()
        task.wait_ocr.side_effect = lambda **kw: [SimpleNamespace(name=label)] if re.search(kw["match"], label) else []
        clicked = []

        def click(**kwargs):
            pattern = kwargs["match"]
            if isinstance(pattern, str) or re.search(pattern, "边界推进晶源采集"):
                return True
            if re.search(pattern, label):
                clicked.append(label)
                return True
            return False

        task.wait_click_ocr.side_effect = click
        return task, clicked

    def test_explore_completed_notice_is_not_clicked(self):
        """采集已领取说明不能点击，派遣仍需保留待核查。"""
        task, clicked = self.explore_task("当前难度奖励已全部领取")
        self.assertEqual("待核查", DailyRewardMixin.explore_claim(task))
        self.assertEqual([], clicked)
        task.wait_pop_up.assert_not_called()
        task.screenshot.assert_called_once_with("explore_dispatch_unconfirmed")
        task.ensure_main.assert_called_once()

    def test_explore_claim_without_dispatch_is_uncertain(self):
        """实际领取分支也不得把未识别到派遣当成功。"""
        task, clicked = self.explore_task("领取")
        self.assertEqual("待核查", DailyRewardMixin.explore_claim(task))
        self.assertEqual(["领取"], clicked)
        task.screenshot.assert_called_once_with("explore_dispatch_unconfirmed")
        task.ensure_main.assert_called_once()

    def test_explore_unrelated_claim_text_remains_uncertain(self):
        """领奖说明与空白页面都不能当作领取成功。"""
        for label in ("完成后领取奖励", ""):
            with self.subTest(label=label):
                task, clicked = self.explore_task(label)
                self.assertEqual("待核查", DailyRewardMixin.explore_claim(task))
                self.assertEqual([], clicked)
                task.ensure_main.assert_called_once()
