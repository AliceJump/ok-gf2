"""
被前台锁挡住时把游戏切到前台。

Windows 只让「刚收到过用户输入」的进程调用 SetForegroundWindow；无人值守时 ok-gf2 是后台进程，
别的窗口（开机后的资源管理器、刚弹出的控制台）在前台时直接调用会报「拒绝访问」。
把本线程的输入状态临时挂到当前前台窗口的线程上，系统就当作同一个输入队列，允许切换。
实录 2026-10-26：重启后本机桌面跑一键日常，「情报和战前补给」滚补给列表时 SetForegroundWindow 报错，整项失败。
"""

import win32api
import win32gui
import win32process


def attach_foreground(hwnd, foreground):
    """挂到前台窗口的输入线程上再切前台；切成功返回 True，任何一步失败返回 False。"""
    try:
        target = win32process.GetWindowThreadProcessId(foreground)[0] if foreground else 0
        current = win32api.GetCurrentThreadId()
        attached = bool(target) and target != current and win32process.AttachThreadInput(current, target, True)
        try:
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
        finally:
            if attached:
                win32process.AttachThreadInput(current, target, False)
    except Exception:
        return False
    return win32gui.GetForegroundWindow() == hwnd
