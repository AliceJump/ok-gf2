"""退出时失效窗口和启动器 PID 的回归测试，不操作真实进程。"""

import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from unittest.mock import patch as mock_patch

import psutil

source = Path(__file__).resolve().parents[1] / "src/patches/shutdown_patch.py"
spec = importlib.util.spec_from_file_location("shutdown_patch", source)
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)


class ShutdownPatchTest(unittest.TestCase):
    def test_legacy_dependency_without_device_module_still_installs_launcher_cleanup(self):
        import builtins

        original_import = builtins.__import__
        launcher = SimpleNamespace(pid=123, pyappify_executable="C:/app/ok-gf2.exe")

        def legacy_import(name, *args, **kwargs):
            if name == "ok.device.interaction_methods.genshin":
                raise ModuleNotFoundError("No module named ok.device", name="ok.device")
            return original_import(name, *args, **kwargs)

        process = Mock()
        process.exe.return_value = launcher.pyappify_executable
        with (
            mock_patch.dict(sys.modules, {"pyappify": launcher}),
            mock_patch.object(builtins, "__import__", side_effect=legacy_import),
            mock_patch.object(patch, "_installed", False),
            mock_patch.object(patch.psutil, "Process", return_value=process),
        ):
            patch.install_shutdown_patch()
            self.assertTrue(launcher.kill_pyappify(timeout=2))
        process.terminate.assert_called_once_with()

    def test_installed_launcher_supports_old_and_current_pyappify_loggers(self):
        """Verify installed launcher supports old and current pyappify loggers."""
        for has_logger in (False, True):
            with self.subTest(has_logger=has_logger):
                launcher = SimpleNamespace(pid=123, pyappify_executable="C:/app/ok-gf2.exe")
                if has_logger:
                    launcher._get_logger = Mock(return_value=Mock())
                interaction = SimpleNamespace(on_destroy=Mock())
                modules = {
                    "pyappify": launcher,
                    "win32gui": SimpleNamespace(IsWindow=lambda hwnd: True),
                    "ok.device.interaction_methods.genshin": SimpleNamespace(GenshinInteraction=interaction),
                }
                process = Mock()
                process.exe.return_value = launcher.pyappify_executable
                with (
                    mock_patch.dict(sys.modules, modules),
                    mock_patch.object(patch, "_installed", False),
                    mock_patch.object(patch.psutil, "Process", return_value=process),
                ):
                    patch.install_shutdown_patch()
                    try:
                        result = launcher.kill_pyappify(timeout=2)
                    except AttributeError as error:
                        self.fail(f"Legacy pyappify cannot clean up: {error}")
                self.assertTrue(result)
                process.terminate.assert_called_once_with()
                process.wait.assert_called_once_with(timeout=2)
                if has_logger:
                    launcher._get_logger.assert_called_once_with()

    def test_closed_game_never_calls_original_activation(self):
        """Verify closed game never calls original activation."""
        original = Mock()
        guarded = patch.guard_destroy(original, lambda hwnd: False)
        guarded(SimpleNamespace(hwnd_window=SimpleNamespace(hwnd=123)))
        original.assert_not_called()

    def test_existing_game_retains_normal_cleanup(self):
        """Verify existing game retains normal cleanup."""
        original = Mock()
        guarded = patch.guard_destroy(original, lambda hwnd: True)
        task = SimpleNamespace(hwnd_window=SimpleNamespace(hwnd=123))
        guarded(task)
        original.assert_called_once_with(task)

    def test_missing_launcher_is_already_stopped(self):
        """Verify missing launcher is already stopped."""
        process_factory = Mock(side_effect=psutil.NoSuchProcess(123))
        self.assertTrue(patch.stop_launcher(123, "C:/app/ok-gf2.exe", 2, process_factory, Mock()))

    def test_reused_pid_does_not_terminate_unrelated_process(self):
        """Verify reused pid does not terminate unrelated process."""
        process = Mock()
        process.exe.return_value = "C:/other/unrelated.exe"
        self.assertFalse(patch.stop_launcher(123, "C:/app/ok-gf2.exe", 2, lambda pid: process, Mock()))
        process.terminate.assert_not_called()

    def test_matching_launcher_uses_terminate_and_wait(self):
        """Verify matching launcher uses terminate and wait."""
        process = Mock()
        process.exe.return_value = "C:/app/ok-gf2.exe"
        self.assertTrue(patch.stop_launcher(123, "C:/app/ok-gf2.exe", 2, lambda pid: process, Mock()))
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=2)

    def test_denied_termination_is_reported_without_claiming_success(self):
        """Verify denied termination is reported without claiming success."""
        process = Mock()
        process.exe.return_value = "C:/app/ok-gf2.exe"
        process.terminate.side_effect = psutil.AccessDenied(123)
        log = Mock()
        self.assertFalse(patch.stop_launcher(123, "C:/app/ok-gf2.exe", 2, lambda pid: process, log))
        log.warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
