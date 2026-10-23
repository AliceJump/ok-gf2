"""
Interception 会话鼠标（实录 2026-10-20）：PostMessage 过不了第 9 章支援单位引导，改用会话鼠标驱动产生真实点击。
这里不碰驱动：设备逻辑用假通道检查报文，GfInteraction 的分派逻辑从源码抠出来跑在假基类上。
"""

import ast
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.core.input_env import (  # noqa: E402
    ENV_AUTO,
    ENV_CONSOLE,
    ENV_RDP,
    KEY_CONSOLE_DEVICE,
    KEY_ENVIRONMENT,
    KEY_RDP_DEVICE,
    KEY_SESSION_MOUSE,
    KIND_CONSOLE,
    KIND_RDP,
    choose_input,
    input_key,
    pinned_device,
)
from src.core.session_mouse import (  # noqa: E402
    BTN_LEFT,
    BTN_RIGHT,
    SessionMouseDevice,
    SessionMouseError,
    absolute_point,
    button_edges,
    is_candidate,
    select_session_device,
)


class PureFunctionTest(unittest.TestCase):
    def test_button_edges(self):
        self.assertEqual(button_edges(0, BTN_LEFT), 1)
        self.assertEqual(button_edges(BTN_LEFT, 0), 2)
        self.assertEqual(button_edges(0, BTN_RIGHT), 4)
        self.assertEqual(button_edges(BTN_RIGHT, 0), 8)
        self.assertEqual(button_edges(BTN_LEFT, BTN_LEFT), 0)
        self.assertEqual(button_edges(0, BTN_LEFT | BTN_RIGHT), 5)

    def test_absolute_point_maps_desktop_to_16bit(self):
        self.assertEqual(absolute_point(0, 0, (0, 0, 2560, 1440)), (0, 0))
        self.assertEqual(absolute_point(1280, 720, (0, 0, 2560, 1440)), (32768, 32768))
        self.assertEqual(
            absolute_point(2559, 1439, (0, 0, 2560, 1440)), (round(2559 * 65535 / 2560), round(1439 * 65535 / 1440))
        )

    def test_absolute_point_rejects_outside_desktop(self):
        for x, y in ((2560, 0), (-1, 0), (0, 1440)):
            with self.assertRaises(SessionMouseError):
                absolute_point(x, y, (0, 0, 2560, 1440))
        with self.assertRaises(SessionMouseError):
            absolute_point(0, 0, (0, 0, 0, 0))

    def test_select_session_device_needs_exactly_one_match(self):
        self.assertEqual(select_session_device({15}, {12: 1, 15: 2}), 15)
        with self.assertRaises(SessionMouseError):
            select_session_device(set(), {12: 1})
        with self.assertRaises(SessionMouseError):
            select_session_device({12, 15}, {12: 1, 15: 2})
        with self.assertRaises(SessionMouseError):
            select_session_device({3}, {12: 1})  # 标记来自不是候选的设备

    def test_console_takes_lowest_of_received_physical_mice(self):
        """本机桌面的真实鼠标都进控制台（实测：11 无线鼠标接收器、12 键盘上的鼠标集合），收到几台都行。"""
        self.assertEqual(select_session_device({12, 11}, {11: 1, 12: 2}, KIND_CONSOLE), 11)
        with self.assertRaises(SessionMouseError):
            select_session_device(set(), {11: 1}, KIND_CONSOLE)

    def test_candidates_by_environment(self):
        self.assertTrue(is_candidate("TS_INPT\\TS_MOU", KIND_RDP))
        self.assertFalse(is_candidate("HID\\VID_046D&PID_C54D&REV_1402&MI_00", KIND_RDP))
        self.assertTrue(is_candidate("HID\\VID_046D&PID_C54D&REV_1402&MI_00", KIND_CONSOLE))
        self.assertFalse(is_candidate("TS_INPT\\TS_MOU", KIND_CONSOLE))  # 本机桌面绝不碰 RDP 鼠标
        self.assertFalse(is_candidate("", KIND_CONSOLE))


