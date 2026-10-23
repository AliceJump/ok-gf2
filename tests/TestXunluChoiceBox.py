"""
实录 2026-10-20：巡录「一键领取」带「标准武器自选礼箱」时弹「请在以上奖励中选择1项」。
脚本不替玩家选武器：点「取消」，结果记成待核查并说明原因；不能点「下一个」。
"""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from src.tasks.daily.daily_reward_mixin import DailyRewardMixin

claim = DailyRewardMixin._claim_xunlu_rewards
record = DailyRewardMixin._record_xunlu_result


def make_task(screens):
    """screens: 每次 wait_ocr 看到的整屏文字列表；点一次按钮翻到下一屏。"""
    task = Mock()
    task.config = {}
    task.box_of_screen.side_effect = lambda *b: b
    screens = [list(s) for s in screens]
    clicked = []

    def wait_ocr(**kw):
        if not screens:
            return []
        return [SimpleNamespace(name=t) for t in screens[0] if any(p.search(t) for p in kw["match"])]

    def ocr(**kw):
        return [SimpleNamespace(name=t) for t in (screens[0] if screens else [])]

    def wait_click_ocr(**kw):
        hit = [t for t in (screens[0] if screens else []) if any(p.search(t) for p in kw["match"])]
        if not hit:
            return False
        clicked.append(hit[0])
        screens.pop(0)
        return True

    task.wait_ocr.side_effect = wait_ocr
    task.ocr.side_effect = ocr
    task.wait_click_ocr.side_effect = wait_click_ocr
    task.click.side_effect = lambda *a, **k: screens.pop(0) if screens else None
    task.clicked = clicked
    return task


CHOICE = ["1/2", "标准武器自选礼箱", "野兔", "复仇女神", "请在以上奖励中选择1项", "取消", "下一个"]


class XunluChoiceBoxTest(unittest.TestCase):
    def test_choice_box_is_cancelled_and_reported(self):
        task = make_task([CHOICE, []])
        result = claim(task)
        self.assertEqual(task.clicked, ["取消"])
        self.assertTrue(str(result).startswith("待核查："), result)
        self.assertIn("标准武器自选礼箱", result)
        self.assertIn("手动选择", result)

    def test_two_choice_boxes_both_cancelled(self):
        task = make_task([CHOICE, CHOICE, []])
        result = claim(task)
        self.assertEqual(task.clicked, ["取消", "取消"])
        self.assertTrue(str(result).startswith("待核查："))

    def test_obtained_after_choice_still_uncertain(self):
        task = make_task([["获得道具"], CHOICE, []])
        result = claim(task)
        self.assertTrue(str(result).startswith("待核查："), result)

    def test_missing_cancel_button_is_failure(self):
        task = make_task([["标准武器自选礼箱", "请在以上奖励中选择1项", "下一个"]])
        self.assertFalse(claim(task))
        self.assertEqual(task.clicked, [])

    def test_record_keeps_specific_reason(self):
        task = Mock()
        record(task, "巡录奖励", "待核查：「标准武器自选礼箱」需要手动选择，脚本已取消未替你选")
        task.info_set.assert_called_once_with(
            "巡录奖励", "待核查：「标准武器自选礼箱」需要手动选择，脚本已取消未替你选"
        )
        record(task, "巡录奖励", "待核查")
        task.info_set.assert_called_with("巡录奖励", "待核查：缺少领取结果证据")


if __name__ == "__main__":
    unittest.main()
