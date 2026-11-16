"""
被前台锁挡住时把游戏切到前台。

Windows 只让「刚收到过用户输入」的进程调用 SetForegroundWindow；无人值守时 ok-gf2 是后台进程，
别的窗口（开机后的资源管理器、刚弹出的控制台）在前台时直接调用会报「拒绝访问」。
把本线程的输入状态临时挂到当前前台窗口的线程上，系统就当作同一个输入队列，允许切换。
实录 2026-10-26：重启后本机桌面跑一键日常，「情报和战前补给」滚补给列表时 SetForegroundWindow 报错，整项失败。

系统面板（任务栏右下角的「快速设置」、通知中心、开始菜单、搜索）占着前台时，上面两种办法都切不回游戏，
只能像人一样按一下 Esc 把面板关掉，游戏自己就回到前台。
"""

import os
import time

import win32api
import win32con
import win32gui
import win32process

# 这些进程的前台窗口是系统弹出面板，Esc 就能关掉（不会关掉别的程序）
SHELL_FLYOUT_PROCESSES = frozenset({"shellexperiencehost.exe", "startmenuexperiencehost.exe", "searchhost.exe"})
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


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


def window_process(hwnd):
    """窗口所属进程的 exe 文件名（小写）；拿不到返回空串。"""
    handle = None
    try:
        pid = win32process.GetWindowThreadProcessId(hwnd)[1]
        handle = win32api.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        return os.path.basename(win32process.GetModuleFileNameEx(handle, 0)).lower()
    except Exception:
        return ""
    finally:
        if handle is not None:
            win32api.CloseHandle(handle)


def dismiss_shell_flyout(foreground):
    """
    前台是系统面板就发一次 Esc（真实按键，落在前台窗口上）把它关掉；发了返回 True，不是系统面板返回 False。
    实录 2026-11-16：会话里有人点开了任务栏右下角的「快速设置」（ShellExperienceHost 的 CoreWindow），面板一直占着前台，
    游戏提不到前台；活动层按住 alt 点「茶歇一刻」后松开 alt 时游戏被当成后台、伪造了失活，没进水吧反而弹出
    「是否离开活动层?」，窗口还被最小化，喝水失败。2026-11-15 在另一个会话里发一次 Esc 面板就关了、游戏自动回前台。
    """
    if not foreground or window_process(foreground) not in SHELL_FLYOUT_PROCESSES:
        return False
    if win32gui.GetForegroundWindow() != foreground:  # 刚好自己关了，别把 Esc 发给别的窗口
        return False
    win32api.keybd_event(win32con.VK_ESCAPE, 0, 0, 0)
    time.sleep(0.05)
    win32api.keybd_event(win32con.VK_ESCAPE, 0, win32con.KEYEVENTF_KEYUP, 0)
    return True
