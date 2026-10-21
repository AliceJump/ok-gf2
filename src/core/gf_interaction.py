"""
少前2 的输入层：鼠标走 Interception 会话鼠标（真实输入），键盘沿用 GenshinInteraction 的 PostMessage。

绑定不到会话鼠标（不在 RDP 会话 / 没装 Interception 驱动 / 设置里关掉）时，每个动作都原样退回
GenshinInteraction，行为和改之前一样。真实点击落在光标下的窗口，所以点之前若游戏不在前台会先把它提到前台
（ok 的 bring_to_front），app 窗口会被全屏游戏盖住——这是真实输入的代价，用 web 页面看进度不受影响。
"""

import time

from ok.device.interaction_methods.genshin import GenshinInteraction
from ok.util.logger import Logger

from src.core.input_config import INPUT_OPTION_NAME, KEY_SESSION_MOUSE
from src.core.session_mouse import BTN_LEFT, BUTTON_OF_KEY, SessionMouseDevice

logger = Logger.get_logger(__name__)


class GfInteraction(GenshinInteraction):
    def __init__(self, capture, hwnd_window):
        super().__init__(capture, hwnd_window)
        self.session_mouse = SessionMouseDevice()
        self.session_mouse_ok = self.session_mouse.open()
        if self.session_mouse_ok:
            logger.info(f"鼠标输入：Interception 会话鼠标（{self.session_mouse.device_path}），键盘仍走 PostMessage")
        else:
            logger.warning("鼠标输入：会话鼠标不可用，退回 PostMessage（Genshin）")

    # ---- 开关 / 坐标 ----
    def session_mouse_enabled(self):
        if not self.session_mouse_ok:
            return False
        try:
            from ok import og

            return bool(og.executor.global_config.get_config(INPUT_OPTION_NAME).get(KEY_SESSION_MOUSE, True))
        except Exception:  # 没有 executor（单测 / 初始化早期）时按开着算
            return True

    def _abs(self, x, y):
        return self.capture.get_abs_cords(int(x), int(y))

    def _ensure_front(self):
        """真实点击落在光标下的窗口；游戏不在前台就先提到前台，提不动也照点（点在游戏区域会顺便激活）。"""
        if self.hwnd_window.is_foreground():
            return True
        ok = self.hwnd_window.bring_to_front()
        time.sleep(0.05)
        if not ok:
            logger.warning("游戏窗口提到前台失败，仍用会话鼠标点击")
        return ok

    def _use_session_mouse(self, x, y):
        return self.session_mouse_enabled() and x >= 0 and y >= 0

    # ---- 鼠标动作 ----
    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.02, move=True, key="left"):
        if not self._use_session_mouse(x, y):
            return super().click(x, y, move_back=move_back, name=name, down_time=down_time, move=move, key=key)
        self._ensure_front()
        ax, ay = self._abs(x, y)
        if not self.session_mouse.click(ax, ay, BUTTON_OF_KEY.get(key, BTN_LEFT), down_time=down_time):
            logger.warning(f"会话鼠标点击 ({x}, {y}) 失败，这一下退回 PostMessage")
            return super().click(x, y, move_back=move_back, name=name, down_time=down_time, move=move, key=key)

    def right_click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.02):
        return self.click(x, y, move_back=move_back, name=name, down_time=down_time, key="right")

    def middle_click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.01):
        return self.click(x, y, move_back=move_back, name=name, down_time=down_time, key="middle")

    def move(self, x, y, down_btn=0):
        if not self._use_session_mouse(x, y):
            return super().move(x, y, down_btn)
        self.session_mouse.move(*self._abs(x, y))

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        if not self._use_session_mouse(x, y):
            return super().mouse_down(x, y, name=name, key=key)
        self._ensure_front()
        self.session_mouse.move(*self._abs(x, y))
        self.session_mouse.press(BUTTON_OF_KEY.get(key, BTN_LEFT))

    def mouse_up(self, x=-1, y=-1, key="left"):
        if not self.session_mouse_enabled():
            return super().mouse_up(x, y, key=key)
        if x >= 0 and y >= 0:
            self.session_mouse.move(*self._abs(x, y))
        self.session_mouse.release()

    def swipe(self, x1, y1, x2, y2, duration=3, settle_time=0.1):
        if not self._use_session_mouse(x1, y1):
            return super().swipe(x1, y1, x2, y2, duration=duration, settle_time=settle_time)
        self._ensure_front()
        steps = max(int(duration / 100), 1)
        self.session_mouse.move(*self._abs(x1, y1))
        self.session_mouse.press(BTN_LEFT)
        for i in range(1, steps + 1):
            self.session_mouse.move(*self._abs(x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps), settle=0)
            time.sleep(0.01)
        if settle_time > 0:
            time.sleep(settle_time)
        self.session_mouse.release()

    def scroll(self, x, y, scroll_amount):
        if not self._use_session_mouse(x, y):
            return super().scroll(x, y, scroll_amount)
        self._ensure_front()
        self.session_mouse.wheel(*self._abs(x, y), scroll_amount)

    def on_destroy(self):
        self.session_mouse.close()
        super().on_destroy()
