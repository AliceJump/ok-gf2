"""复现饮品确认点击丢失后，误报完成并在返回主页时超时。"""

import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

source = Path(__file__).resolve().parents[1] / "src/tasks/daily/daily_activity_mixin.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
namespace = {"re": re}
methods = [
    n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in {"_confirm_drink_result", "do_food_flow"}
]
exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), namespace)


class DrinkResultTest(unittest.TestCase):
    def make_task(self, dropped=0):
        task = Mock()
        task.box = SimpleNamespace(bottom="bottom", bottom_right="bottom_right")
        state = {"visible": True, "clicks": 0}

        def click(**kwargs):
            state["clicks"] += 1
            if state["clicks"] > dropped:
                state["visible"] = False
            return True

        task.wait_click_ocr.side_effect = click
        task.wait_ocr.side_effect = lambda **kwargs: state["visible"]
        task.wait_until.side_effect = lambda predicate, **kwargs: predicate()
        return task, state

    def test_dropped_first_click_retries_until_result_page_disappears(self):
        task, state = self.make_task(dropped=1)
        self.assertTrue(namespace["_confirm_drink_result"](task))
        self.assertEqual(2, state["clicks"])
        self.assertFalse(state["visible"])

    def test_persistent_result_page_is_failure_after_bounded_retries(self):
        task, state = self.make_task(dropped=100)
        self.assertFalse(namespace["_confirm_drink_result"](task))
        self.assertEqual(3, state["clicks"])

    def test_missing_title_alone_never_proves_return_to_activity_layer(self):
        task, state = self.make_task()
        task.is_free_layer.return_value = False
        self.assertFalse(namespace["_confirm_drink_result"](task))
        self.assertEqual(3, state["clicks"])

    def test_food_flow_never_reports_success_with_blocked_drink_result(self):
        task = Mock()
        task._confirm_drink_result.return_value = False
        task.wait_ocr.return_value = [SimpleNamespace(name="entry")]
        with self.assertRaisesRegex(RuntimeError, "饮品加成"):
            namespace["do_food_flow"](
                task,
                enter_func=Mock(),
                entry_match="茶歇一刻",
                main_btn="制作",
                second_btn="确认",
                skip_end_match=["饮品加成"],
            )
        task.wait_pop_up.assert_not_called()
