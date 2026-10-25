"""
第 9 章起的「支援单位」（实录 2026-10-20）：推图卡在 BH-9-1 部署界面，可露凯的引导要先按提示点红框支援点、
推进对话、点「部署支援单位」；之后每关都要把「支援 n/m」上满再点作战开始。
纯函数用缩小的实机截图测；流程把 BaseGfTask 里的方法抠出来跑在 Mock 上。
"""

import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2

from src.core import support_select as ss

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests/fixtures"


def box(name, x=0, y=0, w=10, h=10):
    b = SimpleNamespace(name=name, x=x, y=y, width=w, height=h)
    b.center = lambda: (x + w / 2, y + h / 2)
    return b


class ParseTest(unittest.TestCase):
    def test_support_count(self):
        self.assertEqual(ss.parse_support_count(["支援", "2/3"]), (2, 3))
        self.assertEqual(ss.parse_support_count(["支援", "0/3"]), (0, 3))
        self.assertEqual(ss.parse_support_count(["支 援", "213"]), (2, 3))
        self.assertIsNone(ss.parse_support_count(["人形", "4/4"]))  # 没有支援行
        self.assertIsNone(ss.parse_support_count([]))
        # 实录：第 2、3 波「0/3」被敌人名字/血条挡住
        self.assertEqual(ss.parse_support_count(["支援", "灼光巨人"]), (None, None))
        self.assertEqual(ss.parse_support_count(["支援", "3"]), (None, None))
        self.assertEqual(ss.parse_support_count(["支援箱", "锤岩蟾蜍·冷凝", "1/3", "10"]), (1, 3))

    def test_tutorial_step(self):
        self.assertEqual(ss.tutorial_step(["可露凯", "点击地格上的支援单位部署点。"]), "tile")
        self.assertEqual(
            ss.tutorial_step(["可露凯", "……最后的提示，这次战斗，部署防御工事为好。", "点击部署支援单位。"]), "button"
        )
        self.assertEqual(
            ss.tutorial_step(["可露凯", "但还是提醒一下，每个关卡的支援单位种类、最大上阵数量都可能发生变化。"]),
            "advance",
        )
        # 实录 2026-10-20 第二次进 BH-9-1 的开场白：提到「部署支援单位」但不是让你点按钮
        self.assertEqual(
            ss.tutorial_step(["可露凯", "支援", "在特定关卡内，战前部署支援单位可以让作战效率大幅提", "高。"]),
            "advance",
        )
        self.assertEqual(
            ss.tutorial_step(
                ["可露凯", "支援箱", "最后的提示，这次战斗，部署防御工事为好。", "点击部署支援单位", "冠眼"]
            ),
            "button",
        )
        self.assertEqual(
            ss.tutorial_step(
                ["可露凯", "右侧是支援单位列表。基于战场和战术，选择部署适合的", "支援单位……这些想必不用我多说。"]
            ),
            "advance",
        )
        self.assertIsNone(ss.tutorial_step(["支援", "2/3"]))  # 计数行不是引导
        self.assertIsNone(ss.tutorial_step(["全部歼灭", "在本次作战中取得胜利"]))
        self.assertIsNone(ss.tutorial_step([]))

    def test_support_card_points_sorted_and_offsets(self):
        w, h = 1280, 720
        boxes = [
            box("Lv.20", 1120, 265, 40, 14),
            box("Lv.20", 1020, 152, 40, 14),
            box("Lv.20", 1110, 152, 40, 14),
            box("3207", 1020, 300),
        ]
        cards = ss.support_card_points(boxes, w, h)
        self.assertEqual([c["lv"] for c in cards], ["Lv.20"] * 3)
        self.assertEqual([c["center"][0] for c in cards], [1040, 1130, 1140])  # 先上一行（左到右），再下一行
        self.assertEqual(cards[0]["center"], (1040, int(159 + ss.SUPPORT_CARD_DY * h)))
        self.assertEqual(cards[0]["check"], (int(1040 + ss.SUPPORT_CHECK_DX * w), int(159 + ss.SUPPORT_CHECK_DY * h)))


