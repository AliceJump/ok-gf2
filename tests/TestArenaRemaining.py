"""竞技场剩余次数：段位晋升弹窗盖住计数时先关弹窗再读，读不到时给出明确错误。"""

import re
import unittest
from types import SimpleNamespace

from tests.TestChenyanAssist import battle

arena_remaining = battle["arena_remaining"]
arena_remaining.__globals__.setdefault("stamina_re", re.compile(r"^\d+/\d+"))


class ArenaDevice:
    def __init__(self, popup=False, count="2/3", taps=()):
        """popup：晋升弹窗是否盖着；count：右上角计数（None 表示一直读不到）；taps：依次弹出、要点掉的提示。"""
        self.popup = popup
        self.count = count
        self.taps = list(taps)
        self.clicks = []
        self.backs = 0
        self.shots = []
        self.logs = []

    def ocr(self, *args, match=None, **kwargs):
        """弹窗盖着时读不到计数，只读到晋升文字。"""
        if match is battle["arena_remaining"].__globals__["stamina_re"]:
            if self.popup or self.taps or self.count is None:
                return []
            return [SimpleNamespace(name=self.count)]
        if self.taps and match.search(self.taps[0]):
            return [SimpleNamespace(name=self.taps[0])]
        if self.popup and match.search("您已晋升至职业·三"):
            return [SimpleNamespace(name="您已晋升至职业·三")]
        return []

    def back(self, **kwargs):
        """ESC 关掉晋升弹窗。"""
        self.backs += 1
        self.popup = False

    def click(self, box, **kwargs):
        """点提示文字关掉最上层的弹窗，下一个（如有）接着弹出。"""
        self.clicks.append(box.name)
        self.taps.pop(0)

    def sleep(self, *args):
        pass

    def log_info(self, message, **kwargs):
        self.logs.append(message)

    def screenshot(self, name=None, **kwargs):
        self.shots.append(name)


class TestArenaRemaining(unittest.TestCase):
    def test_reads_count_directly(self):
        device = ArenaDevice()
        self.assertEqual(2, arena_remaining(device))
        self.assertEqual(0, device.backs)

    def test_promotion_popup_is_closed_before_reading(self):
        """实录 2026-10-25：首次升段弹「您已晋升至职业·三」盖住计数，原来直接越界报错。"""
        device = ArenaDevice(popup=True, count="0/3")
        self.assertEqual(0, arena_remaining(device))
        self.assertEqual(1, device.backs)

    def test_new_season_popups_are_tapped_away_before_reading(self):
        """实录 2026-10-26：新周期先弹「实兵演习 已开启」，再弹「您已重置为职业·四」，都要点任意位置继续。"""
        device = ArenaDevice(count="3/3", taps=["点击任意位置继续", "点击屏幕任意位置继续"])
        self.assertEqual(3, arena_remaining(device))
        self.assertEqual(["点击任意位置继续", "点击屏幕任意位置继续"], device.clicks)
        self.assertEqual(0, device.backs)

    def test_missing_count_raises_clear_error(self):
        device = ArenaDevice(count=None)
        with self.assertRaisesRegex(Exception, "剩余次数"):
            arena_remaining(device)
        self.assertEqual(["arena_remaining_missing"], device.shots)
        self.assertEqual(0, device.backs)


if __name__ == "__main__":
    unittest.main()
