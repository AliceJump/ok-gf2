import ast
import ctypes
import ctypes.wintypes
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

source = Path(__file__).resolve().parents[1] / "src/tasks/daily/daily_activity_mixin.py"
task_class = next(
    node
    for node in ast.parse(source.read_text(encoding="utf-8")).body
    if isinstance(node, ast.ClassDef) and node.name == "DailyActivityMixin"
)
methods = [
    node
    for node in task_class.body
    if isinstance(node, ast.FunctionDef)
    and node.name
    in (
        "activities",
        "_collect_supply_activities",
        "_ensure_supply_foreground",
        "_open_supply_activity",
        "_scroll_supply_menu",
        "_claim_supply_activity",
    )
]
namespace = {"re": re, "pop_ups": ["点击空白处关闭"]}
exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), namespace)


screens = {}


def run_in_window(hwnd, func, *args, **kwargs):
    screen = screens[hwnd]
    previous = screen.foreground
    active_and_send_mouse_delta(hwnd)
    try:
        return func(*args, **kwargs)
    finally:
        screen.foreground = previous
        if not previous:
            screen.restores += 1


def active_and_send_mouse_delta(hwnd, **kwargs):
    screen = screens[hwnd]
    if not screen.foreground:
        screen.activations += 1
        screen.foreground = True


def run_at_window_pos(hwnd, func, x, y, sleep_time=0.5):
    screen = screens[hwnd]
    previous = screen.physical_mouse
    screen.physical_mouse = (x, y)
    try:
        return func()
    finally:
        screen.physical_mouse = previous


namespace.update(
    run_in_window=run_in_window,
    run_at_window_pos=run_at_window_pos,
    active_and_send_mouse_delta=active_and_send_mouse_delta,
)


class SupplyScreen:
    activities = namespace["activities"]
    _collect_supply_activities = namespace["_collect_supply_activities"]
    _ensure_supply_foreground = namespace["_ensure_supply_foreground"]
    _open_supply_activity = namespace["_open_supply_activity"]
    _claim_supply_activity = namespace["_claim_supply_activity"]
    _scroll_supply_menu = namespace["_scroll_supply_menu"]

    def __init__(self, entries=None, remaining=None):
        self.entries = entries if entries is not None else {2: "情报补给", 4: "战前补给"}
        self.remaining = remaining if remaining is not None else {"情报补给": 2, "战前补给": 1}
        self.box = SimpleNamespace(_activities="entry", right="right", bottom="bottom")
        self.menu_page = 5  # The game remembers where the user last scrolled.
        self.width, self.height = 2560, 1600
        self.hwnd = SimpleNamespace(hwnd=id(self))
        screens[self.hwnd.hwnd] = self
        self.foreground = False
        self.activations = 0
        self.restores = 0
        self.physical_mouse = (1500, 800)
        self.hover_mouse = None
        self.ineffective_scrolls = []
        self.selected = None
        self.popup = False
        self.page_ok = True
        self.restore_page = True
        self.popup_ok = True
        self.stuck_button = False
        self.known_empty = True
        self.button_label = "领取"
        self.claims = []
        self.menu_checks = 0
        self.scrolls = []
        self.status = {}
        self.info_set = lambda key, value: self.status.update({key: value})
        self.log_info = Mock()
        self.sleep = Mock()
        self.ensure_main = Mock()

    def box_of_screen(self, *bounds):
        return bounds

    def tr(self, message):
        return message

    def move_relative(self, x, y):
        self.hover_mouse = (int(self.width * x), int(self.height * y))

    def scroll_relative(self, x, y, count):
        self.scrolls.append((x, y, count))
        target = (int(self.width * x), int(self.height * y))
        if not self.foreground or self.physical_mouse != target or self.hover_mouse != target:
            self.ineffective_scrolls.append(count)
            return
        self.menu_page = 0 if count > 0 else self.menu_page + 1

    def wait_click_ocr(self, *, match, box, **kwargs):
        if box == "entry":
            return True
        if isinstance(box, tuple):
            self.menu_checks += 1
            entry = self.entries.get(self.menu_page, "")
            if match.search(entry):
                self.selected = entry
                return True
            return False
        if box == "right" and self.remaining.get(self.selected, 0) and match.search(self.button_label):
            self.claims.append(self.selected)
            if not self.stuck_button:
                self.remaining[self.selected] -= 1
            self.popup = self.popup_ok
            return True
        return False

    def wait_ocr(self, *, match, box, **kwargs):
        if isinstance(match, list):
            return self.popup
        if self.page_ok and match.search(self.selected or ""):
            return True
        return self.known_empty and not self.remaining.get(self.selected, 0) and bool(match.search("已领取"))

    def wait_pop_up(self, **kwargs):
        self.popup = False
        self.page_ok = self.restore_page


