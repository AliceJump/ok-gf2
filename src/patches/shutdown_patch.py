"""兼容 ok-script 2.0.5 的退出清理；真实权限失败仍明确报告。"""

import logging
import os
from functools import wraps

import psutil

_installed = False


def guard_destroy(original, is_window):
    """只对仍有效的游戏窗口执行原销毁逻辑。"""

    @wraps(original)
    def guarded(self):
        """跳过已失效窗口，避免退出时激活不存在的窗口。"""
        hwnd = self.hwnd_window.hwnd
        if hwnd and is_window(hwnd):
            return original(self)
        return None

    return guarded


def stop_launcher(pid, executable, timeout, process_factory, logger):
    """核对进程路径后终止启动器，返回是否退出并报告权限失败。"""
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
    """幂等安装退出保护，兼容普通和 DML 依赖中的日志接口。"""
    global _installed
    if _installed:
        return
    import pyappify

    try:
        from ok.device.interaction_methods.genshin import GenshinInteraction
    except ModuleNotFoundError as error:
        if error.name not in {"ok.device", "ok.device.interaction_methods", "ok.device.interaction_methods.genshin"}:
            raise
        logging.getLogger(__name__).info("旧版 ok-script 无桌面交互模块，跳过窗口退出保护")
    else:
        import win32gui

        GenshinInteraction.on_destroy = guard_destroy(GenshinInteraction.on_destroy, win32gui.IsWindow)

    def kill_launcher(timeout=30, exit_event=None):
        """取消退出时不终止启动器，缺少私有日志接口时使用标准日志。"""
        if exit_event is not None and exit_event.is_set():
            return False
        return stop_launcher(
            pyappify.pid,
            pyappify.pyappify_executable,
            timeout,
            psutil.Process,
            getattr(pyappify, "_get_logger", lambda: logging.getLogger(__name__))(),
        )

    pyappify.kill_pyappify = kill_launcher
    _installed = True
