"""
推图选难度（2026-10-21 用户需求）：普通 / 困难二选一，11.0 之后可以开英雄难度推。
界面实录（1280x768）：地图右下角「英雄难度」「普通」「困难」，选中的难度按钮是实心蓝 / 红；
英雄难度窗口底部「开启中 / 未开启」+ 拨动开关；英雄难度的关卡面板没有「特殊奖励」。
只测流程，不依赖 ok 框架：把 ClearMapTask 里相关的函数和方法单独抠出来跑。
"""

import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np

source = Path(__file__).resolve().parents[1] / "src/tasks/ClearMapTask.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ClearMapTask")
wanted = ("read_difficulty", "ensure_difficulty", "ensure_hero", "panel_status", "on_chapter_select")
methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
funcs = [
    n
    for n in tree.body
    if isinstance(n, ast.FunctionDef)
    and n.name in ("difficulty_fill", "selected_difficulty", "chapter_number", "classify_panel")
]
consts = [
    n
    for n in tree.body
    if isinstance(n, ast.Assign)
    and any(
        isinstance(t, ast.Name)
        and t.id
        in (
            "DIFFICULTIES",
            "difficulty_re",
            "DIFFICULTY_FILL",
            "DIFFICULTY_MIN_FILL",
            "HERO_FROM_CHAPTER",
            "hero_button_re",
            "hero_state_re",
            "HERO_SWITCH_DX",
            "HERO_STATE_BOX",
            "chapter_no_re",
            "chapter_select_words",
            "chapter_select_marks_re",
            "LOCKED_WORDS",
        )
        for t in n.targets
    )
]
ns = {"re": re, "cv2": cv2, "nav_tabs_re": re.compile(r"剧情战役|往期活动|补给作战|模拟作战|Supply\s*Missions")}
exec(compile(ast.Module(body=consts + funcs + methods, type_ignores=[]), str(source), "exec"), ns)
W, H = 1280, 768
BLUE, RED, WHITE, GREY = (140, 110, 38), (40, 50, 170), (235, 235, 235), (150, 150, 150)  # BGR


def box(name, x, y, w=36, h=18):
    return SimpleNamespace(name=name, x=x, y=y, width=w, height=h)


def paint(frame, b, color):
    """把按钮文字框周围画成实心按钮的颜色。"""
    cx, cy = b.x + b.width // 2, b.y + b.height // 2
    frame[cy - 15 : cy + 15, cx - 56 : cx + 56] = color


def map_frame(normal, hard):
    frame = np.full((H, W, 3), 245, np.uint8)
    n, h = box("普通", 1064, 723), box("困难", 1198, 723)
    paint(frame, n, normal)
    paint(frame, h, hard)
    return frame, [n, h]


class SelectedDifficultyTest(unittest.TestCase):
    def test_filled_button_is_selected(self):
        frame, boxes = map_frame(BLUE, GREY)
        self.assertEqual(ns["selected_difficulty"](frame, boxes, H), "普通")
        frame, boxes = map_frame(WHITE, RED)
        self.assertEqual(ns["selected_difficulty"](frame, boxes, H), "困难")

    def test_nothing_filled(self):
        frame, boxes = map_frame(WHITE, GREY)
        self.assertIsNone(ns["selected_difficulty"](frame, boxes, H))

    def test_other_text_ignored(self):
        frame = np.zeros((H, W, 3), np.uint8)
        b = box("普通战斗", 600, 400)
        paint(frame, b, BLUE)
        self.assertIsNone(ns["selected_difficulty"](frame, [b], H))


class ChapterNumberTest(unittest.TestCase):
    def test_titles(self):
        self.assertEqual(ns["chapter_number"]([box("/ 11.0 错位锚定·上篇", 560, 25)]), 11)
        self.assertEqual(ns["chapter_number"]([box("C- 11.0.", 560, 15)]), 11)
        self.assertEqual(ns["chapter_number"]([box("/4.0 逆序矩阵", 580, 25)]), 4)
        self.assertIsNone(ns["chapter_number"]([box("240/240", 1010, 25)]))


