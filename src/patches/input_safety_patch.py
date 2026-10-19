"""桌面输入保护：不锁定全局输入，并可靠释放按键。"""

import logging
import time

logger = logging.getLogger(__name__)


def install_input_safety_patch():
    """Install idempotent background input hooks without globally locking input."""
    try:
        import win32api
        import win32con
        from ok.device.interaction_methods.genshin import GenshinInteraction
    except ModuleNotFoundError as error:
        if error.name not in {"ok.device", "ok.device.interaction_methods", "ok.device.interaction_methods.genshin"}:
            raise
        return False
    if getattr(GenshinInteraction, "_gf2_input_safety", False):
        return True

    def operate(self, fun, block=False, require_foreground=False):
        """Run input and restore background window state without hiding operation errors."""
        background = not self.hwnd_window.is_foreground()
        position = win32api.GetCursorPos() if background else None
        try:
            if background:
                self.activate()
                if require_foreground and not self.hwnd_window.is_foreground():
                    logger.warning("游戏窗口激活失败，跳过需要前台窗口的输入")
                    return False
            return fun()
        finally:
            if background:
                try:
                    self.deactivate()
                except Exception:
                    logger.warning("输入结束后停用游戏窗口失败", exc_info=True)
                try:
                    win32api.SetCursorPos(position)
                except Exception:
                    logger.warning("恢复鼠标位置失败", exc_info=True)

    def send_key_up(self, key):
        """Release the key through window messages and tolerate deactivation failure."""
        try:
            self.post_interaction.send_key_up(key)
        finally:
            try:
                self.deactivate()
            except Exception:
                logger.warning("松开按键后停用游戏窗口失败", exc_info=True)

    def scroll(self, x, y, scroll_amount):
        """Send a real wheel event while the game owns the foreground."""
        from src.interaction.Mouse import run_in_window

        position = win32api.GetCursorPos()
        try:
            result = run_in_window(self.hwnd_window.hwnd, self.do_scroll, x, y, scroll_amount)
            if result is False:
                raise RuntimeError("游戏窗口未能进入前台，未发送滚轮输入")
            return result
        finally:
            try:
                win32api.SetCursorPos(position)
            except Exception:
                logger.warning("滚轮输入后恢复鼠标位置失败", exc_info=True)

    def move_mouse_relative(self, dx, dy):
        """Move the real mouse only after confirming that the game is foreground."""
        return operate(self, lambda: self.do_move_mouse_relative(dx, dy), require_foreground=True)

    def do_send_key(self, key, down_time=0.02):
        """Always post key release after a timed key press, including interrupted holds."""
        vk_code = self.get_key_by_str(key)
        try:
            self.post(win32con.WM_KEYDOWN, vk_code, 0x1E0001)
            if down_time > 0.1:
                time.sleep(down_time)
            else:
                self.post(win32con.WM_CHAR, vk_code, 0x1E0001)
        finally:
            self.post(win32con.WM_KEYUP, vk_code, 0xC01E0001)
        time.sleep(down_time if down_time <= 0.1 else 0.02)

    def do_click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.02, move=True, key="left"):
        """Hold the selected mouse button and release it even when interrupted."""
        position = self.make_mouse_position(x, y)
        buttons = {
            "left": (win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, win32con.WM_LBUTTONUP),
            "middle": (win32con.WM_MBUTTONDOWN, win32con.MK_MBUTTON, win32con.WM_MBUTTONUP),
            "right": (win32con.WM_RBUTTONDOWN, win32con.MK_RBUTTON, win32con.WM_RBUTTONUP),
        }
        down, flag, up = buttons[key]
        try:
            self.post(down, flag, position)
            time.sleep(down_time)
        finally:
            self.post(up, 0, position)
        # 留出一次消息处理窗口，再由 operate 停用窗口并恢复光标。
        time.sleep(down_time)

    GenshinInteraction.operate = operate
    GenshinInteraction.send_key_up = send_key_up
    GenshinInteraction.scroll = scroll
    GenshinInteraction.move_mouse_relative = move_mouse_relative
    GenshinInteraction.do_send_key = do_send_key
    GenshinInteraction.do_click = do_click
    GenshinInteraction._gf2_input_safety = True
    return True
