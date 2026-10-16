import unittest
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

from src.tasks.daily.daily_reward_mixin import DailyRewardMixin

claim = DailyRewardMixin._claim_xunlu_rewards
namespace = {
    name: getattr(DailyRewardMixin, name)
    for name in ("xunlu", "_claim_xunlu_rewards", "_xunlu_no_reward_status", "_record_xunlu_result")
}


class XunluOutcomeTest(unittest.TestCase):
    def task(self, action=True, reward=True, page_ok=True):
        """Model task."""
        task = Mock()
        task.box_of_screen.side_effect = lambda *bounds: bounds
        # optional new-season entry, daily tab, daily claim, reward claim
        task.wait_click_ocr.side_effect = [False, True, False, True]
        task._switch_xunlu_rewards_page.return_value = page_ok
        task.wait_ocr.return_value = True
        task._xunlu_no_reward_status.return_value = action
        task._claim_xunlu_rewards.return_value = reward
        task._record_xunlu_result.side_effect = lambda name, result: namespace["_record_xunlu_result"](
            task, name, result
        )
        return task

    def test_reward_success_not_overwritten_by_absent_daily_button(self):
        """Verify reward success not overwritten by absent daily button."""
        task = self.task(action="待核查", reward=True)
        self.assertEqual("待核查", namespace["xunlu"](task))
        task._record_xunlu_result.assert_any_call("巡录奖励", True)
        self.assertFalse(any("执行失败" in call.args[0] for call in task.log_info.call_args_list))

    def test_confirmed_no_rewards_is_success(self):
        """Verify confirmed no rewards is success."""
        task = self.task()
        self.assertIs(True, namespace["xunlu"](task))

    def test_confirmed_no_rewards_keep_specific_status_for_both_pages(self):
        """实际无奖励核验应记录专用状态，同时保持整项成功。"""
        task = self.task()
        task.wait_click_ocr.side_effect = [False, True, False, False]
        action_page = ["每日行动", "沿途行动", "已全部领取"]
        reward_page = ["大奖预览", "通行证", "暂无可领取奖励"]
        task.ocr.side_effect = [
            [SimpleNamespace(name=name) for name in page]
            for page in (action_page, action_page, reward_page, reward_page)
        ]
        task._xunlu_no_reward_status.side_effect = MethodType(namespace["_xunlu_no_reward_status"], task)

        self.assertIs(True, namespace["xunlu"](task))
        for name in ("每日行动", "巡录奖励"):
            task.info_set.assert_any_call(name, "当前无可领取项")
        task._claim_xunlu_rewards.assert_not_called()
        task.screenshot.assert_not_called()

    def test_real_failure_takes_precedence(self):
        """Verify real failure takes precedence."""
        for action, reward in [(False, True), (True, False), ("待核查", False)]:
            task = self.task(action=action, reward=reward)
            self.assertIs(False, namespace["xunlu"](task))

    def test_daily_click_verified_by_page_and_button_transition(self):
        """Verify daily click verified by page and button transition."""
        task = self.task()
        task.wait_click_ocr.side_effect = [False, True, True, True]
        task.wait_ocr.side_effect = [True, True, True, False]
        self.assertIs(True, namespace["xunlu"](task))
        task._record_xunlu_result.assert_any_call("每日行动", True)

    def test_daily_button_persists_after_click_is_failure(self):
        """Verify daily button persists after click is failure."""
        task = self.task()
        task.wait_click_ocr.side_effect = [False, True, True, True]
        self.assertIs(False, namespace["xunlu"](task))
        task._record_xunlu_result.assert_any_call("巡录奖励", True)

    def test_unrecognized_daily_result_is_not_success(self):
        """Verify unrecognized daily result is not success."""
        task = self.task()
        task.wait_click_ocr.side_effect = [False, True, True, True]
        task.wait_ocr.side_effect = [True, True, False]
        self.assertEqual("待核查", namespace["xunlu"](task))

    def test_absent_reward_button_is_uncertain_without_evidence(self):
        """Verify absent reward button is uncertain without evidence."""
        task = self.task(action="待核查")
        task.wait_click_ocr.side_effect = [False, True, False, False]
        self.assertEqual("待核查", namespace["xunlu"](task))
        task._claim_xunlu_rewards.assert_not_called()

    def test_wrong_reward_page_is_failure(self):
        """Verify wrong reward page is failure."""
        task = self.task()
        task.wait_click_ocr.side_effect = [False, True, False, False]
        task.wait_ocr.side_effect = [True, True, False]
        self.assertIs(False, namespace["xunlu"](task))

    def test_no_reward_requires_explicit_whole_page_notice(self):
        """Verify no reward requires explicit whole page notice."""
        for label in ("已全部领取", "暂无可领取奖励"):
            task = Mock()
            task.ocr.side_effect = [
                [SimpleNamespace(name=name) for name in ("每日行动", "沿途行动", "5/5", label) if name],
                [SimpleNamespace(name=name) for name in ("每日行动", "沿途行动", "5/5", label) if name],
            ]
            task.box_of_screen.side_effect = lambda *bounds: bounds
            self.assertEqual("当前无可领取项", namespace["_xunlu_no_reward_status"](task, "action"))
        for label in ("已领取", "每日行动", ""):
            task = Mock()
            task.ocr.side_effect = [
                [SimpleNamespace(name=name) for name in ("每日行动", "沿途行动", label) if name],
                [SimpleNamespace(name=name) for name in ("每日行动", "沿途行动", label) if name],
            ]
            task.box_of_screen.side_effect = lambda *bounds: bounds
            self.assertEqual("待核查", namespace["_xunlu_no_reward_status"](task, "action"))

    def test_popup_with_completion_notice_records_uncertain_and_saves_evidence(self):
        """奖励弹窗与已领完提示重叠时保留两类页面的待核查现场。"""
        for expected_page, name in (("action", "每日行动"), ("reward", "巡录奖励")):
            with self.subTest(expected_page=expected_page):
                task = self.task()
                action_page = ["每日行动", "沿途行动", "5/5", "已全部领取"]
                reward_page = ["大奖预览", "通行证", "70/100", "已全部领取", "获得道具"]
                if expected_page == "action":
                    task.ocr.side_effect = [[SimpleNamespace(name=n) for n in [*action_page, "获得道具"]]] * 2
                else:
                    task.wait_click_ocr.side_effect = [False, True, False, False]
                    task.ocr.side_effect = [
                        [SimpleNamespace(name=n) for n in page]
                        for page in (action_page, action_page, reward_page, reward_page)
                    ]
                task._xunlu_no_reward_status.side_effect = MethodType(namespace["_xunlu_no_reward_status"], task)

                self.assertEqual("待核查", namespace["xunlu"](task))
                task.info_set.assert_any_call(name, "待核查：缺少领取结果证据")
                task.screenshot.assert_called_once_with(f"Xunlu_Uncertain_{name}")