class ChooseInputTest(unittest.TestCase):
    def test_auto_uses_rdp_mouse_only_in_rdp(self):
        self.assertEqual(choose_input({}, KIND_RDP)[:2], (KIND_RDP, None))
        kind, _, reason = choose_input({}, KIND_CONSOLE)
        self.assertIsNone(kind)  # 自动识别到本机桌面不接管人的鼠标
        self.assertIn("本机桌面", reason)

    def test_explicit_environment_must_match_actual(self):
        self.assertEqual(choose_input({KEY_ENVIRONMENT: ENV_CONSOLE}, KIND_CONSOLE)[:2], (KIND_CONSOLE, None))
        self.assertEqual(choose_input({KEY_ENVIRONMENT: ENV_RDP}, KIND_RDP)[:2], (KIND_RDP, None))
        kind, _, reason = choose_input({KEY_ENVIRONMENT: ENV_RDP}, KIND_CONSOLE)
        self.assertIsNone(kind)
        self.assertIn("实际跑在「本机桌面」", reason)
        self.assertIsNone(choose_input({KEY_ENVIRONMENT: ENV_CONSOLE}, KIND_RDP)[0])

    def test_device_setting_per_environment(self):
        settings = {KEY_ENVIRONMENT: ENV_AUTO, KEY_RDP_DEVICE: "13", KEY_CONSOLE_DEVICE: "11"}
        self.assertEqual(choose_input(settings, KIND_RDP)[:2], (KIND_RDP, 13))
        settings[KEY_ENVIRONMENT] = ENV_CONSOLE
        self.assertEqual(choose_input(settings, KIND_CONSOLE)[:2], (KIND_CONSOLE, 11))

    def test_switch_off_or_unknown_session_uses_post_message(self):
        self.assertIsNone(choose_input({KEY_SESSION_MOUSE: False}, KIND_RDP)[0])
        self.assertIsNone(choose_input({}, None)[0])
        self.assertIsNone(choose_input({KEY_ENVIRONMENT: "别的"}, KIND_RDP)[0])

    def test_pinned_device_and_key(self):
        self.assertEqual(pinned_device("15"), 15)
        for value in ("自动", "", None, "3", "abc"):
            self.assertIsNone(pinned_device(value))
        self.assertEqual(input_key({}), input_key({KEY_ENVIRONMENT: ENV_AUTO}))
        self.assertNotEqual(input_key({}), input_key({KEY_ENVIRONMENT: ENV_CONSOLE}))


class FakeChannel:
    index = 15

    def __init__(self):
        self.packets = []
        self.closed = False

    def write(self, packet):
        self.packets.append(packet)

    def close(self):
        self.closed = True


def make_device(session=3, cursor=None, kind=KIND_RDP):
    state = {"session": session, "cursor": cursor or (0, 0), "kind": kind}
    dev = SessionMouseDevice(
        kind=kind,
        identity_fn=lambda: (state["kind"], state["session"]),
        bounds_fn=lambda: (0, 0, 2560, 1440),
        cursor_fn=lambda: state["cursor"],
    )
    dev.channel = FakeChannel()
    dev.session_id = session
    return dev, state


class SessionMouseDeviceTest(unittest.TestCase):
    def test_click_is_move_press_release_with_absolute_coords(self):
        dev, state = make_device()
        state["cursor"] = (1275, 784)
        self.assertTrue(dev.click(1275, 784))
        packets = dev.channel.packets
        self.assertEqual(len(packets), 3)
        self.assertEqual([p.buttons for p in packets], [0, 1, 2])  # 无变化 / 左键按下 / 左键抬起
        self.assertTrue(all(p.flags == 3 for p in packets))
        self.assertEqual((packets[0].x, packets[0].y), (round(1275 * 65535 / 2560), round(784 * 65535 / 1440)))
        self.assertEqual(dev.buttons, 0)
        self.assertEqual(dev.position, (1275, 784))

    def test_right_click_uses_right_button_edges(self):
        dev, state = make_device(cursor=(10, 10))
        self.assertTrue(dev.click(10, 10, buttons=BTN_RIGHT))
        self.assertEqual([p.buttons for p in dev.channel.packets], [0, 4, 8])

    def test_outside_desktop_writes_nothing(self):
        dev, _ = make_device()
        self.assertFalse(dev.click(3000, 10))
        self.assertEqual(dev.channel.packets, [])

    def test_session_change_refuses_to_write(self):
        dev, state = make_device()
        state["session"] = 4
        self.assertFalse(dev.move(10, 10))
        self.assertEqual(dev.channel.packets, [])

    def test_environment_change_refuses_to_write(self):
        dev, state = make_device(kind=KIND_CONSOLE, session=1)
        self.assertTrue(dev.move(10, 10, settle=0))
        state["kind"] = KIND_RDP  # 同一会话号被当成远程桌面连进来，也不再用控制台的真实鼠标
        self.assertFalse(dev.move(20, 20))
        self.assertEqual(len(dev.channel.packets), 1)

    def test_open_refuses_wrong_environment(self):
        dev = SessionMouseDevice(kind=KIND_CONSOLE, identity_fn=lambda: (KIND_RDP, 3))
        if sys.platform == "win32":
            self.assertFalse(dev.open())
        self.assertFalse(dev.bound)

    def test_move_waits_for_cursor_but_does_not_fail_on_mismatch(self):
        dev, state = make_device(cursor=(0, 0))
        self.assertTrue(dev.move(100, 100, settle=0.02))
        self.assertEqual(len(dev.channel.packets), 1)

    def test_wheel_sends_one_report_per_notch(self):
        dev, state = make_device(cursor=(50, 50))
        self.assertTrue(dev.wheel(50, 50, -3))
        wheel_packets = [p for p in dev.channel.packets if p.buttons & 0x400]
        self.assertEqual(len(wheel_packets), 3)
        self.assertTrue(all(p.wheel == (-120) & 0xFFFF for p in wheel_packets))

    def test_close_releases_held_button(self):
        dev, state = make_device(cursor=(5, 5))
        dev.move(5, 5)
        dev.press()
        dev.close()
        self.assertEqual(dev.channel, None)
        self.assertEqual(dev.buttons, 0)


