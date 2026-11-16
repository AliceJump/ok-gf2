"""
系统面板占着前台（实录 2026-11-16）：任务栏右下角的「快速设置」（ShellExperienceHost）开着时游戏切不回前台，
只按一次 Esc 把面板关掉；前台是别的程序时一个键都不发。
"""

import unittest
from unittest.mock import Mock, call, patch

from src.core import foreground

FLYOUT = 66234


def fakes(exe="C:\\Windows\\SystemApps\\ShellExperienceHost_cw5n1h2txyewy\\ShellExperienceHost.exe", current=FLYOUT):
    gui, api, process, con = Mock(), Mock(), Mock(), Mock()
    gui.GetForegroundWindow.return_value = current
    process.GetWindowThreadProcessId.return_value = (42, 1000)
    process.GetModuleFileNameEx.return_value = exe
    api.OpenProcess.return_value = "handle"
    con.VK_ESCAPE, con.KEYEVENTF_KEYUP = 0x1B, 2
    return gui, api, process, con


def run(fn, *args, gui, api, process, con):
    with (
        patch.multiple(foreground, win32gui=gui, win32api=api, win32process=process, win32con=con),
        patch.object(foreground.time, "sleep"),
    ):
        return fn(*args)


class DismissShellFlyoutTest(unittest.TestCase):
    def test_quick_settings_gets_one_escape_press(self):
        gui, api, process, con = fakes()
        self.assertTrue(run(foreground.dismiss_shell_flyout, FLYOUT, gui=gui, api=api, process=process, con=con))
        self.assertEqual(api.keybd_event.call_args_list, [call(0x1B, 0, 0, 0), call(0x1B, 0, 2, 0)])

    def test_start_menu_and_search_count_as_flyouts(self):
        for exe in ("StartMenuExperienceHost.exe", "SearchHost.exe"):
            gui, api, process, con = fakes(exe=exe)
            self.assertTrue(run(foreground.dismiss_shell_flyout, FLYOUT, gui=gui, api=api, process=process, con=con))

    def test_other_program_in_front_gets_no_key(self):
        for exe in ("D:\\GF2 Game\\GF2_Exilium.exe", "explorer.exe", "powershell.exe"):
            gui, api, process, con = fakes(exe=exe)
            self.assertFalse(run(foreground.dismiss_shell_flyout, FLYOUT, gui=gui, api=api, process=process, con=con))
            api.keybd_event.assert_not_called()

    def test_flyout_already_gone_gets_no_key(self):
        gui, api, process, con = fakes(current=459332)
        self.assertFalse(run(foreground.dismiss_shell_flyout, FLYOUT, gui=gui, api=api, process=process, con=con))
        api.keybd_event.assert_not_called()

    def test_no_foreground_window_gets_no_key(self):
        gui, api, process, con = fakes()
        self.assertFalse(run(foreground.dismiss_shell_flyout, 0, gui=gui, api=api, process=process, con=con))
        api.keybd_event.assert_not_called()


class WindowProcessTest(unittest.TestCase):
    def test_lowercase_exe_name_and_handle_closed(self):
        gui, api, process, con = fakes()
        name = run(foreground.window_process, FLYOUT, gui=gui, api=api, process=process, con=con)
        self.assertEqual(name, "shellexperiencehost.exe")
        api.OpenProcess.assert_called_once_with(0x1000, False, 1000)
        api.CloseHandle.assert_called_once_with("handle")

    def test_unreadable_process_gives_empty_name(self):
        gui, api, process, con = fakes()
        process.GetModuleFileNameEx.side_effect = OSError("denied")
        self.assertEqual(run(foreground.window_process, FLYOUT, gui=gui, api=api, process=process, con=con), "")
        api.CloseHandle.assert_called_once_with("handle")


if __name__ == "__main__":
    unittest.main()