class FakeTask:
    """地图 / 章节选择页 / 英雄难度窗口的最小模拟。"""

    width, height = W, H

    def __init__(self, difficulty="普通", hard_unlocked=True, hero=False, chapter=11, hero_switch_works=True):
        self.page = "map"
        self.difficulty = difficulty
        self.select_difficulty = difficulty
        self.hard_unlocked = hard_unlocked
        self.hero = hero
        self.chapter = chapter
        self.hero_switch_works = hero_switch_works
        self.log = []
        self.clicks = []
        self.backs = 0
        self.frame = None
        self.config = {}
        for name in wanted:
            setattr(self, name, ns[name].__get__(self))
        self.next_frame()

    # ---- 画面
    def next_frame(self):
        if self.page == "map":
            normal, hard = (BLUE, GREY) if self.difficulty == "普通" else (WHITE, RED)
        elif self.page == "select":
            normal, hard = (BLUE, (20, 20, 20)) if self.select_difficulty == "普通" else ((20, 20, 20), RED)
        else:
            normal, hard = GREY, GREY
        self.frame, self.diff_boxes = map_frame(normal, hard)

    def ocr(self, box=None, match=None, log=False, **kw):
        if match is ns["difficulty_re"]:
            return list(self.diff_boxes) if self.page in ("map", "select") else []
        if match is ns["hero_state_re"]:
            return [box_("开启中" if self.hero else "未开启", 950, 590)] if self.page == "hero" else []
        if box == "top":
            return [box_(f"/ {self.chapter}.0 某章", 560, 25)] if self.page == "map" else []
        return []

    def wait_ocr(self, box=None, match=None, time_out=0, raise_if_not_found=False, **kw):
        if match is ns["hero_button_re"]:
            return [box_("英雄难度", 900, 723)] if self.page == "map" and self.chapter >= 11 else []
        return self.ocr(box=box, match=match)

    def click(self, target, after_sleep=0):
        name = target[0].name
        self.clicks.append(name)
        if name == "英雄难度":
            self.page = "hero"
        elif name in ("普通", "困难"):
            if self.page == "map" and (name == "普通" or self.hard_unlocked):
                self.difficulty = name
            elif self.page == "select":
                self.select_difficulty = name

    def click_relative(self, x, y, after_sleep=0):
        self.clicks.append(("switch", round(x, 3)))
        if self.page == "hero" and self.hero_switch_works:
            self.hero = not self.hero

    def back(self, after_sleep=0):
        self.backs += 1
        self.page = "map" if self.page == "hero" else "select"

    def open_chapter_select(self):
        self.page = "select"
        return True

    def reenter_from_chapter_select(self):
        self.page = "map"
        self.difficulty = self.select_difficulty
        self.chapter = 4  # 困难只推到了 4.0
        return True

    def ensure_map(self):
        return [object()]

    def log_info(self, msg, notify=False):
        self.log.append(msg)

    def sleep(self, *a):
        pass

    def box_of_screen(self, x, y, to_x, to_y):
        return ("box", x, y, to_x, to_y)

    def debug_shot(self, *a, **kw):
        pass

    def find_boxes(self, boxes, match=None, boundary=None):
        return [b for b in boxes if any(re.search(m, b.name) for m in match)]

    def fix_match_regex(self, words):
        return words


box_ = box


class OnChapterSelectTest(unittest.TestCase):
    def check(self, texts):
        t = FakeTask()

        def ocr(box=None, match=None, **kw):
            pats = match if isinstance(match, list) else [match]
            return [box_(n, 0, 0) for n in texts if any(re.search(m, n) for m in pats)]

        t.ocr = ocr
        return t.on_chapter_select()

    def test_progress_text(self):
        self.assertTrue(self.check(["章节进度", "100%"]))

    def test_progress_hidden_by_art(self):
        # 实录 8.7 章：「章节进度」叠在立绘上读不出，顶上页签和右下「普通 / 困难」都在
        self.assertTrue(self.check(["剧情战役", "往期活动", "100%", "普通", "困难", "确认"]))

    def test_progress_glued_to_percent(self):
        # 实录 14.0 章：「章节进度1100%」连成一个框
        self.assertTrue(self.check(["章节进度1100%", "33/33"]))

    def test_no_difficulty_toggle_but_bottom_left_entries(self):
        # 实录 14.0 章：没有困难模式，章节选择页没有「普通 / 困难」切换
        self.assertTrue(self.check(["剧情战役", "往期活动", "猎人评定", "同调演练", "确认"]))

    def test_other_tab_is_not_chapter_select(self):
        self.assertFalse(self.check(["剧情战役", "模拟作战", "确认"]))

    def test_map_is_not_chapter_select(self):
        self.assertFalse(self.check(["LZ-1-6", "普通", "困难", "英雄难度"]))


