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
    n
    for n in ast.walk(tree)
    if isinstance(n, ast.FunctionDef) and n.name in {"_confirm_drink_result", "_skip_active_food_buff", "do_food_flow"}
]
exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), namespace)


class DuplicateDrinkReturnTest(unittest.TestCase):
    def run_cancel(self, hud_count=7, result_visible=False, dialog_stuck=False):
        """执行真实制作和取消逻辑，只替换 OCR、点击及帧等待边界。"""
        state = {"duplicate": True, "buttons": [], "screenshots": []}

        def read(*, match, **kwargs):
            """按测试状态返回重复提示、结果页或活动层 HUD。"""
            if isinstance(match, re.Pattern):
                return ["同名饮品已生效"] if state["duplicate"] else []
            if match == "饮品加成":
                return ["饮品加成"] if result_visible else []
            return ["Esc", "P", "M", "F1", "F2", "F3", "F4"][:hud_count]

        def click(*, match, **kwargs):
            """记录点击并模拟取消重复提示后的页面状态。"""
            state["buttons"].append(match)
            if match == "取消":
                state["duplicate"] = dialog_stuck
            return True

        task = SimpleNamespace(
            box=SimpleNamespace(center="center", top="top", bottom_right="bottom_right"),
            wait_ocr=lambda **kwargs: [SimpleNamespace(name="茶歇一刻0/1")],
            click_with_key=lambda *args: None,
            wait_click_ocr=click,
            ocr=read,
            wait_until=lambda predicate, **kwargs: bool(predicate()),
            screenshot=state["screenshots"].append,
            log_info=lambda message: None,
        )
        task._skip_active_food_buff = namespace["_skip_active_food_buff"].__get__(task)
        result = namespace["do_food_flow"](
            task,
            enter_func=lambda **kwargs: None,
            entry_match="茶歇一刻",
            main_btn="制作",
            second_btn="确认",
            skip_end_match=["饮品加成"],
        )
        return result, state

    def test_cancelled_drink_requires_activity_hud(self):
        """提示消失但缺少完整 HUD 时不能把饮品标记为完成。"""
        for count in (0, 4):
            with self.subTest(hud_count=count):
                result, state = self.run_cancel(hud_count=count)
                self.assertEqual("confirm", result)
                self.assertEqual(["制作", "取消"], state["buttons"])
                self.assertEqual(["food_duplicate_dialog_blocked"], state["screenshots"])

    def test_visible_drink_result_is_not_activity_layer(self):
        """即使背景 HUD 可见，饮品结果页未关闭也不能报告完成。"""
        result, _ = self.run_cancel(result_visible=True)
        self.assertEqual("confirm", result)

    def test_cancelled_drink_returns_success_only_after_activity_hud(self):
        """结果页关闭且活动层 HUD 出现后才结束重复制作。"""
        result, state = self.run_cancel(hud_count=5)
        self.assertIs(True, result)
        self.assertEqual(["制作", "取消"], state["buttons"])
        self.assertEqual([], state["screenshots"])

    def test_persistent_duplicate_dialog_is_not_success(self):
        """重复提示仍在时，即使背景 HUD 可见也不能成功。"""
        result, _ = self.run_cancel(dialog_stuck=True)
        self.assertEqual("confirm", result)


class DrinkResultTest(unittest.TestCase):
    def test_make_click_retries_only_while_selection_page_remains(self):
        """A reported make click can be dropped while the selection page stays open."""
        task = Mock()
        task.box = SimpleNamespace(bottom_right="bottom_right")
        task.wait_ocr.return_value = [SimpleNamespace(name="茶歇一刻0/1")]
        task._skip_active_food_buff.return_value = None
        task._confirm_drink_result.return_value = True
        state = {"page": "selection", "makes": 0}

        def click(*, match, **kwargs):
            """模拟制作点击后页面从选择页推进到确认页。"""
            if match == "制作":
                state["makes"] += 1
                if state["makes"] == 2:
                    state["page"] = "confirm"
                return True
            return state["page"] == "confirm"

        def read(*, match, **kwargs):
            """根据模拟页面状态返回制作或确认按钮。"""
            if match == "制作":
                return [object()] if state["page"] == "selection" else []
            return [object()] if state["page"] == "confirm" else []

        task.wait_click_ocr.side_effect = click
        task.ocr.side_effect = read
        task.wait_until.side_effect = lambda condition, **kwargs: bool(condition())
        result = namespace["do_food_flow"](
            task,
            enter_func=Mock(),
            entry_match="茶歇一刻",
            main_btn="制作",
            second_btn="确认",
            skip_end_match=["饮品加成"],
        )
        self.assertIs(True, result)
        self.assertEqual(2, state["makes"])

    def test_make_click_stops_after_two_unchanged_selection_pages(self):
        """Do not keep clicking make when both attempts fail to change the page."""
        task = Mock()
        task.box = SimpleNamespace(bottom_right="bottom_right")
        task.wait_ocr.return_value = [SimpleNamespace(name="茶歇一刻0/1")]
        task._skip_active_food_buff.return_value = None
        task.wait_click_ocr.side_effect = lambda *, match, **kwargs: match == "制作"
        task.ocr.side_effect = lambda *, match, **kwargs: [object()] if match == "制作" else []
        task.wait_until.side_effect = lambda condition, **kwargs: bool(condition())
        result = namespace["do_food_flow"](
            task,
            enter_func=Mock(),
            entry_match="茶歇一刻",
            main_btn="制作",
            second_btn="确认",
            skip_end_match=["饮品加成"],
        )
        self.assertEqual("confirm", result)
        self.assertEqual(2, sum(call.kwargs.get("match") == "制作" for call in task.wait_click_ocr.call_args_list))
        task.screenshot.assert_called_with("food_make_not_advanced")

    def test_retry_miss_rechecks_confirm_page_before_failing(self):
        """A retry miss can mean the page advanced between the last OCR and click."""
        task = Mock()
        task.box = SimpleNamespace(bottom_right="bottom_right")
        task.wait_ocr.return_value = [SimpleNamespace(name="茶歇一刻0/1")]
        task._skip_active_food_buff.return_value = None
        state = {"page": "selection", "makes": 0}

        def click(*, match, **kwargs):
            """模拟重试点击未命中但页面已推进的竞态。"""
            if match == "制作":
                state["makes"] += 1
                if state["makes"] == 2:
                    state["page"] = "confirm"
                    return False
                return True
            return state["page"] == "confirm"

        def read(*, match, **kwargs):
            """根据竞态后的页面状态返回制作或确认按钮。"""
            if match == "制作":
                return [object()] if state["page"] == "selection" else []
            return [object()] if state["page"] == "confirm" else []

        task.wait_click_ocr.side_effect = click
        task.ocr.side_effect = read
        task.wait_until.side_effect = lambda condition, **kwargs: bool(condition())
        result = namespace["do_food_flow"](
            task,
            enter_func=Mock(),
            entry_match="茶歇一刻",
            main_btn="制作",
            second_btn="确认",
            skip_end_match=["饮品加成"],
        )
        self.assertIs(True, result)
        self.assertEqual(2, state["makes"])
        task.screenshot.assert_not_called()

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
        result = namespace["do_food_flow"](
            task,
            enter_func=Mock(),
            entry_match="茶歇一刻",
            main_btn="制作",
            second_btn="确认",
            skip_end_match=["饮品加成"],
        )
        self.assertEqual("confirm", result)
        task.log_error.assert_called_once_with("饮品加成确认失败：结果页未关闭")
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
