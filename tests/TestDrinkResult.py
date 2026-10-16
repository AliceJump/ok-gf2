"""复现饮品确认点击丢失后，误报完成并在返回主页时超时。"""

import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

source = Path(__file__).resolve().parents[1] / "src/tasks/daily/daily_activity_mixin.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
namespace = {"re": re}
methods = [
    n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name in {"_confirm_drink_result", "do_food_flow"}
]
exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), namespace)


class DrinkResultTest(unittest.TestCase):
    def make_task(self, dropped=0):
        """Model make task."""
        task = Mock()
        task.box = SimpleNamespace(bottom="bottom", bottom_right="bottom_right", top="top")
        state = {"visible": True, "clicks": 0, "hud": True}

        def click(**kwargs):
            """Model click."""
            state["clicks"] += 1
            if state["clicks"] > dropped:
                state["visible"] = False
            return True

        task.wait_click_ocr.side_effect = click
        task.wait_ocr.side_effect = lambda **kwargs: state["visible"]
        task.ocr.side_effect = lambda *args, **kwargs: (
            state["visible"]
            if kwargs.get("match") == "饮品加成"
            else ["Esc", "P", "M", "F1", "F2"]
            if state["hud"]
            else []
        )
        task.wait_until.side_effect = lambda predicate, **kwargs: predicate()
        return task, state

    def test_dropped_first_click_retries_until_result_page_disappears(self):
        """Verify dropped first click retries until result page disappears."""
        task, state = self.make_task(dropped=1)
        self.assertTrue(namespace["_confirm_drink_result"](task))
        self.assertEqual(2, state["clicks"])
        self.assertFalse(state["visible"])

    def test_persistent_result_page_is_failure_after_bounded_retries(self):
        """Verify persistent result page is failure after bounded retries."""
        task, state = self.make_task(dropped=100)
        self.assertFalse(namespace["_confirm_drink_result"](task))
        self.assertEqual(3, state["clicks"])

    def test_missing_title_alone_never_proves_return_to_activity_layer(self):
        """Verify missing title alone never proves return to activity layer."""
        task, state = self.make_task()
        task.is_free_layer.return_value = False
        state["hud"] = False
        self.assertFalse(namespace["_confirm_drink_result"](task))
        self.assertEqual(3, state["clicks"])

    def test_food_flow_never_reports_success_with_blocked_drink_result(self):
        """Verify food flow never reports success with blocked drink result."""
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

    def test_success_uses_real_executor_without_default_ten_second_wait(self):
        """使用真实 wait_condition 语义和虚拟时钟，检查嵌套默认超时。"""
        from ok.task.task import OCR, ExecutorOperation
        from ok.task.TaskExecutor import TaskExecutor

        task, _state = self.make_task()
        elapsed = [0.0]

        def tick():
            """Model tick."""
            elapsed[0] += 0.1

        executor = SimpleNamespace(
            reset_scene=lambda: None,
            next_frame=tick,
            exit_event=SimpleNamespace(is_set=lambda: False),
            wait_scene_timeout=10,
            wait_until_settle_time=0,
        )
        executor.wait_condition = TaskExecutor.wait_condition.__get__(executor)
        task.executor = executor
        task.wait_until = ExecutorOperation.wait_until.__get__(task)
        task.wait_ocr = OCR.wait_ocr.__get__(task)
        with patch("ok.task.TaskExecutor.time.time", side_effect=lambda: elapsed[0]):
            self.assertTrue(namespace["_confirm_drink_result"](task))
        self.assertLess(elapsed[0], 4, f"成功确认不应进入默认10秒等待，实际{elapsed[0]:.1f}秒")