class EnsureDifficultyTest(unittest.TestCase):
    def test_already_right(self):
        t = FakeTask("普通")
        t.ensure_difficulty("普通")
        self.assertEqual(t.clicks, [])

    def test_switch_on_map(self):
        t = FakeTask("普通", hard_unlocked=True)
        t.ensure_difficulty("困难")
        self.assertEqual((t.page, t.difficulty), ("map", "困难"))
        self.assertEqual(t.clicks, ["困难"])

    def test_hard_locked_falls_back_to_chapter_select(self):
        # 实录：17.0 章地图上「困难」灰的带锁，章节选择页切到困难后选中的是困难 4.0
        t = FakeTask("普通", hard_unlocked=False)
        t.ensure_difficulty("困难")
        self.assertEqual((t.page, t.difficulty, t.chapter), ("map", "困难", 4))
        self.assertEqual(t.clicks, ["困难", "困难"])

    def test_no_buttons_means_normal_only(self):
        # 实录 14.0 章：地图右下只有「英雄难度」，没有「普通 / 困难」，推普通就原地继续
        t = FakeTask("普通")
        t.page = "normal_only"
        t.ensure_difficulty("普通")
        self.assertEqual((t.page, t.clicks), ("normal_only", []))

    def test_no_buttons_and_want_hard_goes_to_chapter_select(self):
        t = FakeTask("普通")
        t.page = "normal_only"
        t.ensure_difficulty("困难")
        self.assertEqual((t.page, t.difficulty), ("map", "困难"))

    def test_back_to_normal(self):
        t = FakeTask("困难")
        t.ensure_difficulty("普通")
        self.assertEqual(t.difficulty, "普通")


class EnsureHeroTest(unittest.TestCase):
    def test_turn_on(self):
        t = FakeTask(hero=False)
        self.assertTrue(t.ensure_hero(True))
        self.assertTrue(t.hero)
        self.assertEqual(t.page, "map")
        # 拨动开关在「未开启」文字中心右边
        self.assertGreater(t.clicks[1][1], (950 + 18) / W)

    def test_turn_off_when_disabled(self):
        t = FakeTask(hero=True)
        self.assertFalse(t.ensure_hero(False))
        self.assertFalse(t.hero)

    def test_already_on_only_closes_dialog(self):
        t = FakeTask(hero=True)
        self.assertTrue(t.ensure_hero(True))
        self.assertEqual(t.clicks, ["英雄难度"])
        self.assertEqual((t.page, t.backs), ("map", 1))

    def test_no_button_before_chapter_11(self):
        t = FakeTask(chapter=4)
        self.assertFalse(t.ensure_hero(True))
        self.assertEqual(t.clicks, [])
        self.assertEqual(t.backs, 0)  # 地图上没窗口时按 ESC 会退到章节选择页

    def test_missing_button_on_hero_chapter_raises(self):
        t = FakeTask(chapter=12)
        t.wait_ocr = lambda **kw: []
        with self.assertRaises(Exception):
            t.ensure_hero(True)

    def test_state_missed_once_after_switch(self):
        # 实录 12.0 章：拨完开关后那一次没读到状态文字，再读就是「开启中」
        t = FakeTask(hero=False)
        real = t.ocr
        misses = iter([True])

        def flaky(box=None, match=None, **kw):
            if match is ns["hero_state_re"] and t.hero and next(misses, False):
                return []
            return real(box=box, match=match)

        t.ocr = flaky
        self.assertTrue(t.ensure_hero(True))

    def test_state_text_with_icon_noise(self):
        self.assertTrue(ns["hero_state_re"].search("开启中√"))
        self.assertFalse(ns["hero_state_re"].search("英雄难度"))

    def test_switch_not_working_raises(self):
        t = FakeTask(hero=False, hero_switch_works=False)
        with self.assertRaises(Exception):
            t.ensure_hero(True)


class HeroPanelTest(unittest.TestCase):
    def panel(self, hero):
        t = FakeTask()
        t.hero_mode = hero
        # 实录：LZ-1-6 英雄难度面板只有挑战目标、敌方单位和「挑战」，没有「特殊奖励」
        return t.panel_status([box("挑战目标", 1000, 190), box("敌方单位", 1000, 295), box("挑战", 1100, 715)])

    def test_hero_panel_without_reward_is_played(self):
        self.assertEqual(self.panel(True)[0], "challenge")

    def test_normal_panel_without_reward_is_cleared(self):
        self.assertEqual(self.panel(False)[0], "cleared")


if __name__ == "__main__":
    unittest.main()
