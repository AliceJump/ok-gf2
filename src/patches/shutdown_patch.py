"""兼容 ok-script 2.0.5 的退出清理；真实权限失败仍明确报告。"""

import os
from functools import wraps

import psutil

_installed = False


def guard_destroy(original, is_window):
    @wraps(original)
    def guarded(self):
        hwnd = self.hwnd_window.hwnd
        if hwnd and is_window(hwnd):
            return original(self)
        return None

    return guarded


def stop_launcher(pid, executable, timeout, process_factory, logger):
    if not pid or not executable:
        return False
    try:
        process = process_factory(pid)
        expected = os.path.normcase(os.path.realpath(executable))
        actual = os.path.normcase(os.path.realpath(process.exe()))
        if actual != expected:
            logger.warning("启动器 PID 已被其他进程使用，跳过终止")
            return False
        process.terminate()
        process.wait(timeout=timeout)
        return True
    except psutil.NoSuchProcess:
        return True
    except (psutil.AccessDenied, psutil.TimeoutExpired, OSError) as error:
        logger.warning(f"启动器未能退出，请手动关闭启动器：{error}")
        return False


def install_shutdown_patch():
    global _installed
    if _installed:
        return
    import pyappify
    import win32gui
    from ok.device.interaction_methods.genshin import GenshinInteraction

    GenshinInteraction.on_destroy = guard_destroy(GenshinInteraction.on_destroy, win32gui.IsWindow)

    def kill_launcher(timeout=30, exit_event=None):
        if exit_event is not None and exit_event.is_set():
            return False
        return stop_launcher(
            pyappify.pid, pyappify.pyappify_executable, timeout, psutil.Process, pyappify._get_logger()
        )

    pyappify.kill_pyappify = kill_launcher
    _installed = True
