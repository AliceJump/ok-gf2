"""前台锁兜底：挂输入线程切前台，结束后一定解除挂接。"""

import unittest
from unittest.mock import Mock, patch

from src.core import foreground


class AttachForegroundTest(unittest.TestCase):
    def fakes(self, switch=True):
        state = {"foreground": 99}
        gui, api, process = Mock(), Mock(), Mock()
        gui.GetForegroundWindow.side_effect = lambda: state["foreground"]
        gui.SetForegroundWindow.side_effect = lambda hwnd: state.update(foreground=hwnd) if switch else None
        api.GetCurrentThreadId.return_value = 7
        process.GetWindowThreadProcessId.return_value = (42, 1000)
        process.AttachThreadInput.return_value = True
        return state, gui, api, process

    def run_attach(self, gui, api, process, hwnd=123, fg=99):
        with patch.multiple(foreground, win32gui=gui, win32api=api, win32process=process):
            return foreground.attach_foreground(hwnd, fg)

    def test_switches_while_attached_and_detaches(self):
        state, gui, api, process = self.fakes()
        self.assertTrue(self.run_attach(gui, api, process))
        self.assertEqual(123, state["foreground"])
        self.assertEqual([(7, 42, True), (7, 42, False)], [c.args for c in process.AttachThreadInput.call_args_list])

    def test_detaches_even_when_switch_raises(self):
        state, gui, api, process = self.fakes()
        gui.SetForegroundWindow.side_effect = OSError("denied")
        self.assertFalse(self.run_attach(gui, api, process))
        process.AttachThreadInput.assert_called_with(7, 42, False)

    def test_switch_without_effect_reports_failure(self):
        state, gui, api, process = self.fakes(switch=False)
        self.assertFalse(self.run_attach(gui, api, process))

    def test_no_foreground_window_skips_attach(self):
        state, gui, api, process = self.fakes()
        self.assertTrue(self.run_attach(gui, api, process, fg=0))
        process.AttachThreadInput.assert_not_called()


if __name__ == "__main__":
    unittest.main()