class FixtureTest(unittest.TestCase):
    def test_tutorial_tile_found_only_when_framed(self):
        frame = cv2.imread(str(FIX / "support_tutorial_tile_1280x720.jpg"))
        xy = ss.find_tutorial_tile(frame, 1280, 720)
        self.assertIsNotNone(xy)
        self.assertLess(abs(xy[0] - 640), 20)  # 红框地格中心约 (640, 390)，地格本身 92x64 大
        self.assertLess(abs(xy[1] - 390), 20)
        frame2 = cv2.imread(str(FIX / "support_tab_deployed_1280x720.jpg"))
        self.assertIsNone(ss.find_tutorial_tile(frame2, 1280, 720))

    def test_deployed_support_card_has_orange_check(self):
        frame = cv2.imread(str(FIX / "support_tab_deployed_1280x720.jpg"))
        # 面板第一行三张卡的「Lv.20」标签中心（实测），第一张已部署（1/3）
        cards = ss.support_card_points(
            [box("Lv.20", 1012, 150, 40, 14), box("Lv.20", 1105, 150, 40, 14), box("Lv.20", 1197, 150, 40, 14)],
            1280,
            720,
        )
        flags = [ss.is_orange_check(frame, *c["check"]) for c in cards]
        self.assertEqual(flags, [True, False, False])

    def test_round_icon_support_point_found_as_fallback(self):
        # 实录 9-7：亮蓝色圆形图标的支援点，菱形模板认不出，靠宽松连通域兜底
        frame = cv2.imread(str(FIX / "support_round_icon_1280x720.jpg"))
        pts = ss.support_point_candidates(frame, 1280, 720)
        self.assertTrue(any(abs(x - 877) < 30 and abs(y - 546) < 30 for x, y in pts), pts)

    def test_support_tiles_found_in_support_tab(self):
        frame = cv2.imread(str(FIX / "support_tab_deployed_1280x720.jpg"))
        tiles = ss.find_deploy_tiles(frame, 1280, 720)
        self.assertGreaterEqual(len(tiles), 4)  # 六个支援点，被工事挡住的那个可能认不出


# ---- 流程：抠出 BaseGfTask 里的方法跑在 Mock 上 ----
source = ROOT / "src/core/BaseGfTask.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BaseGfTask")
wanted = (
    "_support_count",
    "_support_button",
    "_click_support_tab",
    "_ensure_unit_tab",
    "_support_cards",
    "_support_card_placed",
    "_click_support_card",
    "_follow_support_tutorial",
    "deploy_supports",
)
methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
ns = {
    "re": re,
    "SUPPORT_COUNT_BOX": ss.SUPPORT_COUNT_BOX,
    "SUPPORT_TAB_BOX": ss.SUPPORT_TAB_BOX,
    "SUPPORT_TAB_XY": ss.SUPPORT_TAB_XY,
    "TUTORIAL_BOX": ss.TUTORIAL_BOX,
    "BUTTON_BOX": ss.BUTTON_BOX,
    "PANEL_BOX": ss.PANEL_BOX,
    "TAB_BOX": ss.TAB_BOX,
    "support_lv_re": ss.support_lv_re,
    "parse_support_count": ss.parse_support_count,
    "tutorial_step": ss.tutorial_step,
    "support_card_points": ss.support_card_points,
    "find_tutorial_tile": lambda frame, w, h: frame.get("tutorial_tile") if isinstance(frame, dict) else None,
    "is_orange_check": lambda frame, x, y: (x, y) in frame.get("checks", ()),
    "find_deploy_tiles": lambda frame, w, h: [{"center": c, "fill": 0.9} for c in frame.get("tiles", ())],
    "support_point_candidates": lambda frame, w, h: list(frame.get("tiles", ())),
}
exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), ns)


class FakeTask:
    """按区域返回 OCR 文字的假任务：screens 是一串「每帧的区域文字表」，next_frame 翻到下一帧（最后一帧停住）。"""

    width, height = 1280, 720

    def __init__(self, screens):
        self.screens = screens
        self.i = 0
        self.calls = []
        self.box = SimpleNamespace(bottom="bottom")
        for name in wanted:
            setattr(self, name, ns[name].__get__(self))

    @property
    def frame(self):
        return self.screens[self.i]

    def next_frame(self):
        self.i = min(self.i + 1, len(self.screens) - 1)

    def _ocr_panel(self, region, match=None, **kw):
        texts = self.frame.get(region, [])
        boxes = [box(t) for t in texts]
        if match:
            match = match if isinstance(match, (list, tuple)) else [match]
            boxes = [b for b in boxes if any(re.search(m, b.name) for m in match)]
        return boxes

    def ocr(self, match=None, box=None, **kw):
        return [box_(t) for t in self.frame.get("bottom", []) if any(re.search(m, t) for m in match)]

    def fix_match_regex(self, patterns):
        return patterns

    def click(self, target, after_sleep=0):
        self.calls.append(("click", target[0].name if isinstance(target, list) else target.name))

    def click_relative(self, x, y, after_sleep=0):
        self.calls.append(("click_rel", round(x, 3), round(y, 3)))

    def log_info(self, *a, **k):
        pass

    def sleep(self, *a):
        pass

    def info_set(self, *a):
        pass

    def debug_shot(self, *a, **k):
        pass

    def _clear_selection(self):
        self.calls.append(("clear",))
        return True


