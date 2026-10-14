"""复现助战误点装饰文字、详情遮挡和未入队仍开战；设备操作用状态桩替代。"""

import ast
import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def load_methods(path, class_name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    namespace = {"re": re}
    methods = [
        n
        for n in cls.body
        if isinstance(n, ast.FunctionDef)
        and n.name != "__init__"
        and (class_name != "BaseGfTask" or n.name == "auto_battle")
    ]
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(path), "exec"), namespace)
    return namespace


root = Path(__file__).resolve().parents[1]
battle = load_methods(root / "src/tasks/daily/daily_battle_mixin.py", "DailyBattleMixin")
base = load_methods(root / "src/core/BaseGfTask.py", "BaseGfTask")


def matched(pattern, text):
    if isinstance(pattern, (list, tuple)):
        return any(matched(p, text) for p in pattern)
    return bool(pattern.search(text)) if isinstance(pattern, re.Pattern) else pattern == text


class AssistDevice:
    def __init__(self, available=True, filter_readable=True, detail=False, confirm=True, candidates=None):
        self.roles_dict = {"物理": ["威玛西娜"], "酸蚀": ["可露凯"], "浊刻": ["春田", "托洛洛"]}
        self.box = SimpleNamespace(top_right="top", bottom_right="bottom", bottom="bottom")
        self.page = "detail" if detail else "team"
        self.available = available
        self.filter_readable = filter_readable
        self.confirm = confirm
        self.attr = "物理"
        self.clicked = []
        self.battles = 0
        self.errors = []
        self.candidates = candidates
        self.chosen = None

    def __getattr__(self, name):
        if name in battle:
            return battle[name].__get__(self, type(self))
        raise AttributeError(name)

    def box_of_screen(self, *bounds):
        return bounds

    def info_set(self, *args):
        pass

    def log_info(self, *args, **kwargs):
        pass

    def log_warning(self, *args, **kwargs):
        pass

    def log_error(self, message, **kwargs):
        self.errors.append(message)

    def screenshot(self, *args, **kwargs):
        pass

    def sleep(self, *args):
        pass

    def _scroll_chenyan_list(self, count):
        pass

    def get_role_by_name(self, name):
        return next((attr for attr, names in self.roles_dict.items() if name in names), None)

    def click_relative(self, x, y, **kwargs):
        if self.page == "list" and 0.24 < y < 0.29 and 0.37 < x < 0.45:
            self.attr = "燃烧"
        elif self.page == "list" and 0.24 < y < 0.29 and 0.65 < x < 0.72:
            self.attr = "酸蚀"

    def visible(self):
        if self.page == "detail":
            return ["火控预演方案", "作战效能", "OTs-14"]
        if self.page == "duplicate":
            return ["确认"]
        if self.page == "joined":
            return ["确定"] if self.confirm else []
        if self.page == "card":
            return ["入队"]
        if self.page == "list":
            labels = ["班组助战", "NMU", "庆", "😂"]
            if self.filter_readable:
                labels.extend(self.roles_dict)
            if self.available and self.attr == "酸蚀":
                labels.extend(self.candidates or ["可露凯"])
            return labels
        return ["助战"]

    def ocr(self, *args, match=None, **kwargs):
        if match is None:
            match = re.compile(".*")
        labels = self.visible()
        if args and args[1] >= 0.31:
            labels = [text for text in labels if text not in ("班组助战", "NMU", "庆", "😂", *self.roles_dict)]
        return [
            SimpleNamespace(name=text, x=index * 300, y=720, width=80, height=30)
            for index, text in enumerate(labels)
            if matched(match, text)
        ]

    def wait_ocr(self, *args, **kwargs):
        return self.ocr(*args, **kwargs)

    def wait_click_ocr(self, *args, match=None, **kwargs):
        boxes = self.ocr(match=match)
        if not boxes:
            if kwargs.get("raise_if_not_found"):
                raise RuntimeError("button missing")
            return []
        self.click(boxes[0])
        return boxes

    def click(self, target, **kwargs):
        if isinstance(target, list):
            target = target[0]
        name = target.name
        self.clicked.append(name)
        if name == "助战":
            self.page = "list"
        elif name in self.roles_dict:
            self.attr = name
        elif name in (self.candidates or ["可露凯"]):
            self.chosen = name
            self.page = "card"
        elif name == "入队":
            self.page = "duplicate" if self.chosen == "春田" else "joined"
        elif name == "确定":
            self.page = "battle"
        elif name in ("NMU", "庆", "😂"):
            self.page = "detail"

    click_box = click

    def back(self, **kwargs):
        self.page = "list"

    def auto_battle(self, *args):
        self.battles += 1


