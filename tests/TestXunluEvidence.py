import re
import unittest
from unittest.mock import Mock
from types import SimpleNamespace
from src.tasks.daily.daily_reward_mixin import DailyRewardMixin
claim = DailyRewardMixin._claim_xunlu_rewards
namespace = {name: getattr(DailyRewardMixin, name) for name in
             ('xunlu', '_claim_xunlu_rewards', '_xunlu_no_reward_status', '_record_xunlu_result')}
class XunluOutcomeTest(unittest.TestCase):
    def task(self, action=True, reward=True, page_ok=True):
        task = Mock()
        task.box_of_screen.side_effect = lambda *bounds: bounds
        # optional new-season entry, daily tab, daily claim, reward tab, reward claim
        task.wait_click_ocr.side_effect = [False, True, False, True, True]
        task.wait_ocr.return_value = True
        task._xunlu_no_reward_status.return_value = action
        task._claim_xunlu_rewards.return_value = reward
        task._record_xunlu_result.side_effect = lambda name, result: namespace['_record_xunlu_result'](task, name, result)
        return task

    def test_reward_success_not_overwritten_by_absent_daily_button(self):
        task = self.task(action='待核查', reward=True)
        self.assertEqual('待核查', namespace['xunlu'](task))
        task._record_xunlu_result.assert_any_call('巡录奖励', True)
        self.assertFalse(any('执行失败' in call.args[0] for call in task.log_info.call_args_list))

    def test_confirmed_no_rewards_is_success(self):
        task = self.task()
        self.assertIs(True, namespace['xunlu'](task))

    def test_real_failure_takes_precedence(self):
        for action, reward in [(False, True), (True, False), ('待核查', False)]:
            task = self.task(action=action, reward=reward)
            self.assertIs(False, namespace['xunlu'](task))

    def test_daily_click_verified_by_page_and_button_transition(self):
        task = self.task()
        task.wait_click_ocr.side_effect = [False, True, True, True, True]
        task.wait_ocr.side_effect = [True, True, True, False]
        self.assertIs(True, namespace['xunlu'](task))
        task._record_xunlu_result.assert_any_call('每日行动', True)

    def test_daily_button_persists_after_click_is_failure(self):
        task = self.task()
        task.wait_click_ocr.side_effect = [False, True, True, True, True]
        self.assertIs(False, namespace['xunlu'](task))
        task._record_xunlu_result.assert_any_call('巡录奖励', True)

    def test_unrecognized_daily_result_is_not_success(self):
        task = self.task()
        task.wait_click_ocr.side_effect = [False, True, True, True, True]
        task.wait_ocr.side_effect = [True, True, False]
        self.assertEqual('待核查', namespace['xunlu'](task))

    def test_absent_reward_button_is_uncertain_without_evidence(self):
        task = self.task(action='待核查')
        task.wait_click_ocr.side_effect = [False, True, False, True, False]
        self.assertEqual('待核查', namespace['xunlu'](task))
        task._claim_xunlu_rewards.assert_not_called()

    def test_wrong_reward_page_is_failure(self):
        task = self.task()
        task.wait_click_ocr.side_effect = [False, True, False, True, False]
        task.wait_ocr.side_effect = [True, True, False]
        self.assertIs(False, namespace['xunlu'](task))

    def test_no_reward_requires_explicit_whole_page_notice(self):
        for label, expected in [('已全部领取', True), ('暂无可领取奖励', True),
                                ('已领取', '待核查'), ('每日行动', '待核查'), ('', '待核查')]:
            task = Mock()
            task.wait_ocr.side_effect = lambda label=label, **kw: bool(kw['match'][0].search(label))
            self.assertEqual(expected, namespace['_xunlu_no_reward_status'](task))


class RewardEvidenceTest(unittest.TestCase):
    def task(self, names):
        task = Mock()
        task.wait_ocr.side_effect = [[SimpleNamespace(name=n)] if n else [] for n in names]
        task.wait_click_ocr.return_value = True
        return task

    def test_obtained_confirms_success(self):
        task = self.task(['领取奖励', '获得道具', None])
        self.assertIs(True, claim(task))
        task.click.assert_called_once_with(0.5, 0.95, after_sleep=1)

    def test_missing_evidence_is_uncertain(self):
        task = self.task(['领取奖励', None])
        self.assertEqual('待核查', claim(task))

    def test_failed_confirm_is_failure(self):
        task = self.task(['领取奖励'])
        task.wait_click_ocr.return_value = False
        self.assertIs(False, claim(task))

    def test_stuck_dialog_is_failure(self):
        self.assertIs(False, claim(self.task(['领取奖励'] * 8)))