box_ = box
T, B, P, C, S, TAB = ss.TUTORIAL_BOX, ss.BUTTON_BOX, ss.PANEL_BOX, ss.SUPPORT_COUNT_BOX, ss.SUPPORT_TAB_BOX, ss.TAB_BOX


class TutorialFlowTest(unittest.TestCase):
    def test_follows_tile_advance_button_then_stops(self):
        screens = [
            {T: ["可露凯", "点击地格上的支援单位部署点。"], "tutorial_tile": (640, 393)},
            {T: ["可露凯", "但还是提醒一下，每个关卡的支援单位种类、最大上阵数量都可能发生变化。"]},
            {T: ["可露凯", "……最后的提示，这次战斗，部署防御工事为好。", "点击部署支援单位。"], B: ["部署支援单位"]},
            {T: [], C: ["人形", "4/4"]},
        ]
        task = FakeTask(screens)
        self.assertTrue(task._follow_support_tutorial())
        self.assertEqual(
            task.calls,
            [
                ("click_rel", 0.5, 0.546),
                ("click", "但还是提醒一下，每个关卡的支援单位种类、最大上阵数量都可能发生变化。"),
                ("click", "部署支援单位"),
            ],
        )

    def test_no_tutorial_does_nothing(self):
        task = FakeTask([{T: ["支援", "2/3"]}])
        self.assertFalse(task._follow_support_tutorial())
        self.assertEqual(task.calls, [])

    def test_missing_red_frame_advances_dialog_instead(self):
        task = FakeTask([{T: ["可露凯", "点击地格上的支援单位部署点。"]}, {T: []}])
        self.assertTrue(task._follow_support_tutorial())
        self.assertEqual(task.calls, [("click", "点击地格上的支援单位部署点。")])


class FakeGame(FakeTask):
    """按状态回答的假部署界面：地格有人/没人、卡片有没有部署、计数会随「部署支援单位」涨。"""

    def __init__(self, count, tiles, cards_deployed, tab="部署人形"):
        super().__init__([{}])
        self.count = count  # [n, m]
        self.tiles = dict(tiles)  # (x, y) -> 是否已有单位
        self.cards_deployed = list(cards_deployed)
        self.tab = tab
        self.selected_tile = None
        self.selected_card = None
        self.hide_count = False  # 计数被敌人名字挡住（OCR 读不到数字）

    @property
    def frame(self):
        checks = set()
        for i, deployed in enumerate(self.cards_deployed):
            if deployed:
                checks.add(
                    (int(10 + i * 100 + ss.SUPPORT_CHECK_DX * 1280), int(10 + ss.SUPPORT_CHECK_DY * 720))
                )  # Lv 标签框中心 (10+100i, 10)
        return {"checks": checks, "tiles": list(self.tiles)}

    def next_frame(self):
        pass

    def _ocr_panel(self, region, match=None, **kw):
        texts = []
        if region == C:
            if self.count is None:
                texts = ["人形", "4/4"]
            elif self.hide_count:
                texts = ["支援", "灼光巨人"]
            else:
                texts = ["支援", f"{self.count[0]}/{self.count[1]}"]
        elif region == S:
            texts = ["部署人形", "部署支援"]
        elif region == TAB:
            texts = ["可部署支援单位"] if self.tab == "部署支援" else ["我的人形", "好友助战"]
        elif region == P and self.tab == "部署支援":
            texts = ["Lv.20"] * len(self.cards_deployed)
        elif region == B:
            if self.selected_tile is not None and self.tiles[self.selected_tile]:
                texts = ["撤回支援单位"]
            elif self.selected_tile is not None and self.selected_card is not None:
                texts = ["部署支援单位"]
            else:
                texts = ["请点击地格或拖拽以部署单位"]
        boxes = []
        for i, t in enumerate(texts):
            boxes.append(box(t, 5 + i * 100, 5, 10, 10))  # 第 i 张卡的 Lv 标签在 x=5+100i
        if match:
            match = match if isinstance(match, (list, tuple)) else [match]
            boxes = [b for b in boxes if any(re.search(m, b.name) for m in match)]
        return boxes

    def click(self, target, after_sleep=0):
        name = target[0].name if isinstance(target, list) else target.name
        self.calls.append(("click", name))
        if name in ("部署人形", "部署支援"):
            self.tab = name
            self.selected_card = self.selected_tile = None
        elif name == "部署支援单位" and self.selected_tile is not None and self.selected_card is not None:
            self.tiles[self.selected_tile] = True
            self.cards_deployed[self.selected_card] = True
            self.count[0] += 1

    def click_relative(self, x, y, after_sleep=0):
        self.calls.append(("click_rel", round(x, 3), round(y, 3)))
        px, py = x * 1280, y * 720
        for i in range(len(self.cards_deployed)):
            cx = 10 + i * 100
            if abs(px - cx) < 30 and abs(py - (10 + ss.SUPPORT_CARD_DY * 720)) < 30 and self.tab == "部署支援":
                self.selected_card = i
                return
        for t in self.tiles:
            if abs(px - t[0]) < 5 and abs(py - t[1]) < 5:
                self.selected_tile = t
                return

    def _clear_selection(self):
        self.calls.append(("clear",))
        self.selected_tile = None
        return True