class ActivitySupplyTest(unittest.TestCase):
    def test_finds_hidden_entries_and_claims_both_time_slots(self):
        task = SupplyScreen()
        self.assertIs(True, task.activities())
        self.assertEqual(["情报补给", "情报补给", "战前补给"], task.claims)
        self.assertEqual("已确认领取 2 次", task.status["情报补给"])
        self.assertEqual(2, sum(count > 0 for _, _, count in task.scrolls))
        self.assertGreater(task.menu_checks, 2)
        self.assertEqual([], task.ineffective_scrolls)
        self.assertFalse(task.foreground)
        self.assertEqual((1500, 800), task.physical_mouse)
        self.assertEqual(1, task.activations)
        self.assertEqual(1, task.restores)
        task.ensure_main.assert_called_once()

    def test_missing_entries_are_bounded_and_uncertain(self):
        task = SupplyScreen(entries={})
        self.assertEqual("待核查", task.activities())
        self.assertEqual(16, task.menu_checks)
        self.assertEqual([], task.claims)
        self.assertIn("未找到入口", task.status["情报补给"])
        task.ensure_main.assert_called_once()

    def test_focus_interruption_reactivates_without_restoring_between_scrolls(self):
        task = SupplyScreen()
        original = task.wait_click_ocr
        interrupted = False

        def click(**kwargs):
            nonlocal interrupted
            result = original(**kwargs)
            if isinstance(kwargs["box"], tuple) and not interrupted:
                task.foreground = False
                interrupted = True
            return result

        task.wait_click_ocr = click
        self.assertIs(True, task.activities())
        self.assertEqual(2, task.activations)
        self.assertEqual(1, task.restores)
        self.assertEqual([], task.ineffective_scrolls)

    def test_already_foreground_does_not_switch_windows(self):
        task = SupplyScreen()
        task.foreground = True
        self.assertIs(True, task.activities())
        self.assertEqual(0, task.activations)
        self.assertEqual(0, task.restores)
        self.assertTrue(task.foreground)

    def test_optional_prewar_event_can_be_absent(self):
        task = SupplyScreen(entries={2: "情报补给"})
        self.assertIs(True, task.activities())
        self.assertEqual(["情报补给", "情报补给"], task.claims)
        self.assertIn("未找到入口", task.status["战前补给"])

    def test_prewar_success_does_not_hide_missing_intelligence_supply(self):
        task = SupplyScreen(entries={4: "战前补给"})
        self.assertEqual("待核查", task.activities())
        self.assertEqual(["战前补给"], task.claims)
        self.assertIn("待核查", task.status["情报补给"])

    def test_wrong_page_never_clicks_a_claim_button(self):
        task = SupplyScreen()
        task.page_ok = False
        self.assertEqual("待核查", task.activities())
        self.assertEqual([], task.claims)

    def test_missing_popup_stops_without_repeating_uncertain_click(self):
        task = SupplyScreen(entries={2: "情报补给"})
        task.popup_ok = False
        self.assertEqual("待核查", task.activities())
        self.assertEqual(["情报补给"], task.claims)
        self.assertIn("未确认奖励弹窗", task.status["情报补给"])

    def test_already_claimed_is_never_clicked_as_claim(self):
        task = SupplyScreen(entries={2: "情报补给"}, remaining={"情报补给": 2})
        task.button_label = "已领取"
        task.wait_ocr = lambda *, match, **kwargs: (
            not isinstance(match, list) and bool(match.search("情报补给") or match.search("已领取"))
        )
        self.assertIs(True, task.activities())
        self.assertEqual([], task.claims)

    def test_unrecognized_state_is_uncertain(self):
        task = SupplyScreen(entries={2: "情报补给"}, remaining={})
        task.known_empty = False
        self.assertEqual("待核查", task.activities())
        self.assertIn("未识别", task.status["情报补给"])

    def test_lost_page_after_popup_is_uncertain(self):
        task = SupplyScreen(entries={2: "情报补给"})
        task.restore_page = False
        self.assertEqual("待核查", task.activities())
        self.assertEqual(["情报补给"], task.claims)

    def test_persistent_button_does_not_loop_forever(self):
        task = SupplyScreen(entries={2: "情报补给"})
        task.stuck_button = True
        self.assertEqual("待核查", task.activities())
        self.assertEqual(10, len(task.claims))

    def test_navigation_exception_still_restores_main(self):
        task = SupplyScreen()
        task.scroll_relative = Mock(side_effect=RuntimeError("menu unavailable"))
        with self.assertRaisesRegex(RuntimeError, "menu unavailable"):
            task.activities()
        task.ensure_main.assert_called_once()

    def test_daily_run_does_not_report_complete_for_missing_supply(self):
        from src.tasks.DailyTaskRunner import DailyTaskRunner
        from tests.TestDailyTaskRunner import StubTask

        task = StubTask({"活动情报补给": True})
        supply = SupplyScreen(entries={})
        runner = DailyTaskRunner(task, [("活动情报补给", supply.activities)])
        runner.run()
        self.assertEqual("待核查", runner.final_summary["status"])
        self.assertEqual(["活动情报补给"], runner.task_status["uncertain"])
        self.assertEqual([], runner.task_status["success"])


