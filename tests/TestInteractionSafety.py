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
        """Create isolated interaction state without sending desktop input."""
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
        """Release the modifier through the background interaction."""
        obj = self.make_interaction()
        GenshinInteraction.send_key_up(obj, "alt")
        obj.post_interaction.send_key_up.assert_called_once_with("alt")

    def test_background_scroll_never_uses_global_wheel(self):
        """Keep wheel input on the window message path."""
        obj = self.make_interaction()
        obj.operate = Mock(side_effect=AssertionError("global wheel path"))
        GenshinInteraction.scroll(obj, 100, 200, -3)
        obj.post_interaction.scroll.assert_called_once_with(100, 200, -3)

    def test_background_scroll_cleans_up_real_post_message_activation(self):
        """The real post backend activates base and child windows while scrolling."""
        import win32con
        from ok.device.interaction_methods.post_message import PostMessageInteraction

        post = PostMessageInteraction.__new__(PostMessageInteraction)
        post.hwnd_window = SimpleNamespace(hwnd=100, top_hwnd=200)
        post._dynamic_target_hwnd = 0
        post.update_mouse_pos = Mock(return_value=123)
        post.post = Mock()
        obj = SimpleNamespace(
            hwnd_window=SimpleNamespace(is_foreground=lambda: False),
            post_interaction=post,
        )

        GenshinInteraction.scroll(obj, 100, 200, -3)

        activations = [
            (call.args[1], call.kwargs.get("hwnd"))
            for call in post.post.call_args_list
            if call.args[0] == win32con.WM_ACTIVATE
        ]
        self.assertEqual(
            [(win32con.WA_ACTIVE, 100), (win32con.WA_ACTIVE, 200),
             (win32con.WA_INACTIVE, 200), (win32con.WA_INACTIVE, 100)],
            activations,
        )

    def test_foreground_scroll_preserves_activation(self):
        """Do not deactivate a game window that was already foreground."""
        import win32con
        from ok.device.interaction_methods.post_message import PostMessageInteraction

        post = PostMessageInteraction.__new__(PostMessageInteraction)
        post.hwnd_window = SimpleNamespace(hwnd=100, top_hwnd=0)
        post._dynamic_target_hwnd = 0
        post.update_mouse_pos = Mock(return_value=123)
        post.post = Mock()
        obj = SimpleNamespace(
            hwnd_window=SimpleNamespace(is_foreground=lambda: True),
            post_interaction=post,
        )

        GenshinInteraction.scroll(obj, 100, 200, -3)

        self.assertFalse(any(
            call.args[:2] == (win32con.WM_ACTIVATE, win32con.WA_INACTIVE)
            for call in post.post.call_args_list
        ))

    def test_background_scroll_failure_still_cleans_up_activation(self):
        """A failed wheel send must release both activated window handles."""
        import win32con
        from ok.device.interaction_methods.post_message import PostMessageInteraction

        post = PostMessageInteraction.__new__(PostMessageInteraction)
        post.hwnd_window = SimpleNamespace(hwnd=100, top_hwnd=200)
        post._dynamic_target_hwnd = 0
        post.update_mouse_pos = Mock(return_value=123)
        post.post = Mock(side_effect=lambda message, *args, **kwargs: (
            (_ for _ in ()).throw(RuntimeError("wheel failed"))
            if message == win32con.WM_MOUSEWHEEL else None
        ))
        obj = SimpleNamespace(
            hwnd_window=SimpleNamespace(is_foreground=lambda: False),
            post_interaction=post,
        )

        with self.assertRaisesRegex(RuntimeError, "wheel failed"):
            GenshinInteraction.scroll(obj, 100, 200, -3)
        deactivations = [
            call.kwargs["hwnd"] for call in post.post.call_args_list
            if call.args[:2] == (win32con.WM_ACTIVATE, win32con.WA_INACTIVE)
        ]
        self.assertEqual([200, 100], deactivations)

    def test_key_release_error_survives_cleanup_failure(self):
        """Keep the original release error when window cleanup also fails."""
        obj = self.make_interaction()
        original_error = RuntimeError("release failed")
        obj.post_interaction.send_key_up.side_effect = original_error
        obj.deactivate.side_effect = OSError("closed window")
        with (
            self.assertLogs("src.patches.input_safety_patch", level="WARNING"),
            self.assertRaises(RuntimeError) as raised,
        ):
            GenshinInteraction.send_key_up(obj, "alt")
        self.assertIs(original_error, raised.exception)
        obj.deactivate.assert_called_once()

    def test_successful_key_release_tolerates_cleanup_failure(self):
        """Log a cleanup error without failing a completed key release."""
        obj = self.make_interaction()
        obj.deactivate.side_effect = OSError("closed window")
        with self.assertLogs("src.patches.input_safety_patch", level="WARNING"):
            GenshinInteraction.send_key_up(obj, "alt")
        obj.post_interaction.send_key_up.assert_called_once_with("alt")
        obj.deactivate.assert_called_once()

    def test_click_holds_button_before_releasing(self):
        """Preserve the requested button hold and post-click delay."""
        from ok.device.interaction_methods import genshin

        obj = self.make_interaction()
        obj.make_mouse_position = Mock(return_value=123)
        events = []
        obj.post = lambda message, *args: events.append(message)
        with patch.object(genshin.time, "sleep", side_effect=lambda seconds: events.append(("hold", seconds))):
            GenshinInteraction.do_click(obj, 100, 200, down_time=0.04)
        self.assertEqual([genshin.win32con.WM_LBUTTONDOWN, ("hold", 0.04), genshin.win32con.WM_LBUTTONUP, ("hold", 0.04)], events)

    def test_interrupted_click_releases_button(self):
        """Post mouse release when the hold is interrupted."""
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
        """Post key release when a long hold is interrupted."""
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
        """Preserve callback errors while cleaning up without global input locks."""
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
        """Preserve the operation error and restore the cursor if deactivation fails."""
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

    def test_require_foreground_skips_callback_when_activation_is_not_confirmed(self):
        """Do not run global input when activation did not reach the foreground."""
        from ok.device.interaction_methods import genshin

        obj = self.make_interaction()
        callback = Mock()
        with patch.object(genshin.win32api, "GetCursorPos", return_value=(30, 40)), patch.object(
            genshin.win32api, "SetCursorPos"
        ):
            result = GenshinInteraction.operate(obj, callback, require_foreground=True)
        self.assertFalse(result)
        callback.assert_not_called()
        obj.activate.assert_called_once()

    def test_move_mouse_relative_requires_foreground(self):
        """Guard global mouse movement with a foreground check."""
        from ok.device.interaction_methods import genshin

        obj = self.make_interaction()
        obj.do_move_mouse_relative = Mock()
        with patch.object(genshin.win32api, "GetCursorPos", return_value=(30, 40)), patch.object(
            genshin.win32api, "SetCursorPos"
        ):
            result = GenshinInteraction.move_mouse_relative(obj, 3, -2)
        self.assertFalse(result)
        obj.do_move_mouse_relative.assert_not_called()
