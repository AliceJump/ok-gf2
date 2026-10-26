"""复现助战误点装饰文字、详情遮挡和未入队仍开战；设备操作用状态桩替代。"""

import ast
import re
import unittest
import cv2
import numpy as np
import win32api
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.tasks.daily.daily_public_mixin import loop_covers


def load_methods(path, class_name):
    """Load production methods without initializing the game runtime."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    namespace = {
        "re": re,
        "cv2": cv2,
        "win32api": win32api,
        "win32gui": SimpleNamespace(ClientToScreen=lambda hwnd, point: point),
        "loop_covers": loop_covers,
        "attach_foreground": lambda hwnd, foreground: False,
    }
    # 模块级的正则常量和工具函数（如 chenyan_not_open_re、power_of）也一起带上；import 依赖游戏运行时，不执行
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.FunctionDef)):
            try:
                exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), namespace)
            except Exception:
                pass
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
    """Match fixture labels using OCR pattern forms."""
    if isinstance(pattern, (list, tuple)):
        return any(matched(p, text) for p in pattern)
    return bool(pattern.search(text)) if isinstance(pattern, re.Pattern) else pattern == text


class AssistDevice:
    def __init__(self, available=True, filter_readable=True, detail=False, confirm=True, candidates=None):
        """Initialize isolated candidate and page state."""
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
        self.frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    def __getattr__(self, name):
        """Bind production methods to the isolated device."""
        if name in battle:
            return battle[name].__get__(self, type(self))
        raise AttributeError(name)

    def box_of_screen(self, *bounds):
        """Retain screen bounds for fixture OCR calls."""
        return bounds

    def info_set(self, *args):
        """Ignore UI status updates in the isolated device."""
        pass

    def log_info(self, *args, **kwargs):
        """Ignore informational runtime logs in the isolated device."""
        pass

    def log_warning(self, *args, **kwargs):
        """Ignore runtime warnings in the isolated device."""
        pass

    def log_error(self, message, **kwargs):
        """Record errors for assertions on aborted selection."""
        self.errors.append(message)

    def screenshot(self, *args, **kwargs):
        """Avoid producing real screenshots during isolated tests."""
        pass

    def sleep(self, *args):
        """Avoid real delays or trigger cancellation in the hover fixture."""
        pass

    def _scroll_chenyan_list(self, count):
        """Keep the fixture stationary unless the test overrides scrolling."""
        pass

    def get_role_by_name(self, name):
        """Resolve fixture role attributes without loading game assets."""
        return next((attr for attr, names in self.roles_dict.items() if name in names), None)

    def click_relative(self, x, y, **kwargs):
        """Simulate attribute selection at observed fallback positions."""
        if self.page == "list" and 0.24 < y < 0.29 and 0.37 < x < 0.45:
            self.attr = "燃烧"
        elif self.page == "list" and 0.24 < y < 0.29 and 0.65 < x < 0.72:
            self.attr = "酸蚀"

    def visible(self):
        """Return OCR labels for the current simulated page."""
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
        """Return fixture boxes matching the visible page and requested text."""
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
        """Read the fixture page without real polling."""
        return self.ocr(*args, **kwargs)

    def wait_click_ocr(self, *args, match=None, **kwargs):
        """Find a fixture button and apply its page transition."""
        boxes = self.ocr(match=match)
        if not boxes:
            if kwargs.get("raise_if_not_found"):
                raise RuntimeError("button missing")
            return []
        self.click(boxes[0])
        return boxes

    def click(self, target, **kwargs):
        """Apply the selected fixture button or candidate transition."""
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
        """Close fixture details or a modal and return to the list."""
        self.page = "list"

    def auto_battle(self, *args):
        """Record battle starts without interacting with the game."""
        self.battles += 1


class ChenyanAssistTest(unittest.TestCase):
    def test_ots14_precedes_available_weimaxi_na_across_attributes(self):
        """Verify ots14 precedes available weimaxi na across attributes."""
        task = AssistDevice(candidates=["威玛西娜", "OTs-14"])
        original_visible = task.visible
        task.visible = lambda: (
            original_visible() + ["威玛西娜"] if task.page == "list" and task.attr == "物理" else original_visible()
        )
        self.assertTrue(task.choose_chenyan(2))
        self.assertEqual("OTs-14", task.chosen)
        self.assertNotIn("威玛西娜", task.clicked)

    def test_missing_ots14_returns_to_original_first_choice(self):
        """Verify missing ots14 returns to original first choice."""
        task = AssistDevice(candidates=["威玛西娜"])
        original_visible = task.visible
        task.visible = lambda: (
            original_visible() + ["威玛西娜"] if task.page == "list" and task.attr == "物理" else original_visible()
        )
        self.assertTrue(task.choose_chenyan(2))
        self.assertEqual("威玛西娜", task.chosen)

    def test_ots14_search_accepts_uppercase_ocr(self):
        """Verify ots14 search accepts uppercase ocr."""
        task = AssistDevice(candidates=["OTS-14"])
        self.assertTrue(task.choose_chenyan(1))
        self.assertEqual("OTS-14", task.chosen)

    def test_unreadable_attributes_restore_list_after_failed_join(self):
        """Verify unreadable attributes restore list after failed join."""
        task = AssistDevice(filter_readable=False)
        task.page = "card"
        task.attr = "酸蚀"
        self.assertIs(False, battle["_restore_chenyan_list"](task))
        self.assertEqual("list", task.page)
        self.assertEqual([], task.errors)

    def test_unreadable_attributes_accept_empty_list_with_title(self):
        """An empty attribute page remains a recoverable assist list."""
        task = AssistDevice(filter_readable=False, available=False)
        task.page = "list"
        self.assertTrue(battle["_is_chenyan_list"](task))

    def test_conflict_with_unreadable_empty_attribute_continues_to_next_attribute(self):
        """Cancel a duplicate on an empty OCR page, then join another attribute."""
        task = AssistDevice(filter_readable=False, candidates=["可露凯", "新助战"])
        cancelled = []
        original_visible = task.visible
        original_click = task.click
        original_wait_click = task.wait_click_ocr

        def visible():
            """Model visible."""
            if task.page != "list":
                return original_visible()
            names = ["班组助战", "NMU", "庆", "😂"]
            if task.attr == "酸蚀" and not cancelled:
                names.append("可露凯")
            elif task.attr == "燃烧":
                names.append("新助战")
            return names

        def click(target, **kwargs):
            """Model click."""
            original_click(target, **kwargs)
            if task.clicked[-1] == "入队" and task.chosen == "可露凯":
                task.page = "duplicate"

        def wait_click(*args, match=None, **kwargs):
            """Model wait click."""
            if match == "取消" and task.page == "duplicate":
                cancelled.append(True)
                task.page = "list"
                return [SimpleNamespace(name="取消")]
            return original_wait_click(*args, match=match, **kwargs)

        task.visible = visible
        task.click = click
        task.click_box = click
        task.wait_click_ocr = wait_click
        self.assertIs(True, task.choose_chenyan(1))
        self.assertTrue(cancelled)
        self.assertEqual("新助战", task.chosen)
        self.assertEqual(1, task.battles)
        self.assertEqual([], task.errors)

    def test_missing_assist_title_is_not_a_recoverable_list(self):
        """Card OCR alone must not authorize list recovery on an unknown page."""
        task = AssistDevice()
        task.page = "list"
        original_visible = task.visible
        task.visible = lambda: [name for name in original_visible() if name != "班组助战"]
        self.assertFalse(task._is_chenyan_list())

    def test_two_empty_pages_stop_after_one_scroll(self):
        """Verify two empty pages stop after one scroll."""
        task = AssistDevice()
        scrolls = []
        task.ocr = lambda *args, **kwargs: []
        task._scroll_chenyan_list = scrolls.append
        self.assertIsNone(battle["_find_chenyan_assist"](task, "妮基塔"))
        self.assertEqual([1], scrolls)

    def test_same_role_and_slot_on_different_cards_keeps_searching(self):
        """Repeated role labels must not hide a target on a later page."""
        for empty_ocr in (False, True):
            with self.subTest(empty_ocr=empty_ocr):
                task = AssistDevice()
                page = [0]
                target = SimpleNamespace(name="妮基塔")

                def scroll(count):
                    """Change card pixels while preserving OCR names and slots."""
                    page[0] += 1
                    task.frame[300:450, 300:450] = 100 * page[0]

                task._scroll_chenyan_list = scroll
                task.ocr = lambda *args, **kwargs: (
                    [target] if page[0] == 2 else ([] if empty_ocr else [SimpleNamespace(name="春田", x=700, y=400)])
                )
                self.assertIs(target, task._find_chenyan_assist("妮基塔"))
                self.assertEqual(2, page[0])

    def test_unavailable_frame_does_not_prove_list_stopped(self):
        """Keep the bounded search running when page images cannot be read."""
        task = AssistDevice()
        task.frame = None
        task.ocr = lambda *args, **kwargs: []
        scrolls = []
        task._scroll_chenyan_list = scrolls.append
        self.assertIsNone(task._find_chenyan_assist("妮基塔"))
        self.assertEqual(99, len(scrolls))

    def test_small_capture_noise_still_stops_at_bottom(self):
        """Small pixel noise must not turn a stationary list into 100 scrolls."""
        task = AssistDevice()
        scrolls = []
        task.ocr = lambda *args, **kwargs: [SimpleNamespace(name="春田", x=700, y=400)]

        def scroll(count):
            """Model minor capture noise on the same cards."""
            scrolls.append(count)
            task.frame[:] = 2

        task._scroll_chenyan_list = scroll
        self.assertIsNone(task._find_chenyan_assist("妮基塔"))
        self.assertEqual([1], scrolls)

    def test_card_snapshot_scales_and_ignores_area_outside_list(self):
        """Use the same card crop at 1080p, 1440p and 2160p."""
        for width, height in ((1920, 1080), (2560, 1440), (3840, 2160)):
            with self.subTest(size=(width, height)):
                task = AssistDevice()
                task.frame = np.zeros((height, width, 3), dtype=np.uint8)
                task.frame[int(height * 0.4) : int(height * 0.6), int(width * 0.3) : int(width * 0.5)] = 180
                before = task._chenyan_list_snapshot()
                self.assertEqual((144, 256, 3), before.shape)
                task.frame[: int(height * 0.2)] = 255
                np.testing.assert_array_equal(before, task._chenyan_list_snapshot())
                task.frame[int(height * 0.4) : int(height * 0.6), int(width * 0.3) : int(width * 0.5)] = 50
                self.assertGreater((cv2.absdiff(before, task._chenyan_list_snapshot()).max(axis=2) > 12).mean(), 0.005)

    def test_unreadable_attribute_keeps_burning_and_corrosion_distinct(self):
        """Verify unreadable attribute keeps burning and corrosion distinct."""
        task = AssistDevice(filter_readable=False)
        task.page = "list"
        for attr in ("燃烧", "酸蚀"):
            with self.subTest(attr=attr):
                self.assertTrue(battle["_select_chenyan_attribute"](task, attr))
                self.assertEqual(attr, task.attr)

    def test_named_assist_searches_lower_pages_and_stops_when_found(self):
        """Verify named assist searches lower pages and stops when found."""
        task = AssistDevice()
        task.page = "list"
        page = [0]
        scrolls = []

        def scroll(count):
            """Advance the fixture page so search can observe new candidates."""
            scrolls.append(count)
            page[0] += 1

        task._scroll_chenyan_list = scroll
        target = SimpleNamespace(name="妮基塔")
        task.ocr = lambda *args, **kwargs: (
            [target] if page[0] == 2 else [SimpleNamespace(name="春田", x=700, y=900 - page[0] * 100)]
        )
        self.assertIs(target, battle["_find_chenyan_assist"](task, "妮基塔"))
        self.assertEqual([1, 1], scrolls)

    def test_search_reaches_assist_far_below_initial_view(self):
        """Verify search reaches assist far below initial view."""
        task = AssistDevice()
        distance = [0]
        target = SimpleNamespace(name="妮基塔")

        def scroll(count):
            """Advance the fixture page so search can observe new candidates."""
            distance[0] += abs(count)

        task._scroll_chenyan_list = scroll
        task.ocr = lambda *args, **kwargs: (
            [target] if distance[0] >= 30 else [SimpleNamespace(name="春田", x=700, y=900 - distance[0] * 100)]
        )
        self.assertIs(target, battle["_find_chenyan_assist"](task, "妮基塔"))

    def test_visible_candidates_exclude_level_stats_and_short_decorations(self):
        """Verify visible candidates exclude level stats and short decorations."""
        task = AssistDevice()
        labels = ["威玛西娜", "心28628", "V.60", "F8", "AW", "OTs-14"]
        task.ocr = lambda *args, **kwargs: [SimpleNamespace(name=name) for name in labels]
        self.assertEqual(["威玛西娜", "OTs-14"], [box.name for box in battle["_chenyan_candidates"](task)])

    def test_search_stops_when_list_remains_at_bottom(self):
        """Verify search stops when list remains at bottom."""
        task = AssistDevice()
        scrolls = []
        task._scroll_chenyan_list = scrolls.append
        task.ocr = lambda *args, **kwargs: [] if kwargs.get("match") else [SimpleNamespace(name="春田", x=700, y=900)]
        self.assertIsNone(battle["_find_chenyan_assist"](task, "妮基塔"))
        self.assertEqual([1], scrolls)

    def test_visible_target_does_not_scroll_at_all(self):
        """Verify visible target does not scroll at all."""
        task = AssistDevice()
        target = SimpleNamespace(name="妮基塔")
        task.ocr = lambda *args, **kwargs: [target]
        scrolls = []
        task._scroll_chenyan_list = scrolls.append
        self.assertIs(target, battle["_find_chenyan_assist"](task, "妮基塔"))
        self.assertEqual([], scrolls)

    def test_duplicate_modal_over_list_is_not_a_usable_list(self):
        """Verify duplicate modal over list is not a usable list."""
        task = AssistDevice()
        task.visible = lambda: ["班组助战", "物理", "浊刻", "队伍中有相同角色，是否进行替换", "确认", "取消"]
        self.assertFalse(battle["_is_chenyan_list"](task))

    def test_paused_search_sends_no_mouse_input(self):
        """Verify paused search sends no mouse input."""
        task = AssistDevice()
        task.executor = SimpleNamespace(paused=True)
        scrolls = []
        task._scroll_chenyan_list = scrolls.append
        self.assertIsNone(battle["_find_chenyan_assist"](task, "妮基塔"))
        self.assertEqual([], scrolls)

    def make_scroll_task(self, width=1920, height=1080, foreground=99):
        """Mock only the Win32 boundary while keeping the real scroll method."""
        task = AssistDevice()
        task.is_adb = lambda: False
        task.width, task.height = width, height
        task.hwnd = SimpleNamespace(hwnd=123)
        task.executor = SimpleNamespace(paused=False, interaction=SimpleNamespace(do_scroll=Mock()))
        state = {"foreground": foreground, "cursor": (1500, 800)}
        gui, api = Mock(), Mock()
        gui.GetForegroundWindow.side_effect = lambda: state["foreground"]
        gui.SetForegroundWindow.side_effect = lambda hwnd: state.update(foreground=hwnd)
        gui.ClientToScreen.side_effect = lambda hwnd, point: (point[0] + 50, point[1] + 80)
        gui.IsWindow.return_value = True
        api.GetCursorPos.side_effect = lambda: state["cursor"]
        api.SetCursorPos.side_effect = lambda point: state.update(cursor=point)
        return task, state, gui, api

    def test_real_wheel_targets_assist_cards_at_16_by_9_sizes(self):
        for width, height in ((1920, 1080), (2560, 1440), (3840, 2160)):
            with self.subTest(size=(width, height)):
                task, state, gui, api = self.make_scroll_task(width, height)
                expected = (int(width * 0.65) + 50, int(height * 0.60) + 80)
                observed = []
                task.executor.interaction.do_scroll.side_effect = lambda x, y, count: observed.append(
                    (x, y, count, state["foreground"], state["cursor"])
                )
                with patch.dict(battle, {"win32gui": gui, "win32api": api}):
                    self.assertTrue(battle["_scroll_chenyan_list"](task, 1))
                self.assertEqual([(int(width * 0.65), int(height * 0.60), -3, 123, expected)], observed)
                self.assertEqual({"foreground": 99, "cursor": (1500, 800)}, state)

    def test_search_reads_one_frame_per_step(self):
        """Verify search reads one frame per step."""
        task = AssistDevice()
        reads = []
        target = SimpleNamespace(name="妮基塔")
        task.ocr = lambda *args, **kwargs: reads.append(1) or [target]
        self.assertIs(target, battle["_find_chenyan_assist"](task, "妮基塔"))
        self.assertEqual([1], reads)

    def test_cancel_during_hover_restores_window_without_scrolling(self):
        task, state, gui, api = self.make_scroll_task()
        task.executor.interaction.do_scroll = Mock()
        task.sleep = lambda seconds: (_ for _ in ()).throw(RuntimeError("task stopped")) if seconds == 0.1 else None
        with (
            patch.dict(battle, {"win32gui": gui, "win32api": api}),
            self.assertRaisesRegex(RuntimeError, "task stopped"),
        ):
            battle["_scroll_chenyan_list"](task, 1)
        task.executor.interaction.do_scroll.assert_not_called()
        self.assertEqual({"foreground": 99, "cursor": (1500, 800)}, state)

    def test_failed_foreground_activation_sends_no_wheel(self):
        task, state, gui, api = self.make_scroll_task()
        gui.SetForegroundWindow.side_effect = lambda hwnd: None
        task.executor.interaction.do_scroll = Mock()
        with patch.dict(battle, {"win32gui": gui, "win32api": api}), self.assertRaisesRegex(RuntimeError, "前台"):
            battle["_scroll_chenyan_list"](task, 1)
        task.executor.interaction.do_scroll.assert_not_called()
        self.assertEqual({"foreground": 99, "cursor": (1500, 800)}, state)

    def test_foreground_activation_exception_reports_failure_without_wheel(self):
        task, state, gui, api = self.make_scroll_task()
        activation_error = OSError("foreground locked")
        gui.SetForegroundWindow.side_effect = activation_error
        with patch.dict(battle, {"win32gui": gui, "win32api": api}):
            with self.assertRaisesRegex(RuntimeError, "助战列表滚动失败：游戏未进入前台") as raised:
                battle["_scroll_chenyan_list"](task, 1)
        self.assertIs(activation_error, raised.exception.__cause__)
        task.executor.interaction.do_scroll.assert_not_called()
        self.assertEqual({"foreground": 99, "cursor": (1500, 800)}, state)

    def test_foreground_lock_falls_back_to_input_thread_attach(self):
        """前台锁拒绝直接切换时，挂到前台窗口的输入线程上切过去再滚。"""
        task, state, gui, api = self.make_scroll_task()
        gui.SetForegroundWindow.side_effect = OSError("foreground locked")
        attach = Mock(side_effect=lambda hwnd, foreground: state.update(foreground=hwnd) or True)
        task.executor.interaction.do_scroll = Mock()
        with patch.dict(battle, {"win32gui": gui, "win32api": api, "attach_foreground": attach}):
            self.assertTrue(battle["_scroll_chenyan_list"](task, 1))
        attach.assert_called_once_with(123, 99)
        task.executor.interaction.do_scroll.assert_called_once()
        self.assertEqual((1500, 800), state["cursor"])

    def test_scroll_falls_back_to_public_wheel_with_client_coordinates(self):
        task, state, gui, api = self.make_scroll_task()
        observed = []
        task.executor.interaction = SimpleNamespace(
            scroll=lambda x, y, count: observed.append((x, y, count, state["foreground"], state["cursor"]))
        )
        with patch.dict(battle, {"win32gui": gui, "win32api": api}):
            self.assertTrue(battle["_scroll_chenyan_list"](task, 1))
        self.assertEqual([(1248, 648, -3, 123, (1298, 728))], observed)
        self.assertEqual({"foreground": 99, "cursor": (1500, 800)}, state)

    def test_pause_during_hover_restores_focus_without_scrolling(self):
        task, state, gui, api = self.make_scroll_task()
        task.executor.interaction.do_scroll = Mock()
        task.sleep = lambda seconds: setattr(task.executor, "paused", True) if seconds == 0.1 else None
        with patch.dict(battle, {"win32gui": gui, "win32api": api}):
            self.assertFalse(battle["_scroll_chenyan_list"](task, 1))
        task.executor.interaction.do_scroll.assert_not_called()
        self.assertEqual({"foreground": 99, "cursor": (1500, 800)}, state)

    def test_already_foreground_keeps_game_active(self):
        task, state, gui, api = self.make_scroll_task(foreground=123)
        task.executor.interaction.do_scroll = Mock()
        with patch.dict(battle, {"win32gui": gui, "win32api": api}):
            self.assertTrue(battle["_scroll_chenyan_list"](task, 1))
        task.executor.interaction.do_scroll.assert_called_once_with(int(task.width * 0.65), int(task.height * 0.60), -3)
        gui.SetForegroundWindow.assert_not_called()
        self.assertEqual({"foreground": 123, "cursor": (1500, 800)}, state)

    def test_stop_exception_propagates_before_mouse_input(self):
        """Verify stop exception propagates before mouse input."""
        task = AssistDevice()
        events = []
        task.scroll_relative = lambda *args: events.append(args)

        def stopped_sleep(seconds):
            """Raise cancellation before any mouse input occurs."""
            raise RuntimeError("task stopped")

        task.sleep = stopped_sleep
        with self.assertRaisesRegex(RuntimeError, "task stopped"):
            battle["_scroll_chenyan_list"](task, 1)
        self.assertEqual([], events)

    def test_adb_scroll_keeps_swipe_without_message_backend(self):
        """移动端继续使用滑动手势，不依赖桌面窗口消息。"""
        task = AssistDevice()
        task.is_adb = lambda: True
        task.swipe_relative = Mock()
        self.assertTrue(battle["_scroll_chenyan_list"](task, 1))
        task.swipe_relative.assert_called_once_with(0.65, 0.72, 0.65, 0.40, duration=0.3)

    def test_invalid_game_window_sends_no_wheel(self):
        task, state, gui, api = self.make_scroll_task()
        gui.IsWindow.return_value = False
        task.executor.interaction.do_scroll = Mock()
        with patch.dict(battle, {"win32gui": gui, "win32api": api}), self.assertRaisesRegex(RuntimeError, "窗口"):
            battle["_scroll_chenyan_list"](task, 1)
        task.executor.interaction.do_scroll.assert_not_called()
        self.assertEqual({"foreground": 99, "cursor": (1500, 800)}, state)

    def test_missing_real_wheel_backend_fails_before_activation(self):
        task, state, gui, api = self.make_scroll_task()
        task.executor.interaction = SimpleNamespace()
        with patch.dict(battle, {"win32gui": gui, "win32api": api}), self.assertRaisesRegex(RuntimeError, "真实滚轮"):
            battle["_scroll_chenyan_list"](task, 1)
        gui.SetForegroundWindow.assert_not_called()
        self.assertEqual({"foreground": 99, "cursor": (1500, 800)}, state)

    def test_missing_join_on_list_does_not_back_out_of_list(self):
        """Verify missing join on list does not back out of list."""
        task = AssistDevice()
        task.page = "list"
        task.click = lambda target, **kwargs: None
        task.back = lambda **kwargs: setattr(task, "page", "team")
        self.assertIs(False, battle["_try_chenyan_assist"](task, SimpleNamespace(name="托洛洛"), set()))
        self.assertEqual("list", task.page)

    def test_no_available_assist_never_clicks_decoration_or_starts_battle(self):
        """Verify no available assist never clicks decoration or starts battle."""
        task = AssistDevice(available=False)
        self.assertIs(False, battle["choose_chenyan"](task, 1))
        self.assertEqual(0, task.battles)
        self.assertFalse(set(task.clicked) & {"NMU", "庆", "😂"})

    def test_unreadable_attribute_can_still_select_available_assist(self):
        """Verify unreadable attribute can still select available assist."""
        task = AssistDevice(filter_readable=False)
        self.assertIs(True, battle["choose_chenyan"](task, 1))
        self.assertEqual("battle", task.page)
        self.assertEqual(1, task.battles)
        self.assertIn("可露凯", task.clicked)

    def test_missing_team_confirmation_does_not_start_battle(self):
        """Verify missing team confirmation does not start battle."""
        task = AssistDevice(confirm=False)
        self.assertIs(False, battle["choose_chenyan"](task, 1))
        self.assertEqual(0, task.battles)

    def test_fallback_tries_visible_unknown_role_after_duplicate(self):
        """Verify fallback tries visible unknown role after duplicate."""
        task = AssistDevice(candidates=["春田", "新助战"])
        self.assertIs(True, battle["choose_chenyan"](task, 1))
        self.assertEqual("新助战", task.chosen)
        self.assertEqual(1, task.battles)

    def test_details_are_closed_before_trying_next_visible_role(self):
        """Verify details are closed before trying next visible role."""
        task = AssistDevice()
        task.page = "list"
        task.click = lambda target, **kwargs: setattr(task, "page", "detail")
        self.assertFalse(battle["_try_chenyan_assist"](task, SimpleNamespace(name="OTs-14"), set()))
        self.assertEqual("list", task.page)

    def test_english_details_are_closed_before_retry(self):
        """Verify english details are closed before retry."""
        task = AssistDevice()
        task.page = "list"
        task.visible = lambda: ["班组助战", "Firepower Preview", "Combat Effectiveness"]
        task.click = lambda target, **kwargs: setattr(task, "page", "detail")
        self.assertFalse(battle["_try_chenyan_assist"](task, SimpleNamespace(name="OTs-14"), set()))
        self.assertEqual("list", task.page)

    def test_confirmation_timeout_is_closed_before_retry(self):
        """Verify confirmation timeout is closed before retry."""
        task = AssistDevice(confirm=False)
        self.assertFalse(battle["_try_chenyan_assist"](task, SimpleNamespace(name="可露凯"), set()))
        self.assertEqual("list", task.page)

    def test_same_row_uses_left_to_right_despite_ocr_height_jitter(self):
        """Verify same row uses left to right despite ocr height jitter."""
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
        """Verify fallback clicks rows from left to right until usable."""
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
            """Reject earlier candidates and accept the usable fixture role."""
            tried.append(char.name)
            if char.name == "左下":
                task.page = "joined"
                return True
            return False

        task._try_chenyan_assist = try_candidate
        self.assertIs(True, battle["choose_chenyan"](task, 1))
        self.assertEqual(["左上", "右上", "左下"], tried)

    def test_unrecoverable_details_stop_before_clicking_next_candidate(self):
        """Verify unrecoverable details stop before clicking next candidate."""
        task = AssistDevice()
        task.page = "list"
        task.click = lambda target, **kwargs: setattr(task, "page", "detail")
        task.back = lambda **kwargs: None
        self.assertIsNone(battle["_try_chenyan_assist"](task, SimpleNamespace(name="OTs-14"), set()))

    def test_start_timeout_reports_state_instead_of_none_subscript(self):
        """Verify start timeout reports state instead of none subscript."""
        task = SimpleNamespace(
            box=SimpleNamespace(bottom="bottom"),
            info_set=lambda *args: None,
            skip_dialogs=lambda **kwargs: None,
            debug_shot=lambda *args, **kwargs: None,
        )
        with self.assertRaisesRegex(RuntimeError, "作战|战斗"):
            base["auto_battle"](task)


if __name__ == "__main__":
    unittest.main()