class ChenyanAssistTest(unittest.TestCase):
    def test_unreadable_attribute_keeps_burning_and_corrosion_distinct(self):
        task = AssistDevice(filter_readable=False)
        task.page = "list"
        for attr in ("燃烧", "酸蚀"):
            with self.subTest(attr=attr):
                self.assertTrue(battle["_select_chenyan_attribute"](task, attr))
                self.assertEqual(attr, task.attr)

    def test_named_assist_searches_lower_pages_and_stops_when_found(self):
        task = AssistDevice()
        task.page = "list"
        page = [0]
        scrolls = []

        def scroll(count):
            scrolls.append(count)
            page[0] += 1

        task._scroll_chenyan_list = scroll
        target = SimpleNamespace(name="妮基塔")
        task.ocr = lambda *args, **kwargs: [target] if page[0] == 2 else []
        self.assertIs(target, battle["_find_chenyan_assist"](task, "妮基塔"))
        self.assertEqual([1, 1], scrolls)

    def test_search_reaches_assist_far_below_initial_view(self):
        task = AssistDevice()
        distance = [0]
        target = SimpleNamespace(name="妮基塔")

        def scroll(count):
            distance[0] += abs(count)

        task._scroll_chenyan_list = scroll
        task.ocr = lambda *args, **kwargs: [target] if distance[0] >= 30 else []
        self.assertIs(target, battle["_find_chenyan_assist"](task, "妮基塔"))

    def test_visible_candidates_exclude_level_stats_and_short_decorations(self):
        task = AssistDevice()
        labels = ["威玛西娜", "心28628", "V.60", "F8", "AW", "OTs-14"]
        task.ocr = lambda *args, **kwargs: [SimpleNamespace(name=name) for name in labels]
        self.assertEqual(["威玛西娜", "OTs-14"], [box.name for box in battle["_chenyan_candidates"](task)])

    def test_search_stops_when_list_remains_at_bottom(self):
        task = AssistDevice()
        scrolls = []
        task._scroll_chenyan_list = scrolls.append
        task.ocr = lambda *args, **kwargs: [] if kwargs.get("match") else [SimpleNamespace(name="春田", x=700, y=900)]
        self.assertIsNone(battle["_find_chenyan_assist"](task, "妮基塔"))
        self.assertEqual([1], scrolls)

    def test_visible_target_does_not_scroll_at_all(self):
        task = AssistDevice()
        target = SimpleNamespace(name="妮基塔")
        task.ocr = lambda *args, **kwargs: [target]
        scrolls = []
        task._scroll_chenyan_list = scrolls.append
        self.assertIs(target, battle["_find_chenyan_assist"](task, "妮基塔"))
        self.assertEqual([], scrolls)

    def test_duplicate_modal_over_list_is_not_a_usable_list(self):
        task = AssistDevice()
        task.visible = lambda: ["班组助战", "物理", "浊刻", "队伍中有相同角色，是否进行替换", "确认", "取消"]
        self.assertFalse(battle["_is_chenyan_list"](task))

    def test_paused_search_sends_no_mouse_input(self):
        task = AssistDevice()
        task.executor = SimpleNamespace(paused=True)
        scrolls = []
        task._scroll_chenyan_list = scrolls.append
        self.assertIsNone(battle["_find_chenyan_assist"](task, "妮基塔"))
        self.assertEqual([], scrolls)

    def test_each_scroll_is_one_event_without_activation_loop(self):
        task = AssistDevice()
        task.is_adb = lambda: False
        events = []
        task.scroll_relative = lambda x, y, count: events.append(count)
        task.width = 3840
        task.height = 2160
        task.hwnd = SimpleNamespace(hwnd=123)
        task.move_relative = lambda *args: None
        calls = []

        def in_window(hwnd, callback):
            calls.append("activate")
            try:
                return callback()
            finally:
                calls.append("restore")

        helpers = SimpleNamespace(
            run_in_window=in_window,
            run_at_window_pos=lambda hwnd, callback, *args, **kwargs: callback(),
        )
        with patch.dict(sys.modules, {"src.interaction.Mouse": helpers}):
            self.assertTrue(battle["_scroll_chenyan_list"](task, 120))
        self.assertEqual([-3], events)
        self.assertEqual(["activate", "restore"], calls)

    def test_search_reads_one_frame_per_step(self):
        task = AssistDevice()
        reads = []
        target = SimpleNamespace(name="妮基塔")
        task.ocr = lambda *args, **kwargs: reads.append(1) or [target]
        self.assertIs(target, battle["_find_chenyan_assist"](task, "妮基塔"))
        self.assertEqual([1], reads)

    def test_cancel_during_hover_restores_window_without_scrolling(self):
        task = AssistDevice()
        task.is_adb = lambda: False
        task.width, task.height = 3840, 2160
        task.hwnd = SimpleNamespace(hwnd=123)
        task.move_relative = lambda *args: None
        events = []
        task.scroll_relative = lambda *args: events.append(args)
        restored = []

        def sleep(seconds):
            if seconds == 0.1:
                raise RuntimeError("task stopped")

        def in_window(hwnd, callback):
            try:
                return callback()
            finally:
                restored.append(True)

        task.sleep = sleep
        helpers = SimpleNamespace(
            run_in_window=in_window,
            run_at_window_pos=lambda hwnd, callback, *args, **kwargs: callback(),
        )
        with (
            patch.dict(sys.modules, {"src.interaction.Mouse": helpers}),
            self.assertRaisesRegex(RuntimeError, "task stopped"),
        ):
            battle["_scroll_chenyan_list"](task, 1)
        self.assertEqual([], events)
        self.assertEqual([True], restored)

    def test_stop_exception_propagates_before_mouse_input(self):
        task = AssistDevice()
        events = []
        task.scroll_relative = lambda *args: events.append(args)

        def stopped_sleep(seconds):
            raise RuntimeError("task stopped")

        task.sleep = stopped_sleep
        with self.assertRaisesRegex(RuntimeError, "task stopped"):
            battle["_scroll_chenyan_list"](task, 1)
        self.assertEqual([], events)

    def test_missing_join_on_list_does_not_back_out_of_list(self):
        task = AssistDevice()
        task.page = "list"
        task.click = lambda target, **kwargs: None
        task.back = lambda **kwargs: setattr(task, "page", "team")
        self.assertIs(False, battle["_try_chenyan_assist"](task, SimpleNamespace(name="托洛洛"), set()))
        self.assertEqual("list", task.page)

    def test_no_available_assist_never_clicks_decoration_or_starts_battle(self):
        task = AssistDevice(available=False)
        self.assertIs(False, battle["choose_chenyan"](task, 1))
        self.assertEqual(0, task.battles)
        self.assertFalse(set(task.clicked) & {"NMU", "庆", "😂"})

    def test_unreadable_attribute_can_still_select_available_assist(self):
        task = AssistDevice(filter_readable=False)
        self.assertIs(True, battle["choose_chenyan"](task, 1))
        self.assertEqual("battle", task.page)
        self.assertEqual(1, task.battles)
        self.assertIn("可露凯", task.clicked)

    def test_missing_team_confirmation_does_not_start_battle(self):
        task = AssistDevice(confirm=False)
        self.assertIs(False, battle["choose_chenyan"](task, 1))
        self.assertEqual(0, task.battles)

    def test_fallback_tries_visible_unknown_role_after_duplicate(self):
        task = AssistDevice(candidates=["春田", "OTs-14"])
        self.assertIs(True, battle["choose_chenyan"](task, 1))
        self.assertEqual("OTs-14", task.chosen)
        self.assertEqual(1, task.battles)

    def test_details_are_closed_before_trying_next_visible_role(self):
        task = AssistDevice()
        task.page = "list"
        task.click = lambda target, **kwargs: setattr(task, "page", "detail")
        self.assertFalse(battle["_try_chenyan_assist"](task, SimpleNamespace(name="OTs-14"), set()))
        self.assertEqual("list", task.page)

    def test_english_details_are_closed_before_retry(self):
        task = AssistDevice()
        task.page = "list"
        task.visible = lambda: ["班组助战", "Firepower Preview", "Combat Effectiveness"]
        task.click = lambda target, **kwargs: setattr(task, "page", "detail")
        self.assertFalse(battle["_try_chenyan_assist"](task, SimpleNamespace(name="OTs-14"), set()))
        self.assertEqual("list", task.page)

    def test_confirmation_timeout_is_closed_before_retry(self):
        task = AssistDevice(confirm=False)
        self.assertFalse(battle["_try_chenyan_assist"](task, SimpleNamespace(name="可露凯"), set()))
        self.assertEqual("list", task.page)

    def test_same_row_uses_left_to_right_despite_ocr_height_jitter(self):
        task = AssistDevice(available=False)
        task.page = "list"
        boxes = [
            SimpleNamespace(name="右上", x=900, y=703, width=60, height=30),
            SimpleNamespace(name="左下", x=300, y=1100, width=60, height=30),
            SimpleNamespace(name="左上", x=300, y=710, width=60, height=30),
        ]
        ordered = battle["_order_chenyan_candidates"](task, boxes)
        self.assertEqual(["左上", "右上", "左下"], [box.name for box in ordered])

    def test_fallback_clicks_rows_from_left_to_right_until_usable(self):
        task = AssistDevice(available=False)
        boxes = [
            SimpleNamespace(name="右下", x=900, y=1100, width=60, height=30),
            SimpleNamespace(name="右上", x=900, y=703, width=60, height=30),
            SimpleNamespace(name="左下", x=300, y=1100, width=60, height=30),
            SimpleNamespace(name="左上", x=300, y=710, width=60, height=30),
        ]
        original_ocr = task.ocr
        task.ocr = lambda *args, **kwargs: boxes if args and args[1] >= 0.31 else original_ocr(*args, **kwargs)
        tried = []

        def try_candidate(char, duplicates):
            tried.append(char.name)
            if char.name == "左下":
                task.page = "joined"
                return True
            return False

        task._try_chenyan_assist = try_candidate
        self.assertIs(True, battle["choose_chenyan"](task, 1))
        self.assertEqual(["左上", "右上", "左下"], tried)

    def test_unrecoverable_details_stop_before_clicking_next_candidate(self):
        task = AssistDevice()
        task.page = "list"
        task.click = lambda target, **kwargs: setattr(task, "page", "detail")
        task.back = lambda **kwargs: None
        self.assertIsNone(battle["_try_chenyan_assist"](task, SimpleNamespace(name="OTs-14"), set()))

    def test_start_timeout_reports_state_instead_of_none_subscript(self):
        task = SimpleNamespace(
            box=SimpleNamespace(bottom="bottom"),
            info_set=lambda *args: None,
            skip_dialogs=lambda **kwargs: None,
        )
        with self.assertRaisesRegex(RuntimeError, "作战|战斗"):
            base["auto_battle"](task)


if __name__ == "__main__":
    unittest.main()
