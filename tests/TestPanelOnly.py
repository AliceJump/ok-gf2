"""
读关卡面板时去掉卡片自己写的未解锁提示（实录 2026-11-12 热寂悖论挑战模式，2560x1440）：
卡片上写着「需要完成前置关卡」（y=964），伸进右半屏的 DT-1-4 卡片混进了 DT-1-1 的面板文字，能打的关被判成未解锁；
面板里真正的未解锁提示在最底下按钮的位置（DT-1-2：(2078,1313)）。
"""

import ast
import re
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

source = Path(__file__).resolve().parents[1] / "src/tasks/ClearMapTask.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ClearMapTask")
nodes = [
    n
    for n in tree.body
    if (isinstance(n, ast.FunctionDef) and n.name == "panel_only")
    or (
        isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id in ("LOCKED_WORDS", "PANEL_WORDS", "BUTTON_MIN_Y") for t in n.targets)
    )
] + [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "read_panel"]
ns = {"re": re, "time": time}
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), ns)
H = 1440


def boxes(rows):
    return [SimpleNamespace(name=n, x=x, y=y) for n, x, y in rows]


# DT-1-1 面板打开时右半屏读到的 PANEL_WORDS（实机 OCR）
DT11_PANEL = [("特殊奖励", 1944, 895), ("需要完成前置关卡", 1594, 964), ("挑战", 2208, 1318)]
# DT-1-2（锁着）面板
DT12_PANEL = [("特殊奖励", 1944, 895), ("需要完成前置关卡", 1605, 964), ("需要完成前置关卡", 2078, 1313)]
# 面板还没弹出来，只看得到卡片
CARDS_ONLY = [("需要完成前置关卡", 1621, 964), ("需要完成前置关卡", 2080, 964)]


class PanelOnlyTest(unittest.TestCase):
    def test_card_hint_dropped_from_open_panel(self):
        self.assertEqual([b.name for b in ns["panel_only"](boxes(DT11_PANEL), H)], ["特殊奖励", "挑战"])

    def test_panel_hint_at_button_row_kept(self):
        kept = ns["panel_only"](boxes(DT12_PANEL), H)
        self.assertEqual([(b.name, b.y) for b in kept], [("特殊奖励", 895), ("需要完成前置关卡", 1313)])

    def test_cards_only_means_no_panel_yet(self):
        self.assertEqual(ns["panel_only"](boxes(CARDS_ONLY), H), [])


class ReadPanelTest(unittest.TestCase):
    def make_task(self, frames):
        task = Mock()
        task.height = H
        it = iter(frames)
        last = {"rows": []}

        def ocr(*a, **k):
            last["rows"] = next(it, last["rows"])
            return boxes(last["rows"])

        task.ocr.side_effect = ocr
        return task

    def test_waits_past_card_hints_until_panel_shows(self):
        """面板动画还没出来时只读到卡片上的字：继续等，不能当成面板说未解锁。"""
        task = self.make_task([CARDS_ONLY, CARDS_ONLY, DT11_PANEL])
        got = ns["read_panel"](task, time_out=3)
        self.assertEqual([b.name for b in got], ["特殊奖励", "挑战"])
        self.assertEqual(task.ocr.call_count, 3)

    def test_gives_up_after_time_out(self):
        task = self.make_task([CARDS_ONLY])
        self.assertEqual(ns["read_panel"](task, time_out=0), [])


if __name__ == "__main__":
    unittest.main()