# ---- GfInteraction 分派：从源码抠出类，基类和设备都换成假的 ----
source = ROOT / "src/core/gf_interaction.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GfInteraction")


class FakeGenshin:
    def __init__(self, capture, hwnd_window):
        self.capture = capture
        self.hwnd_window = hwnd_window
        self.calls = []

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.02, move=True, key="left"):
        self.calls.append(("post_click", x, y, key))

    def move(self, x, y, down_btn=0):
        self.calls.append(("post_move", x, y))

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        self.calls.append(("post_down", x, y))

    def mouse_up(self, x=-1, y=-1, key="left"):
        self.calls.append(("post_up", x, y))

    def swipe(self, *a, **k):
        self.calls.append(("post_swipe",) + a)

    def scroll(self, x, y, amount):
        self.calls.append(("post_scroll", x, y, amount))

    def on_destroy(self):
        self.calls.append(("destroy",))

    def deactivate(self):
        self.calls.append(("deactivate",))


class FakeDevice:
    opens = True
    created = []

    def __init__(self, kind=None, device=None):
        self.kind, self.device = kind, device
        FakeDevice.created.append(self)
        self.calls = []
        self.device_path = "fake"
        self.click_ok = True

    def open(self):
        return self.opens

    def click(self, x, y, buttons=1, down_time=0.02):
        self.calls.append(("click", x, y, buttons))
        return self.click_ok

    def move(self, x, y, settle=0.1):
        self.calls.append(("move", x, y))
        return True

    def press(self, buttons=1):
        self.calls.append(("press", buttons))
        return True

    def release(self):
        self.calls.append(("release",))
        return True

    def wheel(self, x, y, n):
        self.calls.append(("wheel", x, y, n))
        return True

    def close(self):
        self.calls.append(("close",))


ns = {
    "GenshinInteraction": FakeGenshin,
    "SessionMouseDevice": FakeDevice,
    "BTN_LEFT": 1,
    "BUTTON_OF_KEY": {"left": 1, "right": 2, "middle": 4},
    "INPUT_OPTION_NAME": "输入",
    "choose_input": choose_input,
    "input_key": input_key,
    "current_kind": lambda: STATE["kind"],
    "input_settings": lambda: dict(STATE["settings"]),
    "logger": Mock(),
    "time": __import__("time"),
}
STATE = {"kind": KIND_RDP, "settings": {}}
exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), "exec"), ns)
GfInteraction = ns["GfInteraction"]


def make_interaction(bound=True, foreground=True, origin=(0, 0), kind=KIND_RDP, settings=None):
    FakeDevice.opens = bound
    FakeDevice.created = []
    STATE["kind"], STATE["settings"] = kind, settings or {}
    capture = SimpleNamespace(get_abs_cords=lambda x, y: (origin[0] + x, origin[1] + y))
    window = Mock()
    window.is_foreground.return_value = foreground
    window.bring_to_front.return_value = True
    it = GfInteraction(capture, window)
    it.post_interaction = Mock()
    return it


