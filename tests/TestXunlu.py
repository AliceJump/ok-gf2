import unittest
from unittest.mock import Mock
from src.tasks.daily.daily_reward_mixin import DailyRewardMixin


class XunluTest(unittest.TestCase):

    def test_xunlu_missing_entry_returns_home(self):
        ns = {'xunlu': DailyRewardMixin.xunlu}
        task = Mock()
        task.wait_ocr.return_value = []
        self.assertFalse(ns['xunlu'](task))
        task.wait_click_ocr.assert_not_called()
        task.ensure_main.assert_called_once()

    def test_xunlu_both_entry_forms_open_actions_before_claiming(self):
        ns = {'xunlu': DailyRewardMixin.xunlu}
        for preview in [False, True]:
            with self.subTest(preview=preview):
                task = Mock()
                task.box_of_screen.side_effect = lambda *coords: coords
                task.wait_ocr.side_effect = [[Mock()], True, True, False]
                task.wait_click_ocr.side_effect = [preview, True, True, True, True, True]
                self.assertTrue(ns['xunlu'](task))
                task.ensure_main.assert_called_once()
                self.assertEqual(6, task.wait_click_ocr.call_count)
                calls = task.wait_click_ocr.call_args_list
                self.assertEqual('^沿途行动$', calls[1].kwargs['match'][0].pattern)
                self.assertEqual(task.box.top, calls[1].kwargs['box'])
                self.assertEqual('^一键领取$', calls[2].kwargs['match'][0].pattern)
                self.assertEqual((0.70, 0.88, 1, 1), calls[2].kwargs['box'])
                self.assertEqual('^远航巡录$', calls[3].kwargs['match'][0].pattern)
                self.assertEqual((0.25, 0, 0.65, 0.12), calls[3].kwargs['box'])
                self.assertEqual('^一键领取$', calls[4].kwargs['match'][0].pattern)
                self.assertEqual('^确认$', calls[5].kwargs['match'][0].pattern)
                self.assertEqual(task.box.bottom_right, calls[5].kwargs['box'])
                self.assertEqual((0, 0, 1, 1), task.wait_ocr.call_args_list[2].kwargs['box'])
                self.assertEqual((0, 0, 1, 1), task.wait_ocr.call_args_list[3].kwargs['box'])
                task.click.assert_called_once_with(0.5, 0.95, after_sleep=1)
                names = [call[0] for call in task.mock_calls]
                self.assertLess(names.index('click'), names.index('ensure_main'))
                for call in task.wait_click_ocr.call_args_list:
                    self.assertFalse(call.kwargs['raise_if_not_found'])

    def test_xunlu_does_not_claim_on_pass_page_when_actions_unavailable(self):
        ns = {'xunlu': DailyRewardMixin.xunlu}
        for tab_found, page_found in [(False, False), (True, False)]:
            with self.subTest(tab_found=tab_found):
                task = Mock()
                task.wait_ocr.side_effect = [[Mock()], page_found]
                task.wait_click_ocr.side_effect = [False, tab_found]
                self.assertFalse(ns['xunlu'](task))
                self.assertEqual(2, task.wait_click_ocr.call_count)
                task.ensure_main.assert_called_once()

    def test_xunlu_missing_claim_reports_incomplete(self):
        ns = {'xunlu': DailyRewardMixin.xunlu}
        task = Mock()
        task.wait_ocr.side_effect = [[Mock()], True, True, False]
        task.wait_click_ocr.side_effect = [False, True, False, True, True, True]
        self.assertFalse(ns['xunlu'](task))
        self.assertEqual(6, task.wait_click_ocr.call_count)
        task.ensure_main.assert_called_once()

    def test_xunlu_pass_reward_failures_never_report_success(self):
        ns = {'xunlu': DailyRewardMixin.xunlu}
        scenarios = [
            ([False, True, True, False], [[Mock()], True]),
            ([False, True, True, True, False], [[Mock()], True]),
            ([False, True, True, True, True], [[Mock()], True, False]),
            ([False, True, True, True, True, False], [[Mock()], True, True]),
            ([False, True, True, True, True, True], [[Mock()], True, True, True]),
        ]
        for clicks, observations in scenarios:
            with self.subTest(clicks=clicks, observations=observations):
                task = Mock()
                task.wait_click_ocr.side_effect = clicks
                task.wait_ocr.side_effect = observations
                self.assertFalse(ns['xunlu'](task))
                task.wait_pop_up.assert_not_called()
                task.click.assert_not_called()
                task.ensure_main.assert_called_once()

    def test_xunlu_selects_bottom_bulk_claim_with_individual_claims_visible(self):
        ns = {'xunlu': DailyRewardMixin.xunlu}
        task = Mock()
        task.box_of_screen.side_effect = lambda *coords: coords
        task.wait_ocr.side_effect = [[Mock()], True, True, False]
        selected = []
        calls = 0

        def click_ocr(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return False
            if calls == 3:
                # 2560x1600 日志中的单项领取 y=970，底部一键领取约 y=1515。
                candidates = [('领取', 2274 / 2560, 970 / 1600),
                              ('一键领取', 2225 / 2560, 1515 / 1600)]
                x1, y1, x2, y2 = kwargs['box']
                found = [name for name, x, y in candidates
                         if x1 <= x <= x2 and y1 <= y <= y2
                         and kwargs['match'][0].fullmatch(name)]
                selected.extend(found[:1])
                return bool(found)
            return True

        task.wait_click_ocr.side_effect = click_ocr
        self.assertTrue(ns['xunlu'](task))
        self.assertEqual(['一键领取'], selected)
