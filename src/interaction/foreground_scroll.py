"""Temporarily foreground the game for real wheel input, then restore the desktop."""

import ctypes
import logging
import time
from ctypes import wintypes

import win32api
import win32con
import win32gui
import win32process

# Use the application's configured handlers so wheel diagnostics reach its log.
logger = logging.getLogger("ok.foreground_scroll")

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetClipCursor.argtypes = [ctypes.POINTER(wintypes.RECT)]
_user32.GetClipCursor.restype = wintypes.BOOL


def _get_cursor_clip():
    rect = wintypes.RECT()
    if not _user32.GetClipCursor(ctypes.byref(rect)):
        raise ctypes.WinError(ctypes.get_last_error())
    return rect.left, rect.top, rect.right, rect.bottom


def _foreground(hwnd):
    """Verify foreground ownership; temporarily attach input queues if needed."""
    if win32gui.GetForegroundWindow() == hwnd:
        return
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        logger.debug("直接切换前台窗口失败，尝试临时连接输入队列", exc_info=True)
    if win32gui.GetForegroundWindow() == hwnd:
        return

    current_thread = win32api.GetCurrentThreadId()
    attached = []
    try:
        targets = (win32gui.GetForegroundWindow(), hwnd)
        for target in dict.fromkeys(targets):
            if not target:
                continue
            target_thread = win32process.GetWindowThreadProcessId(target)[0]
            if target_thread == current_thread or target_thread in attached:
                continue
            try:
                win32process.AttachThreadInput(current_thread, target_thread, True)
                attached.append(target_thread)
            except Exception:
                logger.debug("临时连接窗口输入队列失败", exc_info=True)
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
        if win32gui.GetForegroundWindow() != hwnd:
            raise RuntimeError("窗口未能进入前台")
    except Exception as error:
        raise RuntimeError("窗口未能进入前台") from error
    finally:
        for target_thread in reversed(attached):
            try:
                win32process.AttachThreadInput(current_thread, target_thread, False)
            except Exception:
                logger.warning("断开临时窗口输入队列失败", exc_info=True)


def scroll_in_foreground(hwnd, x, y, scroll_amount):
    if not scroll_amount:
        return
    if not win32gui.IsWindow(hwnd):
        raise RuntimeError("滚动失败：游戏窗口无效")
    x, y = int(x), int(y)
    previous_window = win32gui.GetForegroundWindow()
    previous_cursor = win32api.GetCursorPos()
    previous_clip = _get_cursor_clip()
    clip_changed = False
    was_minimized = win32gui.IsIconic(hwnd)
    try:
        if was_minimized:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        _foreground(hwnd)
        time.sleep(0.15)
        left, top, right, bottom = win32gui.GetClientRect(hwnd)
        if not (left <= x < right and top <= y < bottom):
            raise RuntimeError("滚动失败：鼠标位置不在游戏客户区内")
        position = win32gui.ClientToScreen(hwnd, (x, y))
        # Keep physical mouse motion from moving the wheel target off the list.
        # A one-pixel rectangle is held only for this short wheel sequence.
        cursor_clip = (*position, position[0] + 1, position[1] + 1)
        clip_changed = True
        win32api.ClipCursor(cursor_clip)
        win32api.SetCursorPos(position)
        time.sleep(0.1)
        delta = win32con.WHEEL_DELTA if scroll_amount > 0 else -win32con.WHEEL_DELTA
        logger.info("前台滚动开始：窗口=%s 客户区=(%s,%s) 格数=%s", hwnd, x, y, scroll_amount)
        for _ in range(abs(scroll_amount)):
            if win32gui.GetForegroundWindow() != hwnd:
                raise RuntimeError("滚动中游戏失去前台，停止发送滚轮")
            win32api.SetCursorPos(position)
            win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, delta, 0)
            time.sleep(0.03)
        time.sleep(0.15)
        logger.info("前台滚轮输入已发送：格数=%s", scroll_amount)
    finally:
        # Release our confinement before returning control to another window.
        if clip_changed:
            try:
                win32api.ClipCursor(previous_clip)
            except Exception:
                logger.warning("滚动结束后恢复鼠标活动范围失败，尝试解除限制", exc_info=True)
                try:
                    win32api.ClipCursor(None)
                except Exception:
                    logger.warning("滚动结束后解除鼠标限制失败", exc_info=True)
        # Restore only while we still own focus; respect a user's intervening switch.
        try:
            if (
                previous_window != hwnd
                and win32gui.GetForegroundWindow() == hwnd
                and previous_window
                and win32gui.IsWindow(previous_window)
            ):
                _foreground(previous_window)
        except Exception:
            logger.warning("滚动结束后恢复前台窗口失败", exc_info=True)
        try:
            if was_minimized and win32gui.IsWindow(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        except Exception:
            logger.warning("滚动结束后恢复最小化状态失败", exc_info=True)
        try:
            win32api.SetCursorPos(previous_cursor)
        except Exception:
            logger.warning("滚动结束后恢复鼠标位置失败", exc_info=True)
        logger.info("滚动窗口恢复结束：原前台=%s 当前前台=%s", previous_window, win32gui.GetForegroundWindow())
