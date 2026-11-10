"""使用真实框匹配器重放烹饪剧情 OCR，不发送游戏输入。"""

import ast
import re
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from ok import BaseTask, Box

source = Path(__file__).resolve().parents[1] / "src/core/BaseGfTask.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "skip_dialogs")
namespace = {"re": re, "time": time, "pop_ups": ["点击空白处关闭"]}
exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace)


class DialogScreen:
    """仅替换截图、时钟和输入边界，剧情循环与框匹配均使用生产实现。"""

    skip_dialogs = namespace["skip_dialogs"]
    find_boxes = BaseTask.find_boxes

    def __init__(self, label="日跳过", dropped=0, blocked=False):
        self.now = 0
        self.label = label
        self.dropped = dropped
        self.blocked = blocked
        self.finished = False
        self.clicks = []
        self.blind_clicks = []

    def ocr(self):
        """文字与坐标来自 2026-11-10 的 3840×2160 故障截图重放。"""
        if self.finished:
            return [Box(2900, 1900, 300, 70, name="前往战役")]
        return [
            Box(3256, 56, 216, 67, name="自动"),
            Box(3532, 56, 220, 67, name=self.label),
            Box(2700, 1406, 344, 67, name="！来得很及时"),
            Box(2644, 1552, 368, 68, name="！分量十足。"),
            Box(1844, 1751, 144, 75, name="琼玖"),
        ]

    def click(self, boxes, after_sleep=0):
        """模拟点中可见按钮后推进页面，并可丢失输入。"""
        self.clicks.extend(box.name for box in boxes)
        if self.dropped:
            self.dropped -= 1
        elif not self.blocked:
            self.finished = True
        self.sleep(after_sleep)

    def click_relative(self, x, y):
        self.blind_clicks.append((x, y))

    def info_set(self, *args):
        pass

    def sleep(self, seconds):
        self.now += seconds

    def next_frame(self):
        self.now += 0.1

    def run(self):
        with patch.object(time, "time", lambda: self.now):
            return self.skip_dialogs(end_match=["前往战役"], time_out=8, has_dialog=False, raise_if_not_found=False)


class SkipDialogsTest(unittest.TestCase):
    def test_cooking_icon_prefix_reaches_result(self):
        """OCR 将图标合并为日/口时仍能跳过并识别真实结束页。"""
        for label in ("日跳过", "口跳过", "跳过", " 跳 过 "):
            with self.subTest(label=label):
                task = DialogScreen(label)
                result = task.run()
                self.assertEqual(["前往战役"], [box.name for box in result or []])
                self.assertEqual([label], task.clicks)
                self.assertEqual([], task.blind_clicks)

    def test_dropped_skip_is_retried(self):
        """首次跳过输入丢失后仍在同页，下次识别应重试可见按钮。"""
        task = DialogScreen(dropped=1)
        self.assertTrue(task.run())
        self.assertEqual(["日跳过", "日跳过"], task.clicks)

    def test_unresponsive_skip_is_bounded(self):
        """按钮始终无响应时有界超时，不误报结果页。"""
        task = DialogScreen(blocked=True)
        self.assertIsNone(task.run())
        self.assertEqual(4, len(task.clicks))
        self.assertEqual([], task.blind_clicks)

    def test_dialogue_text_is_not_a_skip_button(self):
        """含跳过字样的普通对话不应被当作按钮或触发盲点。"""
        for label in ("是否跳过剧情？", "不要跳过", "跳过后不可返回", "日常跳过"):
            with self.subTest(label=label):
                task = DialogScreen(label)
                self.assertIsNone(task.run())
                self.assertEqual([], task.clicks)
                self.assertEqual([], task.blind_clicks)


if __name__ == "__main__":
    unittest.main()
