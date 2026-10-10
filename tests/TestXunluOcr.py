import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from src.tasks.daily.daily_reward_mixin import DailyRewardMixin

xunlu = DailyRewardMixin.xunlu


class XunluOcrTest(unittest.TestCase):
    def run_claim(self, label, persists=False):
        task = Mock()
        task.box_of_screen.side_effect = lambda *bounds: bounds
        task._switch_xunlu_rewards_page.return_value = True
        task._claim_xunlu_rewards.return_value = True
        task._xunlu_no_reward_status.return_value = "待核查"
        clicks = []
        read_count = 0
        click_count = 0

        def read(**kwargs):
            nonlocal read_count
            read_count += 1
            if read_count <= 3:
                return [Mock()]
            # After clicking, a surviving OCR-truncated button must still be detected.
            return [SimpleNamespace(name="键领取")] if persists and kwargs["match"][0].fullmatch("键领取") else []

        def click(**kwargs):
            nonlocal click_count
            click_count += 1
            if click_count == 1:
                return False  # Optional preview entry.
            if click_count == 2:
                return True  # Action tab.
            candidates = [("领取", 0.86, 0.61), (label, 0.86, 0.94)]
            left, top, right, bottom = kwargs["box"]
            found = [
                name
                for name, x, y in candidates
                if left <= x <= right and top <= y <= bottom and kwargs["match"][0].fullmatch(name)
            ]
            clicks.extend(found)
            return bool(found)

        task.wait_ocr.side_effect = read
        task.wait_click_ocr.side_effect = click
        result = xunlu(task)
        return task, clicks, result

    def test_bulk_claim_accepts_missing_first_character_on_both_pages(self):
        for label in ("一键领取", "键领取", "一 键 领 取", "键 领 取"):
            with self.subTest(label=label):
                task, clicks, result = self.run_claim(label)
                self.assertIs(result, True)
                self.assertEqual([label, label], clicks)
                calls = task.wait_click_ocr.call_args_list
                self.assertEqual((0.50, 0.50, 1, 1), calls[2].kwargs["box"])
                self.assertEqual((0.50, 0.80, 1, 1), calls[3].kwargs["box"])
                task._claim_xunlu_rewards.assert_called_once()

    def test_individual_and_unrelated_labels_are_not_clicked(self):
        for label in ("领取", "已领取", "全部领取", "一键领取奖励", "不可一键领取"):
            with self.subTest(label=label):
                task, clicks, result = self.run_claim(label)
                self.assertEqual([], clicks)
                self.assertEqual("待核查", result)
                task._claim_xunlu_rewards.assert_not_called()

    def test_truncated_button_after_click_is_not_success(self):
        task, _, result = self.run_claim("一键领取", persists=True)
        self.assertIs(result, False)
        task._record_xunlu_result.assert_any_call("每日行动", False)

    def test_absent_button_is_uncertain(self):
        _, clicks, result = self.run_claim("")
        self.assertEqual([], clicks)
        self.assertEqual("待核查", result)
