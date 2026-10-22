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

from src.core.session_mouse import (  # noqa: E402
    BTN_LEFT,
    BTN_RIGHT,
    SessionMouseDevice,
    SessionMouseError,
    absolute_point,
    button_edges,
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


class FakeChannel:
    index = 15

    def __init__(self):
        self.packets = []
        self.closed = False

    def write(self, packet):
        self.packets.append(packet)

    def close(self):
        self.closed = True


def make_device(session=3, cursor=None):
    state = {"session": session, "cursor": cursor or (0, 0)}
    dev = SessionMouseDevice(
        session_id_fn=lambda: state["session"],
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

    def __init__(self):
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
    "KEY_SESSION_MOUSE": "会话鼠标驱动",
    "logger": Mock(),
    "time": __import__("time"),
}
exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), "exec"), ns)
GfInteraction = ns["GfInteraction"]


def make_interaction(bound=True, foreground=True, origin=(0, 0)):
    FakeDevice.opens = bound
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
        it.session_mouse_enabled = lambda: False
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
