# Test case
"""BaseGfTask 的 alt 点击支持测试。

不接 ok-script 运行时（BaseTask 需要 executor/app），用桩子类验证：
按键时序、alt_hold_delay 行为、click / wait_click_* 的 alt 分派、free_layer_click 复用。

两个桩分工不同：
- ``ClickStub`` 把 ``click`` 换成记录桩 → 用来测 ``click_with_alt`` 内部的时序；
- ``DispatchStub`` 保留真实的 ``click``、只把 ``click_with_alt`` 换成桩 → 用来测上层方法的 alt 分派。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ok import Box  # noqa: E402
from src.tasks.BaseGfTask import BaseGfTask  # noqa: E402


class BaseStub(BaseGfTask):
    """公共桩：不调用 super().__init__，避免依赖 executor/app。"""

    def __init__(self, ocr_result=None, feature_box=None):
        self.calls = []
        self._ocr_result = ocr_result
        self._feature_box = feature_box

    @property
    def frame(self):
        return None

    @property
    def debug(self):
        return False

    def send_key_down(self, key, after_sleep=0):
        self.calls.append(("key_down", key))

    def send_key_up(self, key, after_sleep=0):
        self.calls.append(("key_up", key))

    def sleep(self, seconds):
        self.calls.append(("sleep", seconds))

    def screenshot(self, name=None, **kwargs):
        self.calls.append(("screenshot", name))

    def click_box(self, *args, **kwargs):
        # 非 alt 路径最终会走到这里；换成记录桩以免触碰需要 executor 的真实点击
        self.calls.append(("click_box", args, kwargs))
        return True

    def wait_ocr(self, *args, **kwargs):
        self.calls.append(("wait_ocr",))
        return self._ocr_result

    def ocr(self, *args, **kwargs):
        return self._ocr_result

    def wait_until(self, condition, **kwargs):
        return self._feature_box

    def find_one(self, *args, **kwargs):
        return self._feature_box

    def kinds(self):
        return [c[0] for c in self.calls]


class ClickStub(BaseStub):
    """替换 click，用于观察 click_with_alt 的按键时序。"""

    def click(self, *args, **kwargs):
        self.calls.append(("click", args, kwargs))
        return True


class DispatchStub(BaseStub):
    """保留真实 click，只替换 click_with_alt，用于验证 alt 分派。"""

    def click_with_alt(self, *args, **kwargs):
        self.calls.append(("click_with_alt", args, kwargs))
        return "alt"


class TestClickWithAlt(unittest.TestCase):
    def test_key_sequence(self):
        """按下 alt → 等待 → 点击 → 松开 alt。"""
        task = ClickStub()
        task.click_with_alt(0.5, 0.6, alt_hold_delay=0.5)

        self.assertEqual(task.kinds(), ["key_down", "sleep", "click", "key_up"])
        self.assertEqual(task.calls[0], ("key_down", "alt"))
        self.assertEqual(task.calls[1], ("sleep", 0.5))
        self.assertEqual(task.calls[2][1], (0.5, 0.6))
        self.assertEqual(task.calls[3], ("key_up", "alt"))

    def test_zero_hold_delay_skips_sleep(self):
        """alt_hold_delay=0 时不插入额外等待。"""
        task = ClickStub()
        task.click_with_alt(0.5, 0.6, alt_hold_delay=0)
        self.assertEqual(task.kinds(), ["key_down", "click", "key_up"])

    def test_alt_is_released_on_click_error(self):
        """点击抛异常时也必须松开 alt，否则后续按键会一直被 alt 污染。"""

        class BoomStub(ClickStub):
            def click(self, *args, **kwargs):
                self.calls.append(("click", args, kwargs))
                raise RuntimeError("boom")

        task = BoomStub()
        with self.assertRaises(RuntimeError):
            task.click_with_alt(0.1, 0.2, alt_hold_delay=0)
        self.assertEqual(task.kinds(), ["key_down", "click", "key_up"])


class TestAltDispatch(unittest.TestCase):
    def test_click_alt_flag_dispatches_to_click_with_alt(self):
        task = DispatchStub()
        task.click(0.1, 0.2, alt=True)
        self.assertEqual(task.kinds(), ["click_with_alt"])

    def test_wait_click_ocr_alt_dispatches(self):
        box = Box(10, 10, 100, 20, name="登录")
        task = DispatchStub(ocr_result=[box])
        result = task.wait_click_ocr(match="登录", alt=True)

        self.assertEqual(task.kinds(), ["wait_ocr", "click_with_alt"])
        self.assertEqual(result, [box])

    def test_wait_click_ocr_without_alt_does_not_use_alt_click(self):
        box = Box(10, 10, 100, 20, name="登录")
        task = DispatchStub(ocr_result=[box])
        task.wait_click_ocr(match="登录")
        self.assertNotIn("click_with_alt", task.kinds())

    def test_wait_click_feature_alt_dispatches(self):
        box = Box(10, 10, 100, 20, name="start")
        task = DispatchStub(feature_box=box)
        self.assertTrue(task.wait_click_feature("start_button", alt=True))
        self.assertEqual(task.kinds(), ["click_with_alt"])

    def test_wait_click_feature_alt_miss_returns_false(self):
        task = DispatchStub(feature_box=None)
        self.assertFalse(task.wait_click_feature("start_button", alt=True))
        self.assertEqual(task.kinds(), [])


class TestFreeLayerClick(unittest.TestCase):
    def test_reuses_click_with_alt_without_extra_delay(self):
        """free_layer_click 复用 click_with_alt，且保持原有「不加额外等待」的时序。"""
        task = DispatchStub()
        task.free_layer_click(0.3, 0.4)

        self.assertEqual(task.kinds(), ["click_with_alt"])
        _name, args, kwargs = task.calls[0]
        self.assertEqual(args[:2], (0.3, 0.4))
        self.assertEqual(kwargs.get("alt_hold_delay"), 0)
        self.assertEqual(kwargs.get("debug_name"), "free_layer_click")


if __name__ == '__main__':
    unittest.main()
