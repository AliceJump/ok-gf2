import unittest
from unittest.mock import Mock
from types import SimpleNamespace
from src.tasks.daily.daily_reward_mixin import DailyRewardMixin

claim = DailyRewardMixin._claim_xunlu_rewards


class XunluRewardsTest(unittest.TestCase):
    def task(self, pages, reward='数据链路', missing=False, stuck=False, show_obtained=True,
             next_buttons=0, missing_after=None):
        task = Mock()
        task.config = {}
        task.box_of_screen.side_effect = lambda *bounds: bounds
        pages = list(pages)
        if pages and show_obtained:
            pages.append('获得道具')
        clicks = []
        def ocr(**kwargs):
            return [SimpleNamespace(name=pages[0])] if pages else []
        def click(**kwargs):
            nonlocal next_buttons
            pattern = kwargs['match'][0]
            if pattern.search(reward):
                if missing or (missing_after is not None and clicks.count(reward) >= missing_after):
                    return False
                clicks.append(reward)
                return True
            expected = ('下一个' if next_buttons else '开启') if pages[0] == '拂晓之光补给包' else '确认'
            if not pattern.search(expected):
                return False
            clicks.append(expected)
            if not stuck:
                if expected == '下一个':
                    next_buttons -= 1
                else:
                    pages.pop(0)
            return True
        task.click.side_effect = lambda *args, **kwargs: pages.pop(0)
        task.wait_ocr.side_effect = ocr
        task.wait_click_ocr.side_effect = click
        return task, clicks

    def test_popup_orders_and_repeated_packs(self):
        for pages in (['领取奖励'], ['拂晓之光补给包'],
                      ['领取奖励', '拂晓之光补给包'],
                      ['拂晓之光补给包', '领取奖励'],
                      ['拂晓之光补给包', '拂晓之光补给包']):
            with self.subTest(pages=pages):
                task, clicks = self.task(pages)
                self.assertIs(True, claim(task))
                expected = []
                for page in pages:
                    expected.extend(['数据链路', '开启'] if page == '拂晓之光补给包' else ['确认'])
                self.assertEqual(expected, clicks)

    def test_missing_reward_never_opens(self):
        task, clicks = self.task(['拂晓之光补给包'], missing=True)
        self.assertFalse(claim(task))
        self.assertEqual([], clicks)

    def test_next_pages_reselect_reward_before_opening(self):
        for count in (1, 3):
            with self.subTest(next_buttons=count):
                task, clicks = self.task(['拂晓之光补给包'], next_buttons=count)
                self.assertIs(True, claim(task))
                self.assertEqual(['数据链路', '下一个'] * count + ['数据链路', '开启'], clicks)

    def test_missing_reward_on_next_page_does_not_open(self):
        task, clicks = self.task(['拂晓之光补给包'], next_buttons=1, missing_after=1)
        self.assertFalse(claim(task))
        self.assertEqual(['数据链路', '下一个'], clicks)

    def test_next_button_without_obtained_does_not_report_success(self):
        task, clicks = self.task(['拂晓之光补给包'], next_buttons=1, show_obtained=False)
        self.assertEqual('待核查', claim(task))
        self.assertEqual(['数据链路', '下一个', '数据链路', '开启'], clicks)

    def test_stuck_next_button_is_bounded(self):
        task, clicks = self.task(['拂晓之光补给包'], next_buttons=1, stuck=True)
        self.assertFalse(claim(task))
        self.assertEqual(['数据链路', '下一个'] * 8, clicks)

    def test_custom_reward(self):
        task, clicks = self.task(['拂晓之光补给包'], reward='大容量内存条')
        task.config = {'拂晓之光补给包奖励': '大容量内存条'}
        self.assertIs(True, claim(task))
        self.assertEqual(['大容量内存条', '开启'], clicks)

    def test_no_popup_is_not_success(self):
        task, clicks = self.task([])
        self.assertEqual('待核查', claim(task))
        self.assertEqual([], clicks)

    def test_confirmation_without_obtained_is_uncertain(self):
        task, clicks = self.task(['领取奖励'], show_obtained=False)
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

class XunluPageSwitchTest(unittest.TestCase):
    def task(self, results):
        task = Mock()
        task.box_of_screen.side_effect = lambda *bounds: bounds
        task.wait_ocr.side_effect = results
        return task

    def test_retries_when_click_does_not_switch_page(self):
        task = self.task([False, True, False])
        self.assertTrue(DailyRewardMixin._switch_xunlu_rewards_page(task))
        self.assertEqual(2, task.wait_click_ocr.call_count)

    def test_still_on_action_page_does_not_count_as_success(self):
        task = self.task([True, True, True, False])
        self.assertTrue(DailyRewardMixin._switch_xunlu_rewards_page(task))
        self.assertEqual(2, task.wait_click_ocr.call_count)

    def test_stuck_page_stops_after_three_attempts(self):
        task = self.task([False, False, False])
        self.assertFalse(DailyRewardMixin._switch_xunlu_rewards_page(task))
        self.assertEqual(3, task.wait_click_ocr.call_count)

    def test_success_does_not_repeat_click(self):
        task = self.task([True, False])
        self.assertTrue(DailyRewardMixin._switch_xunlu_rewards_page(task))
        task.wait_click_ocr.assert_called_once()
