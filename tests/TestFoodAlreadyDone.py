import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

source = Path(__file__).resolve().parents[1] / "src/tasks/daily/daily_activity_mixin.py"

def method(name):
    node = next(n for n in ast.walk(ast.parse(source.read_text(encoding="utf-8"))) if isinstance(n, ast.FunctionDef) and n.name == name)
    ns = {"re": re}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), ns)
    return ns[name]

class FoodAlreadyDoneTest(unittest.TestCase):
    def test_completed_drink_entry_does_not_click_or_wait_for_make(self):
        task = Mock()
        task.wait_ocr.return_value = [SimpleNamespace(name="茶歇一刻1/1")]
        result = method("do_food_flow")(task, enter_func=Mock(), entry_match=re.compile("茶歇一刻"), main_btn="制作", second_btn="确认", skip_end_match=["饮品加成"])
        self.assertIs(True, result)
        task.click_with_key.assert_not_called()
        task.wait_click_ocr.assert_not_called()
        task.skip_dialogs.assert_not_called()

    def test_duplicate_dish_is_cancelled_before_waiting_for_invite(self):
        task = Mock()
        task.wait_ocr.return_value = [SimpleNamespace(name="美味烹调")]
        task._skip_active_food_buff.return_value = True
        result = method("do_food_flow")(task, enter_func=Mock(), entry_match="美味烹调", main_btn="下一步", second_btn="确认邀请", skip_end_match=["前往战役"])
        self.assertIs(True, result)
        self.assertEqual(1, task.wait_click_ocr.call_count)
        task.skip_dialogs.assert_not_called()

    def test_only_identified_duplicate_food_dialog_is_cancelled(self):
        run = method("_skip_active_food_buff")
        for text, expected in [("同名菜品已生效，番茄鱼汤可能覆盖已生效菜品，是否确认继续", True), ("是否离开活动层？", None), ("购买是否确认继续", None)]:
            task = Mock()
            task.box.center = "center"
            task.wait_ocr.side_effect = lambda **kw: [object()] if kw["match"].search(text) else []
            task.wait_until.return_value = True
            self.assertIs(expected, run(task))
            if expected:
                self.assertEqual("取消", task.wait_click_ocr.call_args.kwargs["match"])
            else:
                task.wait_click_ocr.assert_not_called()

    def test_failed_cancel_never_reports_duplicate_food_handled(self):
        task = Mock()
        task.wait_ocr.return_value = [object()]
        task.wait_click_ocr.return_value = False
        self.assertIs(False, method("_skip_active_food_buff")(task))

    def test_unfinished_drink_still_enters_make_flow(self):
        task = Mock()
        task.wait_ocr.return_value = [SimpleNamespace(name="茶歇一刻0/1")]
        task._skip_active_food_buff.return_value = None
        task.wait_click_ocr.side_effect = [True, False]
        result = method("do_food_flow")(task, enter_func=Mock(), entry_match="茶歇一刻", main_btn="制作", second_btn="确认", skip_end_match=["饮品加成"])
        self.assertEqual("confirm", result)
        task.click_with_key.assert_called_once()

    def test_dialog_that_remains_after_cancel_is_failure(self):
        task = Mock()
        task.wait_ocr.return_value = [object()]
        task.wait_until.return_value = False
        self.assertIs(False, method("_skip_active_food_buff")(task))