class NativeHoverTest(unittest.TestCase):
    def bridge(self):
        mouse_source = Path(__file__).resolve().parents[1] / "src/interaction/Mouse.py"
        methods = [
            node
            for node in ast.parse(mouse_source.read_text(encoding="utf-8")).body
            if isinstance(node, ast.FunctionDef) and node.name in ("run_at_window_pos", "run_in_window")
        ]
        state = {"foreground": 99, "mouse": (1500, 800)}
        gui, user32 = Mock(), Mock()
        gui.GetForegroundWindow.side_effect = lambda: state["foreground"]
        gui.SetForegroundWindow.side_effect = lambda hwnd: state.update(foreground=hwnd)
        gui.IsWindow.return_value = True
        gui.ClientToScreen.side_effect = lambda hwnd, point: (point[0] + 50, point[1] + 80)

        def cursor(pointer):
            pointer._obj.x, pointer._obj.y = state["mouse"]

        user32.GetCursorPos.side_effect = cursor
        user32.SetCursorPos.side_effect = lambda x, y: state.update(mouse=(x, y))
        bridge = {
            "ctypes": ctypes,
            "user32": user32,
            "win32gui": gui,
            "time": Mock(),
            "active_and_send_mouse_delta": lambda hwnd, **kw: state.update(foreground=hwnd) or True,
        }
        exec(compile(ast.Module(body=methods, type_ignores=[]), str(mouse_source), "exec"), bridge)
        return bridge, state

    def test_game_is_foreground_and_physical_cursor_is_in_list_during_scroll(self):
        bridge, state = self.bridge()
        observed = []

        def scroll():
            observed.append(state.copy())

        bridge["run_in_window"](77, bridge["run_at_window_pos"], 77, scroll, 307, 960)
        self.assertEqual([{"foreground": 77, "mouse": (357, 1040)}], observed)
        self.assertEqual({"foreground": 99, "mouse": (1500, 800)}, state)

    def test_scroll_exception_restores_physical_cursor_and_previous_window(self):
        bridge, state = self.bridge()

        def scroll():
            raise RuntimeError("wheel failed")

        with self.assertRaisesRegex(RuntimeError, "wheel failed"):
            bridge["run_in_window"](77, bridge["run_at_window_pos"], 77, scroll, 307, 960)
        self.assertEqual({"foreground": 99, "mouse": (1500, 800)}, state)


if __name__ == "__main__":
    unittest.main()
