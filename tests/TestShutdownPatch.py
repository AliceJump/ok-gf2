"""退出时失效窗口和启动器 PID 的回归测试，不操作真实进程。"""

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import psutil

source = Path(__file__).resolve().parents[1] / "src/patches/shutdown_patch.py"
if source.exists():
    spec = importlib.util.spec_from_file_location("shutdown_patch", source)
    patch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patch)
else:
    patch = SimpleNamespace()


class ShutdownPatchTest(unittest.TestCase):
    def test_closed_game_never_calls_original_activation(self):
        original = Mock()
        guarded = patch.guard_destroy(original, lambda hwnd: False)
        guarded(SimpleNamespace(hwnd_window=SimpleNamespace(hwnd=123)))
        original.assert_not_called()

    def test_existing_game_retains_normal_cleanup(self):
        original = Mock()
        guarded = patch.guard_destroy(original, lambda hwnd: True)
        task = SimpleNamespace(hwnd_window=SimpleNamespace(hwnd=123))
        guarded(task)
        original.assert_called_once_with(task)

    def test_missing_launcher_is_already_stopped(self):
        process_factory = Mock(side_effect=psutil.NoSuchProcess(123))
        self.assertTrue(patch.stop_launcher(123, "C:/app/ok-gf2.exe", 2, process_factory, Mock()))

    def test_reused_pid_does_not_terminate_unrelated_process(self):
        process = Mock()
        process.exe.return_value = "C:/other/unrelated.exe"
        self.assertFalse(patch.stop_launcher(123, "C:/app/ok-gf2.exe", 2, lambda pid: process, Mock()))
        process.terminate.assert_not_called()

    def test_matching_launcher_uses_terminate_and_wait(self):
        process = Mock()
        process.exe.return_value = "C:/app/ok-gf2.exe"
        self.assertTrue(patch.stop_launcher(123, "C:/app/ok-gf2.exe", 2, lambda pid: process, Mock()))
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=2)

    def test_denied_termination_is_reported_without_claiming_success(self):
        process = Mock()
        process.exe.return_value = "C:/app/ok-gf2.exe"
        process.terminate.side_effect = psutil.AccessDenied(123)
        log = Mock()
        self.assertFalse(patch.stop_launcher(123, "C:/app/ok-gf2.exe", 2, lambda pid: process, log))
        log.warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
