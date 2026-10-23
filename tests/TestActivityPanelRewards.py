import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

source = Path(__file__).resolve().parents[1] / "src/tasks/daily/daily_activity_mixin.py"
node = next(n for n in ast.parse(source.read_text(encoding="utf-8")).body if isinstance(n, ast.ClassDef))
methods = [
    n
    for n in node.body
    if isinstance(n, ast.FunctionDef)
    and n.name in ("_ensure_activity_panel", "_claim_activity_panel_rewards", "_close_reward_popup", "free_time_layer")
]
ns = {"re": re}
exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), ns)
ensure_panel = ns["_ensure_activity_panel"]
claim_rewards = ns["_claim_activity_panel_rewards"]
close_popup = ns["_close_reward_popup"]
free_time_layer = ns["free_time_layer"]


class ActivityPanelRewardRegressionTest(unittest.TestCase):
    def test_reward_or_leisure_page_counts_as_open_without_toggling_f2(self):
        """Verify reward or leisure page counts as open without toggling f2."""
        for visible_text in ("逸趣导算", "一键领取"):
            with self.subTest(visible_text=visible_text):
                task = Mock()
                task.box_of_screen.side_effect = lambda *bounds: bounds

                def ocr(*, match, visible_text=visible_text, **kwargs):
                    """Return fixture boxes matching the visible page and requested text."""
                    return [object()] if isinstance(match, re.Pattern) and match.search(visible_text) else []

                task.wait_ocr.side_effect = ocr

                self.assertTrue(ensure_panel(task))
                task.send_key.assert_not_called()
                task.wait_click_ocr.assert_not_called()

    def test_claims_all_visible_rewards_and_closes_each_popup(self):
        task = Mock()
        task.box_of_screen.side_effect = lambda *bounds: bounds
        task.wait_click_ocr.side_effect = [object(), object(), False]

        self.assertTrue(claim_rewards(task))
        self.assertEqual(3, task.wait_click_ocr.call_count)
        self.assertEqual(2, task._close_reward_popup.call_count)
        task.wait_pop_up.assert_not_called()
        claim_pattern = task.wait_click_ocr.call_args_list[0].kwargs["match"]
        self.assertIsNotNone(claim_pattern.fullmatch("一键领取"))

    def test_rewards_are_claimed_even_when_watering_is_disabled(self):
        task = Mock()
        task.config = {"活动层浇花": False}
        task.is_free_layer.return_value = True
        task.do_food_flow.return_value = True
        task._ensure_activity_panel.return_value = True

        self.assertTrue(free_time_layer(task))
        task._claim_activity_panel_rewards.assert_called_once_with()
        task.water_flowers.assert_not_called()
        self.assertEqual(2, task.do_food_flow.call_count)
        self.assertEqual(3, task.ensure_main.call_count)

    def test_missing_first_character_in_claim_button_is_accepted(self):
        """Verify missing first character in claim button is accepted."""
        task = Mock()
        task.box_of_screen.side_effect = lambda *bounds: bounds
        state = {"claimed": False}

        def click(*, match, **kwargs):
            """Apply the selected fixture button or candidate transition."""
            if not state["claimed"] and match.fullmatch("键领取"):
                state["claimed"] = True
                return True
            return False

        task.wait_click_ocr.side_effect = click
        self.assertTrue(claim_rewards(task))
        self.assertTrue(state["claimed"])


class RewardPopupTest(unittest.TestCase):
    """实录 2026-10-21：升级动画后「获得道具」才出来，要等到并点掉提示文字，不能按 ESC。"""

    def make_task(self, frames):
        task = Mock()
        frames = list(frames)

        def wait_ocr(*, match, time_out, **kwargs):
            task.waits.append(time_out)
            names = frames.pop(0) if frames else []
            return [SimpleNamespace(name=n) for n in names if any(p.search(n) for p in match)]

        task.waits = []
        task.wait_ocr.side_effect = wait_ocr
        return task

    def test_late_popup_is_closed_by_clicking_hint(self):
        task = self.make_task([["获得道具", "活动层Lv.10", "点击空白处关闭"], []])
        self.assertTrue(close_popup(task))
        self.assertEqual("点击空白处关闭", task.click.call_args_list[0].args[0].name)
        self.assertEqual(15, task.waits[0])
        task.back.assert_not_called()

    def test_truncated_hint_is_accepted(self):
        task = self.make_task([["道具", "处关闭"], []])
        self.assertTrue(close_popup(task))
        self.assertEqual("处关闭", task.click.call_args_list[0].args[0].name)

    def test_title_without_hint_clicks_bottom_blank(self):
        task = self.make_task([["获得道具"], []])
        self.assertTrue(close_popup(task))
        task.click.assert_called_once_with(0.5, 0.9, after_sleep=1.5)

    def test_no_popup_returns_without_clicking(self):
        task = self.make_task([[]])
        self.assertTrue(close_popup(task))
        task.click.assert_not_called()

    def test_stuck_popup_reports_failure(self):
        task = self.make_task([["获得道具", "点击空白处关闭"]] * 4)
        self.assertFalse(close_popup(task))
        self.assertEqual(4, task.click.call_count)
        task.log_warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
