import re
import unittest
from unittest.mock import Mock
from types import SimpleNamespace
from src.tasks.daily.daily_reward_mixin import DailyRewardMixin
claim = DailyRewardMixin._claim_xunlu_rewards
class XunluRewardsTest(unittest.TestCase):
    def task(self, pages, reward='数据链路', missing=False, stuck=False, show_obtained=True):
        task = Mock()
        task.config = {}
        task.box_of_screen.side_effect = lambda *bounds: bounds
        pages = list(pages)
        clicks = []
        def ocr(**kwargs):
            return [SimpleNamespace(name=pages[0])] if pages else []
        def click(**kwargs):
            pattern = kwargs['match'][0]
            if pattern.search(reward):
                if missing:
                    return False
                clicks.append(reward)
                return True
            expected = '开启' if pages[0] == '拂晓之光补给包' else '确认'
            if not pattern.search(expected):
                return False
            clicks.append(expected)
            if not stuck:
                pages.pop(0)
            return True
        def click_blank(*args, **kwargs):
            # 「获得道具」展示页没有操作按钮，点击底部空白处关闭后继续。
            if pages and pages[0] == '获得道具':
                pages.pop(0)
        task.wait_ocr.side_effect = ocr
        task.wait_click_ocr.side_effect = click
        task.click.side_effect = click_blank
        return task, clicks

    def test_popup_orders_and_repeated_packs(self):
        # 末尾的「获得道具」是奖励到账证据，缺少它只能判为待核查。
        for pages in (['领取奖励', '获得道具'], ['拂晓之光补给包', '获得道具'],
                      ['领取奖励', '拂晓之光补给包', '获得道具'],
                      ['拂晓之光补给包', '领取奖励', '获得道具'],
                      ['拂晓之光补给包', '拂晓之光补给包', '获得道具']):
            with self.subTest(pages=pages):
                task, clicks = self.task(pages)
                self.assertIs(True, claim(task))
                expected = []
                for page in pages:
                    if page == '获得道具':
                        continue
                    expected.extend(['数据链路', '开启'] if page == '拂晓之光补给包' else ['确认'])
                self.assertEqual(expected, clicks)

    def test_missing_reward_never_opens(self):
        task, clicks = self.task(['拂晓之光补给包'], missing=True)
        self.assertFalse(claim(task))
        self.assertEqual([], clicks)

    def test_custom_reward(self):
        task, clicks = self.task(['拂晓之光补给包', '获得道具'], reward='大容量内存条')
        task.config = {'拂晓之光补给包奖励': '大容量内存条'}
        self.assertIs(True, claim(task))
        self.assertEqual(['大容量内存条', '开启'], clicks)

    def test_no_popup_is_not_success(self):
        task, clicks = self.task([])
        self.assertEqual('待核查', claim(task))
        self.assertEqual([], clicks)

    def test_popup_without_obtained_evidence_is_uncertain(self):
        task, clicks = self.task(['领取奖励'])
        self.assertEqual('待核查', claim(task))
        self.assertEqual(['确认'], clicks)

    def test_missing_confirmation_is_failure(self):
        task, _ = self.task(['领取奖励'])
        task.wait_click_ocr.side_effect = None
        task.wait_click_ocr.return_value = False
        self.assertIs(False, claim(task))

    def test_stuck_dialog_is_bounded_failure(self):
        task, clicks = self.task(['领取奖励'], stuck=True)
        self.assertFalse(claim(task))
        self.assertEqual(8, len(clicks))
