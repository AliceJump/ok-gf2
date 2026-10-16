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
        "_ensure_supply_menu",
        "_open_supply_activity",
        "_scroll_supply_menu",
        "_claim_supply_activity",
    )
]
namespace = {"re": re, "pop_ups": ["点击空白处关闭"]}
exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), namespace)


screens = {}


def run_in_window(hwnd, func, *args, **kwargs):
    """模拟后台滚动前后的窗口状态恢复。"""
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
    """记录模拟窗口激活，不发送系统输入。"""
    screen = screens[hwnd]
    if not screen.foreground:
        screen.activations += 1
        screen.foreground = True


def run_at_window_pos(hwnd, func, x, y, sleep_time=0.5):
    """临时移动模拟鼠标并保证恢复原位置。"""
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
    _open_supply_activity = namespace["_open_supply_activity"]
    _claim_supply_activity = namespace["_claim_supply_activity"]
    _scroll_supply_menu = namespace["_scroll_supply_menu"]

    def __init__(self, entries=None, remaining=None):
        """Model init."""
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
        self._ensure_supply_menu = Mock(return_value=True)
        self.sleep = Mock()
        self.ensure_main = Mock()
        self.executor = SimpleNamespace(
            interaction=SimpleNamespace(
                hwnd_window=SimpleNamespace(is_foreground=lambda: self.foreground),
                post_interaction=SimpleNamespace(
                    move=lambda x, y: self.move_relative(x / self.width, y / self.height),
                    scroll=lambda x, y, count: self.scroll_relative(x / self.width, y / self.height, count),
                    deactivate=Mock(),
                )
            )
        )

    def box_of_screen(self, *bounds):
        """用归一化边界标识侧栏识别区域。"""
        return bounds

    def tr(self, message):
        """保持测试状态文案不变。"""
        return message

    def move_relative(self, x, y):
        """记录虚拟悬停点以验证滚轮的目标区域。"""
        self.hover_mouse = (int(self.width * x), int(self.height * y))

    def scroll_relative(self, x, y, count):
        """Model scroll relative."""
        self.scrolls.append((x, y, count))
        target = (int(self.width * x), int(self.height * y))
        if self.hover_mouse != target:
            self.ineffective_scrolls.append(count)
            return
        self.menu_page = 0 if count > 0 else self.menu_page + 1

    def wait_click_ocr(self, *, match, box, **kwargs):
        """仅在当前页面匹配入口或领取按钮时推进状态。"""
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
        """按当前补给页面、弹窗和领取状态提供证据。"""
        if isinstance(match, list):
            return self.popup
        if self.page_ok and match.search(self.selected or ""):
            return True
        return self.known_empty and not self.remaining.get(self.selected, 0) and bool(match.search("已领取"))

    def wait_pop_up(self, **kwargs):
        """关闭奖励弹窗并模拟返回补给页。"""
        self.popup = False
        self.page_ok = self.restore_page


