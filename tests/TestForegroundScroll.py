"""Foreground wheel delivery and restoration; no real desktop input in unit tests."""

import importlib
import unittest
from unittest.mock import Mock, patch


class ForegroundScrollTest(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("src.interaction.foreground_scroll")
        self.gui = Mock()
        self.api = Mock()
        self.process = Mock()
        self.focus = 20
        self.cursor = (900, 700)
        self.original_clip = (0, 0, 1920, 1080)
        self.clip = self.original_clip
        self.events = []
        self.gui.IsWindow.return_value = True
        self.gui.IsIconic.return_value = False
        self.gui.GetClientRect.return_value = (0, 0, 1920, 1080)
        self.gui.ClientToScreen.return_value = (230, 650)
        self.gui.GetForegroundWindow.side_effect = lambda: self.focus
        self.api.GetCursorPos.side_effect = lambda: self.cursor
        self.api.GetCurrentThreadId.return_value = 1
        self.process.GetWindowThreadProcessId.side_effect = lambda hwnd: (hwnd, 100)

        def focus(hwnd):
            self.focus = hwnd
            self.events.append(("focus", hwnd))

        def cursor(position):
            self.cursor = position
            self.events.append(("cursor", position))

        def wheel(*args):
            self.events.append(("wheel", self.focus, self.cursor, args[3]))

        def clip(rect):
            self.clip = rect
            self.events.append(("clip", rect))

        self.gui.SetForegroundWindow.side_effect = focus
        self.api.SetCursorPos.side_effect = cursor
        self.api.mouse_event.side_effect = wheel
        self.api.ClipCursor.side_effect = clip
        for name, value in [
            ("win32gui", self.gui),
            ("win32api", self.api),
            ("win32process", self.process),
            ("time", Mock()),
        ]:
            patcher = patch.object(self.module, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(self.module, "_get_cursor_clip", return_value=self.original_clip, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def scroll(self, count=-3):
        return self.module.scroll_in_foreground(10, 230, 650, count)

    def test_moves_cursor_and_uses_real_wheel_then_restores(self):
        self.scroll()
        self.assertEqual([e for e in self.events if e[0] == "wheel"], [("wheel", 10, (230, 650), -120)] * 3)
        self.assertEqual(self.focus, 20)
        self.assertEqual(self.cursor, (900, 700))

    def test_positive_direction(self):
        self.scroll(2)
        self.assertEqual([e[-1] for e in self.events if e[0] == "wheel"], [120, 120])

    def test_input_error_restores_both_and_propagates(self):
        self.api.mouse_event.side_effect = RuntimeError("wheel failed")
        with self.assertRaisesRegex(RuntimeError, "wheel failed"):
            self.scroll()
        self.assertEqual((self.focus, self.cursor), (20, (900, 700)))

    def test_refused_foreground_never_sends_wheel(self):
        self.gui.SetForegroundWindow.side_effect = OSError("denied")
        with self.assertRaisesRegex(RuntimeError, "前台"):
            self.scroll()
        self.api.mouse_event.assert_not_called()
        self.assertEqual(self.cursor, (900, 700))
        # Temporary input queue attachments must be balanced, even on failure.
        calls = self.process.AttachThreadInput.call_args_list
        self.assertTrue(calls)
        self.assertEqual(sum(c.args[2] for c in calls), len(calls) // 2)

    def test_focus_loss_stops_further_wheels_and_preserves_user_focus(self):
        def wheel(*args):
            self.focus = 30

        self.api.mouse_event.side_effect = wheel
        with self.assertRaisesRegex(RuntimeError, "前台"):
            self.scroll()
        self.assertEqual(self.api.mouse_event.call_count, 1)
        self.assertEqual(self.focus, 30)
        self.assertEqual(self.cursor, (900, 700))

    def test_cursor_movement_does_not_interrupt_wheels(self):
        def wheel(*args):
            self.events.append(("wheel", self.focus, self.cursor, args[3]))
            self.cursor = (500, 500)

        self.api.mouse_event.side_effect = wheel
        self.scroll()
        self.assertEqual([e for e in self.events if e[0] == "wheel"], [("wheel", 10, (230, 650), -120)] * 3)
        self.assertEqual((self.focus, self.cursor), (20, (900, 700)))

    def test_cursor_is_confined_during_wheels_and_released_before_focus_restore(self):
        def wheel(*args):
            self.assertEqual(self.clip, (230, 650, 231, 651))

        self.api.mouse_event.side_effect = wheel
        self.scroll()
        self.assertEqual(self.clip, self.original_clip)
        release = self.events.index(("clip", self.original_clip))
        self.assertLess(release, self.events.index(("focus", 20)))

    def test_input_error_also_restores_cursor_clip(self):
        self.api.mouse_event.side_effect = RuntimeError("wheel failed")
        with self.assertRaisesRegex(RuntimeError, "wheel failed"):
            self.scroll()
        self.api.ClipCursor.assert_called_with(self.original_clip)
        self.assertEqual(self.clip, self.original_clip)

    def test_focus_loss_also_restores_cursor_clip(self):
        self.api.mouse_event.side_effect = lambda *args: setattr(self, "focus", 30)
        with self.assertRaisesRegex(RuntimeError, "前台"):
            self.scroll()
        self.api.ClipCursor.assert_called_with(self.original_clip)
        self.assertEqual(self.focus, 30)

    def test_clip_failure_sends_no_wheels_and_restores_desktop(self):
        def clip(rect):
            self.clip = rect
            if rect != self.original_clip:
                raise OSError("clip denied")

        self.api.ClipCursor.side_effect = clip
        with self.assertRaisesRegex(OSError, "clip denied"):
            self.scroll()
        self.api.mouse_event.assert_not_called()
        self.assertEqual(self.clip, self.original_clip)
        self.assertEqual((self.focus, self.cursor), (20, (900, 700)))

    def test_clip_restore_failure_releases_to_screen_without_hiding_input_error(self):
        def clip(rect):
            if rect == self.original_clip:
                raise OSError("restore clip denied")
            self.clip = rect

        self.api.ClipCursor.side_effect = clip
        self.api.mouse_event.side_effect = RuntimeError("wheel failed")
        with (
            self.assertLogs(self.module.logger, "WARNING"),
            self.assertRaisesRegex(RuntimeError, "wheel failed"),
        ):
            self.scroll()
        self.api.ClipCursor.assert_called_with(None)
        self.assertEqual((self.focus, self.cursor), (20, (900, 700)))

    def test_already_foreground_does_not_switch_away(self):
        self.focus = 10
        self.scroll()
        self.gui.SetForegroundWindow.assert_not_called()
        self.assertEqual(self.focus, 10)
        self.assertEqual(self.cursor, (900, 700))

    def test_zero_does_not_touch_desktop(self):
        self.scroll(0)
        self.gui.GetForegroundWindow.assert_not_called()
        self.api.SetCursorPos.assert_not_called()
        self.api.mouse_event.assert_not_called()

    def test_invalid_window_never_sends_input(self):
        self.gui.IsWindow.return_value = False
        with self.assertRaisesRegex(RuntimeError, "窗口"):
            self.scroll()
        self.api.mouse_event.assert_not_called()

    def test_restore_failure_does_not_mask_input_error_or_skip_cursor_restore(self):
        def focus(hwnd):
            if hwnd == 20:
                raise OSError("restore denied")
            self.focus = hwnd

        self.gui.SetForegroundWindow.side_effect = focus
        self.api.mouse_event.side_effect = RuntimeError("wheel failed")
        with (
            self.assertLogs(self.module.logger, "WARNING"),
            self.assertRaisesRegex(RuntimeError, "wheel failed"),
        ):
            self.scroll()
        self.assertEqual(self.cursor, (900, 700))

    def test_minimized_game_returns_to_minimized_state(self):
        self.gui.IsIconic.return_value = True
        self.scroll()
        import win32con

        self.gui.ShowWindow.assert_any_call(10, win32con.SW_RESTORE)
        self.gui.ShowWindow.assert_any_call(10, win32con.SW_MINIMIZE)

    def test_input_queue_fallback_activates_and_detaches(self):
        attempts = []

        def focus(hwnd):
            attempts.append(hwnd)
            if len(attempts) == 1:
                raise OSError("normal activation denied")
            self.focus = hwnd

        self.gui.SetForegroundWindow.side_effect = focus
        self.scroll()
        self.assertEqual(self.api.mouse_event.call_count, 3)
        self.assertEqual(self.focus, 20)
        self.assertEqual(
            [c.args for c in self.process.AttachThreadInput.call_args_list],
            [(1, 20, True), (1, 10, True), (1, 10, False), (1, 20, False)],
        )

    def test_minimized_state_restored_even_if_previous_focus_restore_fails(self):
        self.gui.IsIconic.return_value = True

        def focus(hwnd):
            if hwnd == 20:
                raise OSError("restore denied")
            self.focus = hwnd

        self.gui.SetForegroundWindow.side_effect = focus
        with self.assertLogs(self.module.logger, "WARNING"):
            self.scroll()
        import win32con

        self.gui.ShowWindow.assert_any_call(10, win32con.SW_MINIMIZE)
        self.assertEqual(self.cursor, (900, 700))


if __name__ == "__main__":
    unittest.main(verbosity=2)
