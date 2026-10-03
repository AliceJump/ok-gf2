import ast
import re
import unittest
from pathlib import Path
from unittest.mock import Mock

source = Path(__file__).resolve().parents[1] / "src/tasks/daily/daily_activity_mixin.py"
node = next(n for n in ast.parse(source.read_text(encoding="utf-8")).body if isinstance(n, ast.ClassDef))
methods = [
    n
    for n in node.body
    if isinstance(n, ast.FunctionDef)
    and n.name in ("_ensure_activity_panel", "_claim_activity_panel_rewards", "free_time_layer")
]
ns = {"re": re}
exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), ns)
ensure_panel = ns["_ensure_activity_panel"]
claim_rewards = ns["_claim_activity_panel_rewards"]
free_time_layer = ns["free_time_layer"]


class ActivityPanelRewardRegressionTest(unittest.TestCase):
    def test_reward_or_leisure_page_counts_as_open_without_toggling_f2(self):
        for visible_text in ("逸趣导算", "一键领取"):
            with self.subTest(visible_text=visible_text):
                task = Mock()
                task.box_of_screen.side_effect = lambda *bounds: bounds

                def ocr(*, match, **kwargs):
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
        self.assertEqual(2, task.wait_pop_up.call_count)
        for call in task.wait_pop_up.call_args_list:
            self.assertEqual({"time_out": 6, "count": 1}, call.kwargs)
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


if __name__ == "__main__":
    unittest.main()