class ActivitySupplyTest(unittest.TestCase):
    def test_finds_hidden_entries_and_claims_both_time_slots(self):
        """Verify finds hidden entries and claims both time slots."""
        task = SupplyScreen()
        self.assertIs(True, task.activities())
        self.assertEqual(["情报补给", "情报补给", "战前补给"], task.claims)
        self.assertEqual("已确认领取 2 次", task.status["情报补给"])
        self.assertEqual(2, sum(count > 0 for _, _, count in task.scrolls))
        self.assertGreater(task.menu_checks, 2)
        self.assertEqual([], task.ineffective_scrolls)
        self.assertFalse(task.foreground)
        self.assertEqual((1500, 800), task.physical_mouse)
        self.assertEqual(0, task.activations)
        self.assertEqual(0, task.restores)
        task.ensure_main.assert_called_once()

    def test_absent_supply_events_are_bounded_and_skipped(self):
        """Verify absent supply events are bounded and skipped."""
        task = SupplyScreen(entries={})
        self.assertIs(True, task.activities())
        self.assertEqual(16, task.menu_checks)
        self.assertEqual([], task.claims)
        self.assertIn("未找到入口", task.status["情报补给"])
        task.ensure_main.assert_called_once()

    def test_focus_interruption_does_not_reactivate_game(self):
        """Verify focus interruption does not reactivate game."""
        task = SupplyScreen()
        original = task.wait_click_ocr
        interrupted = False

        def click(**kwargs):
            """Model click."""
            nonlocal interrupted
            result = original(**kwargs)
            if isinstance(kwargs["box"], tuple) and not interrupted:
                task.foreground = False
                interrupted = True
            return result

        task.wait_click_ocr = click
        self.assertIs(True, task.activities())
        self.assertEqual(0, task.activations)
        self.assertEqual(0, task.restores)
        self.assertEqual([], task.ineffective_scrolls)

    def test_already_foreground_does_not_switch_windows(self):
        """前台游戏领取补给时不切换系统窗口。"""
        task = SupplyScreen()
        task.foreground = True
        self.assertIs(True, task.activities())
        self.assertEqual(0, task.activations)
        self.assertEqual(0, task.restores)
        self.assertTrue(task.foreground)

    def test_optional_prewar_event_can_be_absent(self):
        """战前补给缺席不影响已确认的情报补给领取。"""
        task = SupplyScreen(entries={2: "情报补给"})
        self.assertIs(True, task.activities())
        self.assertEqual(["情报补给", "情报补给"], task.claims)
        self.assertIn("未找到入口", task.status["战前补给"])

    def test_intelligence_event_can_also_be_absent(self):
        """Verify intelligence event can also be absent."""
        task = SupplyScreen(entries={4: "战前补给"})
        self.assertIs(True, task.activities())
        self.assertEqual(["战前补给"], task.claims)
        self.assertIn("跳过", task.status["情报补给"])

    def test_unopened_activity_menu_stays_uncertain_and_never_searches(self):
        """Verify unopened activity menu stays uncertain and never searches."""
        task = SupplyScreen()
        task._ensure_supply_menu.return_value = False
        self.assertEqual("待核查", task.activities())
        self.assertEqual(0, task.menu_checks)
        self.assertEqual([], task.claims)

    def test_wrong_page_never_clicks_a_claim_button(self):
        """页面无法确认时不点击疑似领取按钮。"""
        task = SupplyScreen()
        task.page_ok = False
        self.assertEqual("待核查", task.activities())
        self.assertEqual([], task.claims)

    def test_missing_popup_stops_without_repeating_uncertain_click(self):
        """领取后弹窗缺失时停止重复操作并保留待核查。"""
        task = SupplyScreen(entries={2: "情报补给"})
        task.popup_ok = False
        self.assertEqual("待核查", task.activities())
        self.assertEqual(["情报补给"], task.claims)
        self.assertIn("未确认奖励弹窗", task.status["情报补给"])

    def test_already_claimed_is_never_clicked_as_claim(self):
        """完整匹配领取按钮，排除已领取文字。"""
        task = SupplyScreen(entries={2: "情报补给"}, remaining={"情报补给": 2})
        task.button_label = "已领取"
        task.wait_ocr = lambda *, match, **kwargs: (
            not isinstance(match, list) and bool(match.search("情报补给") or match.search("已领取"))
        )
        self.assertIs(True, task.activities())
        self.assertEqual([], task.claims)

    def test_unrecognized_state_is_uncertain(self):
        """无法识别按钮或领取状态时保留待核查。"""
        task = SupplyScreen(entries={2: "情报补给"}, remaining={})
        task.known_empty = False
        self.assertEqual("待核查", task.activities())
        self.assertIn("未识别", task.status["情报补给"])

    def test_lost_page_after_popup_is_uncertain(self):
        """奖励弹窗后页面丢失时停止后续领取。"""
        task = SupplyScreen(entries={2: "情报补给"})
        task.restore_page = False
        self.assertEqual("待核查", task.activities())
        self.assertEqual(["情报补给"], task.claims)

    def test_persistent_button_does_not_loop_forever(self):
        """领取按钮不消失时限制重复次数。"""
        task = SupplyScreen(entries={2: "情报补给"})
        task.stuck_button = True
        self.assertEqual("待核查", task.activities())
        self.assertEqual(10, len(task.claims))

    def test_navigation_exception_still_restores_main(self):
        """导航异常仍返回主页并传播原异常。"""
        task = SupplyScreen()
        task.scroll_relative = Mock(side_effect=RuntimeError("menu unavailable"))
        with self.assertRaisesRegex(RuntimeError, "menu unavailable"):
            task.activities()
        task.ensure_main.assert_called_once()

    def test_daily_run_continues_when_optional_supply_events_are_absent(self):
        """Verify daily run continues when optional supply events are absent."""
        from src.tasks.DailyTaskRunner import DailyTaskRunner
        from tests.TestDailyTaskRunner import StubTask

        task = StubTask({"活动情报补给": True})
        supply = SupplyScreen(entries={})
        runner = DailyTaskRunner(task, [("活动情报补给", supply.activities)])
        runner.run()
        self.assertEqual([], runner.task_status["uncertain"])
        self.assertEqual(["活动情报补给"], runner.task_status["success"])


