"""
推图持续推进（2026-10-20 用户需求：本章推完就进下一章继续打）。
章节选择页的 OCR 文本用实机记录（2560x1440）；纯函数从 ClearMapTask 源码抠出来跑，不依赖 ok 框架。
"""

import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

source = Path(__file__).resolve().parents[1] / "src/tasks/ClearMapTask.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
names = ("chapter_titles", "current_and_next_chapter", "chapter_signature", "chapter_display_name")
funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
consts = [
    n
    for n in tree.body
    if isinstance(n, ast.Assign)
    and any(
        (isinstance(t, ast.Name) and t.id.startswith("CHAPTER_"))
        or (isinstance(t, ast.Name) and t.id.startswith("chapter_"))
        for t in n.targets
    )
]
ns = {"re": re}
exec(compile(ast.Module(body=consts + funcs, type_ignores=[]), str(source), "exec"), ns)
current_and_next_chapter, chapter_signature = ns["current_and_next_chapter"], ns["chapter_signature"]
W, H = 2560, 1440


def boxes(rows):
    return [SimpleNamespace(name=n, x=x, y=y, width=120, height=40) for n, x, y in rows]


# 实录 17:59:15：9.0 远日点·上篇 是当前章，下面全是锁着的章节
SELECT = [
    ("剧情战役", 1387, 45),
    ("往期活动", 1680, 45),
    ("Supply Missions", 1968, 42),
    ("模拟作战", 2259, 42),
    ("0／9.0", 13, 191),
    ("远日点·上篇", 205, 183),
    ("远日点·下篇", 173, 304),
    ("C- 11.0.", 69, 421),
    ("错位锚定·上篇", 173, 418),
    ("C-12.0", 69, 531),
    ("错位锚定·下篇", 173, 537),
    ("交织突进", 173, 656),
    ("C-13.0", 69, 778),
    ("火花之罪·上篇心", 176, 778),
    ("C-14.", 69, 895),
    ("火花之罪·中篇", 171, 892),
    ("章节进度", 2059, 921),
    ("57%", 2221, 895),
    ("火花之罪·下篇", 169, 1006),
    ("27/48", 2339, 1016),
    ("废墟之下，火种在黑暗中发芽。", 2043, 1056),
    ("普通", 2085, 1228),
    ("猎人评定", 200, 1284),
    ("同调演练", 629, 1286),
    ("确认", 2219, 1318),
]


class ChapterSelectTest(unittest.TestCase):
    def test_current_and_next(self):
        cur, nxt = current_and_next_chapter(boxes(SELECT), W, H)
        self.assertEqual(cur.name, "远日点·上篇")
        self.assertEqual(nxt.name, "远日点·下篇")

    def test_badge_follows_selected_row(self):
        rows = [r for r in SELECT if r[0] != "0／9.0"] + [("10.0", 10, 300)]
        cur, nxt = current_and_next_chapter(boxes(rows), W, H)
        self.assertEqual(cur.name, "远日点·下篇")
        self.assertEqual(nxt.name, "错位锚定·上篇")

    def test_small_c_labels_are_not_the_badge(self):
        rows = [r for r in SELECT if r[0] != "0／9.0"]
        cur, _ = current_and_next_chapter(boxes(rows), W, H)
        self.assertEqual(cur.name, "远日点·上篇")  # 没角标时取最上面那个，不会被 C-12.0 带偏

    def test_last_chapter_has_no_next(self):
        rows = [("0／15.0", 13, 1000), ("火花之罪·下篇", 169, 1006), ("章节进度", 2059, 921)]
        cur, nxt = current_and_next_chapter(boxes(rows), W, H)
        self.assertEqual(cur.name, "火花之罪·下篇")
        self.assertIsNone(nxt)

    def test_locked_click_keeps_signature_even_if_tagline_ocr_differs(self):
        # 实录 17:59:47：点锁着的「远日点·下篇」后再读，简介少了句号，坐标也微动
        after = [r for r in SELECT if not r[0].startswith("废墟")] + [("废墟之下，火种在黑暗中发芽", 2048, 1061)]
        after = [("0/9.0", 19, 185) if r[0] == "0／9.0" else r for r in after]
        self.assertEqual(chapter_signature(boxes(SELECT), W, H), chapter_signature(boxes(after), W, H))

    def test_selecting_other_chapter_changes_signature(self):
        after = [
            ("100%", 2221, 895) if r[0] == "57%" else ("48/48", 2339, 1016) if r[0] == "27/48" else r for r in SELECT
        ]
        self.assertNotEqual(chapter_signature(boxes(SELECT), W, H), chapter_signature(boxes(after), W, H))


class DisplayNameTest(unittest.TestCase):
    def test_strip_badge_and_noise(self):
        f = ns["chapter_display_name"]
        self.assertEqual(f("010.0远日点·下篇Q"), "远日点·下篇")  # 实录 18:40 的 OCR
        self.assertEqual(f("火花之罪·上篇心"), "火花之罪·上篇心")
        self.assertEqual(f("交织突进"), "交织突进")


if __name__ == "__main__":
    unittest.main()