class GfInteractionTest(unittest.TestCase):
    def test_click_goes_through_session_mouse_with_screen_coords(self):
        it = make_interaction(origin=(100, 50))
        it.click(1275, 784)
        self.assertEqual(it.session_mouse.calls, [("click", 1375, 834, 1)])
        self.assertEqual(it.calls, [])
        it.hwnd_window.bring_to_front.assert_not_called()

    def test_game_is_brought_to_front_before_real_click(self):
        it = make_interaction(foreground=False)
        it.click(10, 20)
        it.hwnd_window.bring_to_front.assert_called_once()
        self.assertEqual(it.session_mouse.calls, [("click", 10, 20, 1)])

    def test_unbound_device_falls_back_to_post_message(self):
        it = make_interaction(bound=False)
        self.assertFalse(it.session_mouse_ok)
        it.click(10, 20)
        it.scroll(1, 2, -1)
        self.assertEqual(it.calls, [("post_click", 10, 20, "left"), ("post_scroll", 1, 2, -1)])
        self.assertEqual(it.session_mouse.calls, [])

    def test_failed_real_click_retries_with_post_message(self):
        it = make_interaction()
        it.session_mouse.click_ok = False
        it.click(10, 20)
        self.assertEqual(it.calls, [("post_click", 10, 20, "left")])

    def test_disabled_in_global_config_uses_post_message(self):
        it = make_interaction()
        STATE["settings"] = {KEY_SESSION_MOUSE: False}
        it.click(10, 20)
        self.assertEqual(it.calls, [("post_click", 10, 20, "left")])
        self.assertEqual(FakeDevice.created[0].calls, [("close",)])

    def test_console_auto_stays_on_post_message(self):
        it = make_interaction(kind=KIND_CONSOLE)
        self.assertIsNone(it.session_mouse)
        it.click(10, 20)
        self.assertEqual(it.calls, [("post_click", 10, 20, "left")])

    def test_console_environment_binds_real_mouse(self):
        it = make_interaction(kind=KIND_CONSOLE, settings={KEY_ENVIRONMENT: ENV_CONSOLE, KEY_CONSOLE_DEVICE: "11"})
        self.assertEqual((it.session_mouse.kind, it.session_mouse.device), (KIND_CONSOLE, 11))
        it.click(10, 20)
        self.assertEqual(it.session_mouse.calls, [("click", 10, 20, 1)])

    def test_changing_environment_rebinds_before_next_click(self):
        it = make_interaction(kind=KIND_CONSOLE)
        it.click(1, 1)
        STATE["settings"] = {KEY_ENVIRONMENT: ENV_CONSOLE}
        it.click(2, 2)
        self.assertEqual(it.calls, [("post_click", 1, 1, "left")])
        self.assertEqual(it.session_mouse.kind, KIND_CONSOLE)
        self.assertEqual(it.session_mouse.calls, [("click", 2, 2, 1)])

    def test_mismatched_environment_never_binds(self):
        it = make_interaction(kind=KIND_RDP, settings={KEY_ENVIRONMENT: ENV_CONSOLE})
        self.assertEqual(FakeDevice.created, [])
        it.click(10, 20)
        self.assertEqual(it.calls, [("post_click", 10, 20, "left")])

    def test_negative_coords_mean_current_position_and_stay_on_post_message(self):
        it = make_interaction()
        it.click(-1, -1)
        self.assertEqual(it.calls, [("post_click", -1, -1, "left")])

    def test_right_click_maps_to_right_button(self):
        it = make_interaction()
        it.right_click(3, 4)
        self.assertEqual(it.session_mouse.calls, [("click", 3, 4, 2)])

    def test_swipe_is_press_moves_release(self):
        it = make_interaction()
        it.swipe(0, 0, 100, 0, duration=300, settle_time=0)
        calls = it.session_mouse.calls
        self.assertEqual(calls[0], ("move", 0, 0))
        self.assertEqual(calls[1], ("press", 1))
        self.assertEqual(calls[-1], ("release",))
        self.assertEqual([c for c in calls if c[0] == "move"][-1], ("move", 100, 0))

    def test_key_up_really_releases_and_keeps_foreground_game_active(self):
        """alt+点击之后不能伪造失活，否则活动层饮品页的「制作」和 ESC 都不认（实录 2026-10-21）。"""
        it = make_interaction(foreground=True)
        it.send_key_up("alt")
        it.post_interaction.send_key_up.assert_called_once_with("alt")
        self.assertEqual(it.calls, [])

    def test_key_up_in_background_still_deactivates(self):
        it = make_interaction(foreground=False)
        it.send_key_up("alt")
        it.post_interaction.send_key_up.assert_called_once_with("alt")
        self.assertEqual(it.calls, [("deactivate",)])

    def test_destroy_closes_device(self):
        it = make_interaction()
        it.on_destroy()
        self.assertEqual(it.session_mouse.calls, [("close",)])
        self.assertEqual(it.calls, [("destroy",)])


class InteractionConfigTest(unittest.TestCase):
    def test_interaction_is_a_list_with_postmessage_fallback(self):
        """Qt「捕获」页的输入方式列表只接受字符串或列表；写成单个类会报 len(type)（实录 2026-10-21）。"""
        import ast
        from pathlib import Path as _Path

        tree = ast.parse((_Path(__file__).resolve().parents[1] / "src/config.py").read_text(encoding="utf-8"))
        windows = next(
            v
            for node in ast.walk(tree)
            if isinstance(node, ast.Dict)
            for k, v in zip(node.keys, node.values, strict=True)
            if isinstance(k, ast.Constant) and k.value == "interaction"
        )
        self.assertIsInstance(windows, ast.List)
        names = [e.id if isinstance(e, ast.Name) else e.value for e in windows.elts]
        self.assertEqual(names, ["GfInteraction", "Genshin"])


if __name__ == "__main__":
    unittest.main()
