import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from ok import Box
from ok.feature.Box import relative_box

source = Path(__file__).resolve().parents[1] / "src/tasks/daily/daily_activity_mixin.py"


def method(name):
    """Model method."""
    node = next(
        n
        for n in ast.walk(ast.parse(source.read_text(encoding="utf-8")))
        if isinstance(n, ast.FunctionDef) and n.name == name
    )
    ns = {"re": re}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), ns)
    return ns[name]


class FoodAlreadyDoneTest(unittest.TestCase):
    def drink_scene(self, boxes, width=1920, height=1080):
        """保留真实 Box 与裁剪坐标，只替换设备 OCR 和点击边界。"""
        task = Mock()
        task.width, task.height = width, height
        task.box_of_screen.side_effect = lambda *bounds: relative_box(width, height, *bounds)

        def read(*, match=None, box=None, **kwargs):
            """模拟标题筛选和局部 OCR，不将无关计数送入结果。"""
            return [
                item
                for item in boxes
                if (
                    (match is None or re.search(match, item.name))
                    and (
                        box is None
                        or (
                            box.x <= item.x
                            and item.x + item.width <= box.x + box.width
                            and box.y <= item.y
                            and item.y + item.height <= box.y + box.height
                        )
                    )
                )
            ]

        task.wait_ocr.side_effect = read
        task.ocr.side_effect = read
        task.wait_click_ocr.return_value = False
        return task

    def run_drink(self, task):
        """执行真实饮品流程，制作按钮不可用时必须靠完成证据跳过。"""
        return method("do_food_flow")(
            task,
            enter_func=Mock(),
            entry_match=re.compile("茶歇一刻"),
            main_btn="制作",
            second_btn="确认",
            skip_end_match=["饮品加成"],
        )

    def test_split_completed_counter_skips_unavailable_make_button(self):
        """标题和次数分框时，正常返回完成且不再尝试制作。"""
        for counter in [Box(930, 400, 40, 24, name="1/1"), Box(840, 430, 48, 24, name="1 ／ 1")]:
            with self.subTest(counter=counter.name, y=counter.y):
                task = self.drink_scene([Box(800, 400, 120, 24, name="茶歇一刻"), counter])
                self.assertIs(True, self.run_drink(task))
                task.click_with_key.assert_not_called()
                task.wait_click_ocr.assert_not_called()

    def test_unrelated_completed_counter_does_not_skip_unfinished_drink(self):
        """旁边其他入口的 1/1 不能使未完成或无计数的饮品误报完成。"""
        for count in ["0/1", "2/2", ""]:
            with self.subTest(count=count):
                task = self.drink_scene(
                    [
                        Box(800, 400, 120, 24, name="茶歇一刻"),
                        Box(930, 400, 40, 24, name=count),
                        Box(1400, 400, 40, 24, name="1/1"),
                        Box(930, 650, 40, 24, name="1/1"),
                    ]
                )
                self.assertEqual("button", self.run_drink(task))
                task.click_with_key.assert_called_once()

    def test_combined_counter_must_be_exactly_one_of_one(self):
        """同框 1/10 和显式未完成状态不能误用附近的完成计数。"""
        for count in ["0/1", "1/10", "11/11"]:
            with self.subTest(count=count):
                task = self.drink_scene(
                    [
                        Box(800, 400, 170, 24, name="茶歇一刻" + count),
                        Box(980, 400, 40, 24, name="1/1"),
                    ]
                )
                self.assertEqual("button", self.run_drink(task))
                task.click_with_key.assert_called_once()

    def test_split_counter_near_screen_edge_uses_clamped_region(self):
        """不同分辨率及靠边入口使用合法局部区域读取计数。"""
        task = self.drink_scene(
            [
                Box(1130, 670, 96, 16, name="茶歇一刻"),
                Box(1230, 690, 32, 16, name="1/1"),
            ],
            width=1280,
            height=720,
        )
        self.assertIs(True, self.run_drink(task))
        region = task.ocr.call_args.kwargs["box"]
        self.assertGreaterEqual(region.x, 0)
        self.assertGreaterEqual(region.y, 0)
        self.assertLessEqual(region.x + region.width, 1280)
        self.assertLessEqual(region.y + region.height, 720)
        task.click_with_key.assert_not_called()

    def test_completed_drink_entry_does_not_click_or_wait_for_make(self):
        """Verify completed drink entry does not click or wait for make."""
        task = Mock()
        task.wait_ocr.return_value = [SimpleNamespace(name="茶歇一刻1/1")]
        result = method("do_food_flow")(
            task,
            enter_func=Mock(),
            entry_match=re.compile("茶歇一刻"),
            main_btn="制作",
            second_btn="确认",
            skip_end_match=["饮品加成"],
        )
        self.assertIs(True, result)
        task.click_with_key.assert_not_called()
        task.wait_click_ocr.assert_not_called()
        task.skip_dialogs.assert_not_called()

    def test_duplicate_dish_is_cancelled_before_waiting_for_invite(self):
        """Verify duplicate dish is cancelled before waiting for invite."""
        task = Mock()
        task.wait_ocr.return_value = [SimpleNamespace(name="美味烹调")]
        task._skip_active_food_buff.return_value = True
        result = method("do_food_flow")(
            task,
            enter_func=Mock(),
            entry_match="美味烹调",
            main_btn="下一步",
            second_btn="确认邀请",
            skip_end_match=["前往战役"],
        )
        self.assertIs(True, result)
        self.assertEqual(1, task.wait_click_ocr.call_count)
        task.skip_dialogs.assert_not_called()
        task._skip_active_food_buff.assert_called_once_with(next_match="确认邀请", stay_match="下一步")

    def test_cancel_back_on_dish_page_counts_as_done(self):
        """实录 2026-10-21：取消「已有 xx 生效中」后回到选择菜品页，右下角仍是「下一步」，算已吃过。"""
        task = Mock()
        task.box.center = "center"
        task.box.bottom_right = "bottom_right"
        state = {"dialog": "当前已有章鱼小丸子生效中，是否确认更换?"}

        def read(*, match, box=None, **kwargs):
            if isinstance(match, re.Pattern):
                return [object()] if match.search(state["dialog"]) else []
            if match == "下一步" and box == "bottom_right":
                return [object()]
            return []

        def cancel(**kwargs):
            state["dialog"] = ""
            return True

        task.ocr.side_effect = read
        task.wait_until.side_effect = lambda predicate, **kwargs: bool(predicate())
        task.wait_click_ocr.side_effect = cancel
        run = method("_skip_active_food_buff")
        self.assertIs(True, run(task, next_match="确认邀请", stay_match="下一步"))
        state["dialog"] = "当前已有章鱼小丸子生效中，是否确认更换?"
        task.screenshot.reset_mock()
        self.assertIs(False, run(task, next_match="确认邀请"))

    def test_only_identified_duplicate_food_dialog_is_cancelled(self):
        """Verify only identified duplicate food dialog is cancelled."""
        run = method("_skip_active_food_buff")
        for text, expected in [
            ("同名菜品已生效，番茄鱼汤可能覆盖已生效菜品，是否确认继续", True),
            ("是否离开活动层？", None),
            ("购买是否确认继续", None),
        ]:
            task = Mock()
            task.box.center = "center"
            state = {"dialog": text}

            def read(*, match, **kwargs):
                """仅返回当前重复提示或活动层 HUD 的模拟 OCR。"""
                if isinstance(match, re.Pattern):
                    return [object()] if match.search(state["dialog"]) else []
                if isinstance(match, list):
                    return ["Esc", "P", "M", "F1", "F2"]
                return []

            def cancel(**kwargs):
                """模拟点击取消并关闭重复提示。"""
                state["dialog"] = ""
                return True

            task.ocr.side_effect = read
            task.wait_until.side_effect = lambda predicate, **kwargs: bool(predicate())
            task.wait_click_ocr.side_effect = cancel
            self.assertIs(expected, run(task))
            if expected:
                self.assertEqual("取消", task.wait_click_ocr.call_args.kwargs["match"])
            else:
                task.wait_click_ocr.assert_not_called()

    def test_failed_cancel_never_reports_duplicate_food_handled(self):
        """Verify failed cancel never reports duplicate food handled."""
        task = Mock()
        task.wait_ocr.return_value = [object()]
        task.wait_click_ocr.return_value = False
        self.assertIs(False, method("_skip_active_food_buff")(task))

    def test_unfinished_drink_still_enters_make_flow(self):
        """Verify unfinished drink still enters make flow."""
        task = Mock()
        task.wait_ocr.return_value = [SimpleNamespace(name="茶歇一刻0/1")]
        task._skip_active_food_buff.return_value = None
        task.wait_click_ocr.side_effect = [True, False]
        result = method("do_food_flow")(
            task,
            enter_func=Mock(),
            entry_match="茶歇一刻",
            main_btn="制作",
            second_btn="确认",
            skip_end_match=["饮品加成"],
        )
        self.assertEqual("confirm", result)
        task.click_with_key.assert_called_once()

    def test_dialog_that_remains_after_cancel_is_failure(self):
        """Verify dialog that remains after cancel is failure."""
        task = Mock()
        task.ocr.return_value = [object()]
        task.wait_until.side_effect = lambda predicate, **kwargs: bool(predicate())
        self.assertIs(False, method("_skip_active_food_buff")(task))
