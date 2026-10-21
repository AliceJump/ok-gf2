"""输入安全回归；Win32 边界使用桩，不操作桌面。"""

import ast
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from src.interaction import Mouse


class InputSafetyTest(unittest.TestCase):
    def test_denied_activation_never_injects_alt_or_mouse(self):
        """Respect failed foreground activation without injecting global input."""
        import win32api
        import win32gui

        gui = Mock()
        gui.error = win32gui.error
        gui.GetForegroundWindow.return_value = 99
        gui.IsWindow.return_value = True
        gui.IsIconic.return_value = False
        gui.IsWindowVisible.return_value = True
        gui.SetForegroundWindow.side_effect = win32gui.error(0, "SetForegroundWindow", "denied")
        with (
            patch.object(Mouse, "win32gui", gui),
            patch.object(Mouse, "user32") as user,
            patch.object(Mouse, "time"),
            patch.object(win32api, "keybd_event") as key,
        ):
            result = Mouse.active_and_send_mouse_delta(77, dx=30)
        self.assertFalse(result)
        key.assert_not_called()
        user.mouse_event.assert_not_called()

    def test_failed_activation_does_not_execute_window_callback(self):
        """Skip the callback when foreground activation fails."""
        gui = Mock()
        gui.GetForegroundWindow.return_value = 99
        callback = Mock()
        with (
            patch.object(Mouse, "win32gui", gui),
            patch.object(Mouse, "active_and_send_mouse_delta", return_value=False),
        ):
            Mouse.run_in_window(77, callback)
        callback.assert_not_called()

    def test_window_restore_respects_user_switch_during_callback(self):
        """Leave the foreground unchanged when the user switches windows."""
        state = {"foreground": 99}
        gui = Mock()
        gui.GetForegroundWindow.side_effect = lambda: state["foreground"]

        def activate(hwnd, **kwargs):
            """Simulate successful window activation without touching the desktop."""
            state["foreground"] = hwnd
            return True

        with (
            patch.object(Mouse, "win32gui", gui),
            patch.object(Mouse, "active_and_send_mouse_delta", side_effect=activate),
        ):
            Mouse.run_in_window(77, lambda: state.update(foreground=123))
        gui.SetForegroundWindow.assert_not_called()

    def test_click_with_key_releases_modifier_when_click_fails(self):
        """Release the modifier after a failed click and retain the click error."""
        path = Path(__file__).resolve().parents[1] / "src/core/BaseGfTask.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "click_with_key")
        ns = {}
        import threading

        ns.update(threading=threading, time=Mock())
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), "exec"), ns)
        task = Mock()
        task.click.side_effect = RuntimeError("click failed")
        with self.assertRaisesRegex(RuntimeError, "click failed"):
            ns["click_with_key"](task, "alt", object())
        task.send_key_up.assert_called_once_with("alt")