class SupplyMenuVerificationTest(unittest.TestCase):
    def check_menu(self, menu, home=()):
        """用实际匹配词过滤 OCR，避免桩忽略正则掩盖识别错误。"""
        task = Mock()
        task.box.right = "right"
        task.box_of_screen.side_effect = lambda *args: args
        task.wait_until.side_effect = lambda predicate, **kw: predicate()

        def ocr(*, box, match):
            """返回经过生产正则或主页匹配词筛选的识别框。"""
            texts = home if box == "right" else menu
            return [SimpleNamespace(name=text) for text in texts if (
                any(word in text for word in match) if isinstance(match, list) else match.search(text)
            )]

        task.ocr.side_effect = ocr
        return namespace["_ensure_supply_menu"](task), task

    def test_spaced_supply_names_confirm_open_menu(self):
        """入口名称带字间空格时仍能识别已打开的列表。"""
        for name in ("情 报 补 给", "战 前 补 给"):
            with self.subTest(name=name):
                self.assertTrue(self.check_menu([name])[0])

    def test_sidebar_headers_confirm_menu_without_optional_supplies(self):
        """两个固定侧栏页签足以确认列表，不要求可选补给仍存在。"""
        self.assertTrue(self.check_menu(["新手", "活动", "琥珀月光"])[0])
        self.assertTrue(self.check_menu(["新 手", "活 动"])[0])

    def test_arbitrary_chinese_text_does_not_confirm_menu(self):
        """主页文字漏读时任意中文也不能充当列表证据。"""
        self.assertFalse(self.check_menu(["任意文字"])[0])

    def test_one_home_label_rejects_even_specific_menu_evidence(self):
        """一个主页标签仍是反证，不能把点击失败报告成活动缺席。"""
        for menu in (["任意文字"], ["情报补给"], ["新手", "活动"]):
            with self.subTest(menu=menu):
                result, task = self.check_menu(menu, ["整备室"])
                self.assertFalse(result)
                task.screenshot.assert_called_once_with("supply_menu_not_open")

    def test_empty_or_single_generic_header_remains_uncertain(self):
        """空白、单个活动按钮和多个主页标签均不能确认列表。"""
        for menu, home in (([], []), (["活动"], []), (["新手"], []), (["情报补给"], ["招募", "活动层"])):
            with self.subTest(menu=menu, home=home):
                self.assertFalse(self.check_menu(menu, home)[0])


