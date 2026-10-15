import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ok.device.interaction_methods.genshin import GenshinInteraction

try:
    from src.patches.input_safety_patch import install_input_safety_patch
except ModuleNotFoundError:
    pass
else:
    install_input_safety_patch()


class InteractionSafetyTest(unittest.TestCase):
    def make_interaction(self):
        obj = SimpleNamespace(
            hwnd_window=SimpleNamespace(is_foreground=lambda: False),
            post_interaction=Mock(),
            activate=Mock(),
            deactivate=Mock(),
            block_input=Mock(),
            unblock_input=Mock(),
            user32=Mock(),
            get_key_by_str=Mock(return_value=18),
        )
        return obj

    def test_background_key_up_posts_release_before_deactivation(self):
        obj = self.make_interaction()
        GenshinInteraction.send_key_up(obj, "alt")
        obj.post_interaction.send_key_up.assert_called_once_with("alt")

    def test_background_scroll_never_uses_global_wheel(self):
        obj = self.make_interaction()
        obj.operate = Mock(side_effect=AssertionError("global wheel path"))
        GenshinInteraction.scroll(obj, 100, 200, -3)
        obj.post_interaction.scroll.assert_called_once_with(100, 200, -3)

    def test_click_holds_button_before_releasing(self):
        from ok.device.interaction_methods import genshin

        obj = self.make_interaction()
        obj.make_mouse_position = Mock(return_value=123)
        events = []
        obj.post = lambda message, *args: events.append(message)
        with patch.object(genshin.time, "sleep", side_effect=lambda seconds: events.append(("hold", seconds))):
            GenshinInteraction.do_click(obj, 100, 200, down_time=0.04)
        self.assertEqual([genshin.win32con.WM_LBUTTONDOWN, ("hold", 0.04), genshin.win32con.WM_LBUTTONUP, ("hold", 0.04)], events)

    def test_interrupted_click_releases_button(self):
        from ok.device.interaction_methods import genshin

        obj = self.make_interaction()
        obj.make_mouse_position = Mock(return_value=123)
        obj.post = Mock()
        with (
            patch.object(genshin.time, "sleep", side_effect=RuntimeError("interrupted")),
            self.assertRaisesRegex(RuntimeError, "interrupted"),
        ):
            GenshinInteraction.do_click(obj, 100, 200, down_time=0.04)
        self.assertEqual(genshin.win32con.WM_LBUTTONUP, obj.post.call_args.args[0])

    def test_interrupted_key_hold_still_releases_key(self):
        from ok.device.interaction_methods import genshin

        obj = self.make_interaction()
        obj.post = Mock()
        with (
            patch.object(genshin.time, "sleep", side_effect=RuntimeError("interrupted")),
            self.assertRaisesRegex(RuntimeError, "interrupted"),
        ):
            GenshinInteraction.do_send_key(obj, "alt", down_time=0.5)
        self.assertEqual(genshin.win32con.WM_KEYUP, obj.post.call_args.args[0])

    def test_click_callback_error_propagates_without_locking_input(self):
        from ok.device.interaction_methods import genshin

        obj = self.make_interaction()
        with (
            patch.object(genshin.win32api, "GetCursorPos", return_value=(30, 40)),
            patch.object(genshin.win32api, "SetCursorPos"),
            self.assertRaisesRegex(RuntimeError, "failed"),
        ):
            GenshinInteraction.operate(obj, Mock(side_effect=RuntimeError("failed")), block=True)
        obj.block_input.assert_not_called()
        obj.deactivate.assert_called_once()

    def test_cleanup_failure_never_hides_operation_error(self):
        from ok.device.interaction_methods import genshin

        obj = self.make_interaction()
        obj.deactivate.side_effect = OSError("closed window")
        with (
            patch.object(genshin.win32api, "GetCursorPos", return_value=(30, 40)),
            patch.object(genshin.win32api, "SetCursorPos") as cursor,
            self.assertRaisesRegex(RuntimeError, "failed"),
        ):
            GenshinInteraction.operate(obj, Mock(side_effect=RuntimeError("failed")), block=True)
        cursor.assert_called_once_with((30, 40))