class DeploySupportsTest(unittest.TestCase):
    def test_stage_without_supports_is_skipped(self):
        game = FakeGame(None, {}, [])
        self.assertFalse(game.deploy_supports())
        self.assertEqual(game.calls, [])

    def test_full_supports_are_left_alone(self):
        game = FakeGame([3, 3], {(300, 300): True}, [True, True, True])
        self.assertFalse(game.deploy_supports())
        self.assertEqual(game.calls, [])

    def test_deploys_on_free_point_after_skipping_occupied_one(self):
        game = FakeGame([2, 3], {(300, 300): True, (400, 340): False, (500, 380): False}, [True, True, False])
        self.assertTrue(game.deploy_supports())
        self.assertEqual(game.count, [3, 3])
        self.assertTrue(game.tiles[(400, 340)])
        self.assertFalse(game.tiles[(500, 380)])  # 满了就不再点别的格子
        self.assertEqual(game.calls[0], ("click", "部署支援"))
        self.assertEqual(game.calls[-1], ("click", "部署人形"))
        self.assertEqual(game.calls.count(("click", "部署支援单位")), 1)
        self.assertIn(("clear",), game.calls)  # 点到有人的格子后清掉选中

    def test_fills_two_missing_supports(self):
        game = FakeGame([1, 3], {(300, 300): True, (400, 340): False, (500, 380): False}, [True, False, False])
        self.assertTrue(game.deploy_supports())
        self.assertEqual(game.count, [3, 3])
        self.assertEqual(game.cards_deployed, [True, True, True])

    def test_hidden_count_still_deploys_until_cards_or_points_run_out(self):
        game = FakeGame([0, 3], {(300, 300): False, (400, 340): False, (500, 380): False}, [False, False, False, False])
        game.hide_count = True
        self.assertTrue(game.deploy_supports())
        self.assertEqual(game.count, [3, 3])  # 三个支援点都上了（计数读不到，靠卡片勾选确认）
        self.assertEqual(game.cards_deployed, [True, True, True, False])
        self.assertEqual(game.calls[-1], ("click", "部署人形"))

    def test_no_free_card_stops(self):
        game = FakeGame([1, 3], {(300, 300): True, (400, 340): False}, [True])
        self.assertFalse(game.deploy_supports())
        self.assertNotIn(("click", "部署支援单位"), game.calls)
        self.assertEqual(game.calls[-1], ("click", "部署人形"))

    def test_no_free_point_stops(self):
        game = FakeGame([1, 3], {(300, 300): True}, [True, False])
        self.assertFalse(game.deploy_supports())
        self.assertEqual(game.count, [1, 3])
        self.assertEqual(game.calls[-1], ("click", "部署人形"))

    def test_unit_tab_restored_when_left_on_support_tab(self):
        game = FakeGame([2, 3], {}, [], tab="部署支援")
        self.assertTrue(game._ensure_unit_tab())
        self.assertEqual(game.calls, [("click", "部署人形")])
        self.assertEqual(game.tab, "部署人形")
        self.assertFalse(game._ensure_unit_tab())


if __name__ == "__main__":
    unittest.main()