class RewardEvidenceTest(unittest.TestCase):
    def task(self, names):
        """Model task."""
        task = Mock()
        task.wait_ocr.side_effect = [[SimpleNamespace(name=n)] if n else [] for n in names]
        task.wait_click_ocr.return_value = True
        return task

    def test_obtained_confirms_success(self):
        """Verify obtained confirms success."""
        task = self.task(["领取奖励", "获得道具", None])
        self.assertIs(True, claim(task))
        task.click.assert_called_once_with(0.5, 0.95, after_sleep=1)

    def test_missing_evidence_is_uncertain(self):
        """Verify missing evidence is uncertain."""
        task = self.task(["领取奖励", None])
        self.assertEqual("待核查", claim(task))

    def test_failed_confirm_is_failure(self):
        """Verify failed confirm is failure."""
        task = self.task(["领取奖励"])
        task.wait_click_ocr.return_value = False
        self.assertIs(False, claim(task))

    def test_stuck_dialog_is_failure(self):
        """Verify stuck dialog is failure."""
        self.assertIs(False, claim(self.task(["领取奖励"] * 8)))


class NoClaimableRewardTest(unittest.TestCase):
    def task(self, pages):
        """Model task."""
        task = Mock()
        task.box_of_screen.side_effect = lambda *bounds: bounds
        task.wait_ocr.return_value = []
        task.ocr.side_effect = [[SimpleNamespace(name=n) for n in page] for page in pages]
        return task

    def test_unrelated_full_screen_ratio_does_not_confirm_no_rewards(self):
        """页面标记与无关体力或数量比值不能证明奖励已经领完。"""
        for expected_page, markers in (
            ("action", ["每日行动", "沿途行动"]),
            ("reward", ["大奖预览", "通行证"]),
        ):
            for ratio in ("161/240", "5/5", "70/100"):
                with self.subTest(page=expected_page, ratio=ratio):
                    page = [*markers, ratio]
                    self.assertEqual(
                        "待核查",
                        DailyRewardMixin._xunlu_no_reward_status(self.task([page, page]), expected_page),
                    )

    def test_action_page_progress_without_explicit_notice_stays_uncertain(self):
        """行动任务数量与单项已领取标签不能证明整个页面没有奖励。"""
        page = ["每日行动", "沿途行动", "完成日常委托", "5/5", "已领取"]
        task = self.task([page, page])
        self.assertEqual("待核查", DailyRewardMixin._xunlu_no_reward_status(task, "action"))

    def test_reward_page_level_without_explicit_notice_stays_uncertain(self):
        """等级和里程比值不能证明奖励已经领完。"""
        page = ["大奖预览", "通行证", "等级Lv.48", "70/100"]
        task = self.task([page, page])
        self.assertEqual("待核查", DailyRewardMixin._xunlu_no_reward_status(task, "reward"))

    def test_missing_or_wrong_page_stays_uncertain(self):
        """Verify missing or wrong page stays uncertain."""
        for page in ([], ["已领取"], ["每日行动"], ["通行证", "大奖预览"], ["商城", "5/5"]):
            with self.subTest(page=page):
                self.assertEqual("待核查", DailyRewardMixin._xunlu_no_reward_status(self.task([page, page]), "action"))

    def test_expected_page_must_match_both_ocr_passes(self):
        """Verify expected page must match both ocr passes."""
        action_page = ["每日行动", "沿途行动", "5/5"]
        reward_page = ["大奖预览", "通行证", "70/100"]
        self.assertEqual(
            "待核查",
            DailyRewardMixin._xunlu_no_reward_status(self.task([action_page, reward_page]), "action"),
        )
        self.assertEqual(
            "待核查",
            DailyRewardMixin._xunlu_no_reward_status(self.task([reward_page, action_page]), "reward"),
        )

    def test_expected_page_rejects_other_page_with_progress(self):
        """Verify expected page rejects other page with progress."""
        reward_page = ["大奖预览", "通行证", "70/100"]
        self.assertEqual(
            "待核查", DailyRewardMixin._xunlu_no_reward_status(self.task([reward_page, reward_page]), "action")
        )

    def test_visible_claim_or_loading_transition_is_not_no_rewards(self):
        """Verify visible claim or loading transition is not no rewards."""
        page = ["每日行动", "沿途行动", "5/5"]
        for second in ([], page + ["领取"], page + ["键领取"]):
            with self.subTest(second=second):
                self.assertEqual(
                    "待核查", DailyRewardMixin._xunlu_no_reward_status(self.task([page, second]), "action")
                )

    def test_reward_popup_overrides_completion_notice_in_either_ocr_pass(self):
        """任一轮存在奖励覆盖层时，背景的已领完提示不能确认成功。"""
        for expected_page, markers in (
            ("action", ["每日行动", "沿途行动", "5/5"]),
            ("reward", ["大奖预览", "通行证", "70/100"]),
        ):
            for notice in ("已全部领取", "全部已领取", "暂无可领取奖励", "无可领取奖励"):
                for popup in ("获得道具", "领取奖励", "拂晓之光补给包"):
                    for popup_pass in (0, 1):
                        with self.subTest(page=expected_page, notice=notice, popup=popup, popup_pass=popup_pass):
                            page = [*markers, notice]
                            pages = [page, page]
                            pages[popup_pass] = [*page, popup]
                            self.assertEqual(
                                "待核查",
                                DailyRewardMixin._xunlu_no_reward_status(self.task(pages), expected_page),
                            )

    def test_explicit_no_reward_without_popup_is_confirmed(self):
        """完整无奖励提示中的领取奖励字样不是弹窗证据。"""
        for expected_page, markers in (
            ("action", ["每日行动", "沿途行动"]),
            ("reward", ["大奖预览", "通行证"]),
        ):
            for notice in ("已全部领取", "全部已领取", "暂无可领取奖励", "无可领取奖励"):
                with self.subTest(page=expected_page, notice=notice):
                    page = [*markers, notice]
                    self.assertEqual(
                        "当前无可领取项",
                        DailyRewardMixin._xunlu_no_reward_status(self.task([page, page]), expected_page),
                    )

    def test_no_claimable_label_does_not_claim_all_rewards_were_received(self):
        """Verify no claimable label does not claim all rewards were received."""
        task = Mock()
        DailyRewardMixin._record_xunlu_result(task, "每日行动", "当前无可领取项")
        task.info_set.assert_called_once_with("每日行动", "当前无可领取项")