class BackgroundSupplyScrollTest(unittest.TestCase):
    """真实窗口消息方法通过桩边界验证，不对游戏发送输入。"""

    def make_task(self):
        """保留真实 move/scroll 方法，只替换 Win32 消息发送边界。"""
        from ok.device.interaction_methods.post_message import PostMessageInteraction

        post = PostMessageInteraction.__new__(PostMessageInteraction)
        post.post = Mock()
        post.update_mouse_pos = Mock(return_value=123)
        post.try_activate = Mock()
        task = SimpleNamespace(
            width=2560,
            height=1600,
            sleep=Mock(),
            executor=SimpleNamespace(interaction=SimpleNamespace(
                post_interaction=post, hwnd_window=SimpleNamespace(is_foreground=lambda: False)
            )),
            move_relative=Mock(side_effect=AssertionError("不应进入Genshin物理鼠标路径")),
            scroll_relative=Mock(side_effect=AssertionError("不应依赖全局滚轮补丁")),
        )
        return task, post

    def test_foreground_scroll_preserves_activation_for_real_next_click(self):
        """真实消息停用会使前台 Genshin 点击缺少激活，滚动必须保留激活。"""
        import win32con
        from ok.device.interaction_methods.genshin import GenshinInteraction

        task, post = self.make_task()
        state = {"active": True}

        def send(message, wparam=0, *args, **kwargs):
            """只模拟 Win32 消息接收窗口的激活状态。"""
            if message == win32con.WM_ACTIVATE:
                state["active"] = wparam == win32con.WA_ACTIVE

        post.post.side_effect = send
        post.try_activate.side_effect = post.activate
        interaction = GenshinInteraction.__new__(GenshinInteraction)
        interaction.hwnd_window = SimpleNamespace(is_foreground=lambda: True)
        interaction.post_interaction = post
        task.executor.interaction = interaction
        namespace["_scroll_supply_menu"](task, -3)
        # 依赖 operate 的真实前台分支不补发 activate；以接收窗口状态验证后续点击可用。
        self.assertTrue(interaction.operate(lambda: state["active"]))
        self.assertNotIn(
            (win32con.WM_ACTIVATE, win32con.WA_INACTIVE),
            [call.args[:2] for call in post.post.call_args_list],
        )

    def test_foreground_scroll_failure_does_not_deactivate(self):
        """前台滚动失败也不得向原本激活的窗口发送停用消息。"""
        task, post = self.make_task()
        task.executor.interaction.hwnd_window.is_foreground = lambda: True
        post.scroll = Mock(side_effect=RuntimeError("wheel failed"))
        post.deactivate = Mock()
        with self.assertRaisesRegex(RuntimeError, "wheel failed"):
            namespace["_scroll_supply_menu"](task, -3)
        post.deactivate.assert_not_called()

    def test_real_message_backend_scrolls_without_pr97_patch(self):
        """未安装 #97 时也只发送悬停和滚轮消息。"""
        import win32con

        task, post = self.make_task()
        namespace["_scroll_supply_menu"](task, -3)
        self.assertEqual(
            [win32con.WM_MOUSEMOVE, win32con.WM_MOUSEWHEEL, win32con.WM_ACTIVATE],
            [call.args[0] for call in post.post.call_args_list],
        )
        self.assertEqual((307, 960), post.update_mouse_pos.call_args.args)
        task.move_relative.assert_not_called()
        task.scroll_relative.assert_not_called()

    def test_scroll_failure_still_deactivates_message_target(self):
        """滚动异常时清理消息激活状态，并保留原异常。"""
        task, post = self.make_task()
        post.scroll = Mock(side_effect=RuntimeError("wheel failed"))
        post.deactivate = Mock()
        with self.assertRaisesRegex(RuntimeError, "wheel failed"):
            namespace["_scroll_supply_menu"](task, -3)
        post.deactivate.assert_called_once()

    def test_missing_message_backend_is_explicit_failure(self):
        """缺少后台消息接口时明确失败，不能回落到物理滚轮。"""
        task, _ = self.make_task()
        task.executor.interaction = SimpleNamespace()
        with self.assertRaisesRegex(RuntimeError, "窗口消息"):
            namespace["_scroll_supply_menu"](task, -3)


class NativeHoverTest(unittest.TestCase):
    def bridge(self):
        """Model bridge."""
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
            """读取模拟鼠标位置到 Win32 指针边界。"""
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
        """验证旧窗口桥接在作用域内移动并恢复鼠标。"""
        bridge, state = self.bridge()
        observed = []

        def scroll():
            """模拟滚动回调或滚动异常。"""
            observed.append(state.copy())

        bridge["run_in_window"](77, bridge["run_at_window_pos"], 77, scroll, 307, 960)
        self.assertEqual([{"foreground": 77, "mouse": (357, 1040)}], observed)
        self.assertEqual({"foreground": 99, "mouse": (1500, 800)}, state)

    def test_scroll_exception_restores_physical_cursor_and_previous_window(self):
        """验证旧窗口桥接遇到滚轮异常仍恢复状态。"""
        bridge, state = self.bridge()

        def scroll():
            """模拟滚动回调或滚动异常。"""
            raise RuntimeError("wheel failed")

        with self.assertRaisesRegex(RuntimeError, "wheel failed"):
            bridge["run_in_window"](77, bridge["run_at_window_pos"], 77, scroll, 307, 960)
        self.assertEqual({"foreground": 99, "mouse": (1500, 800)}, state)


if __name__ == "__main__":
    unittest.main()
