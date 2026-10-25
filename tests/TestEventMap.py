"""
往期活动推图（2026-10-22 用户需求）：活动列表的纯函数，OCR 文本用实机记录（2560x1440）。
纯函数从 EventMapTask 源码抠出来跑，不依赖 ok 框架。
"""

import ast
import re
import unittest
from difflib import SequenceMatcher
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

source = Path(__file__).resolve().parents[1] / "src/tasks/EventMapTask.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
nodes = [
    n
    for n in tree.body
    if (isinstance(n, ast.FunctionDef))
    or (isinstance(n, ast.Assign) and all(isinstance(t, ast.Name) and (t.id.isupper() or t.id.endswith("_re")) for t in n.targets))
]
ns = {"re": re, "SequenceMatcher": SequenceMatcher}
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), ns)
event_cards, pick_event, same_event, event_title_on_map = (
    ns["event_cards"],
    ns["pick_event"],
    ns["same_event"],
    ns["event_title_on_map"],
)
W, H = 2560, 1440


def boxes(rows):
    return [SimpleNamespace(name=n, x=x, y=y, width=150, height=40) for n, x, y in rows]


# 实录 2026-10-22 01:50：往期活动 → 活动剧情 列表最左边
LIST = [
    ("剧情战役", 1389, 45),
    ("往期活动", 1680, 45),
    ("Supply Missions", 1968, 42),
    ("模拟作战", 2261, 45),
    ("活动剧情", 69, 193),
    ("悖论操演", 67, 323),
    ("03", 1605, 304),
    ("模拟习练", 67, 458),
    ("狂想四重奏", 667, 1083),
    ("拂晓的回响", 1205, 1081),
    ("密米尔的返演·上篇", 1691, 1085),
    ("密米尔的返演·下篇", 2235, 1088),
    ("完成度0%", 691, 1141),
    ("完成度0%", 1235, 1141),
    ("完成度0%", 1779, 1141),
    ("完成度0%", 2323, 1141),
]


class EventListTest(unittest.TestCase):
    def test_pairs_title_with_percent(self):
        cards = event_cards(boxes(LIST), W, H)
        self.assertEqual(
            [(t.name, p) for t, p in cards],
            [("狂想四重奏", 0), ("拂晓的回响", 0), ("密米尔的返演·上篇", 0), ("密米尔的返演·下篇", 0)],
        )

    def test_left_menu_and_tabs_are_not_cards(self):
        names = [t.name for t, _ in event_cards(boxes(LIST), W, H)]
        self.assertNotIn("活动剧情", names)
        self.assertNotIn("往期活动", names)

    def test_pick_first_unfinished_skipping_done(self):
        rows = [("完成度100%", 691, 1141) if r == ("完成度0%", 691, 1141) else r for r in LIST]
        cards = event_cards(boxes(rows), W, H)
        self.assertEqual(pick_event(cards, [])[0].name, "拂晓的回响")
        self.assertEqual(pick_event(cards, ["拂晓的回晌"])[0].name, "密米尔的返演·上篇")
        self.assertIsNone(pick_event([(c[0], 100) for c in cards], []))

    def test_percent_with_spaces(self):
        cards = event_cards(boxes([("狂想四重奏", 667, 1083), ("完成度 57 %", 691, 1141)]), W, H)
        self.assertEqual(cards[0][1], 57)

    def test_same_event_tolerates_ocr_typo(self):
        self.assertTrue(same_event("狂想四重秦", "狂想四重奏"))  # 实录：地图顶上的活动名
        self.assertFalse(same_event("密米尔的返演·上篇", "狂想四重奏"))
        self.assertFalse(same_event("", "狂想四重奏"))

    def test_upper_and_lower_part_are_different_events(self):
        # 上篇 / 下篇只差一个字，相似度很高；必须挑没推过的那个
        cards = event_cards(boxes(LIST), W, H)
        hit = pick_event(cards, ["狂想四重奏", "拂晓的回响", "密米尔的返演·上篇"])
        self.assertEqual(hit[0].name, "密米尔的返演·下篇")

    def test_title_on_map(self):
        # 实录 01:51：活动地图顶上「狂想四重秦」（OCR 错字）+「活动剧情」
        rows = [("狂想四重秦", 1213, 42), ("活动剧情", 1192, 79), ("MA-1-1", 968, 683)]
        self.assertEqual(event_title_on_map(boxes(rows), W, H), "狂想四重秦")

    def test_title_split_into_two_boxes(self):
        # 实录 2026-10-22：「密米尔的返演·上篇」只读出前半截，上篇被拆到另一个框
        rows = [("·上篇", 1330, 45), ("密米尔的返演", 1170, 42), ("活动剧情", 1192, 79)]
        title = event_title_on_map(boxes(rows), W, H)
        self.assertEqual(title, "密米尔的返演·上篇")
        self.assertFalse(same_event(title, "密米尔的返演·下篇"))

    def test_decorative_line_above_title(self):
        # 实录 2026-10-22 08:56：「前进吧，王牌配送员！」上面还有一行装饰字「SAKURA」，只取最上一行会读成空
        rows = [("SAKURA", 1180, 4), ("前进吧，王牌配送员！", 1150, 48), ("活动剧情", 1192, 90)]
        self.assertEqual(event_title_on_map(boxes(rows), W, H), "前进吧，王牌配送员！")
        self.assertIsNone(event_title_on_map(boxes([("SAKURA", 1180, 4), ("活动剧情", 1192, 90)]), W, H))


try:
    import cv2
    import numpy as np
except ImportError:  # mac 开发机没装 cv2，这组只在 Windows 上跑
    cv2 = None


@unittest.skipIf(cv2 is None, "需要 cv2")
class EventTabTest(unittest.TestCase):
    """实录 2026-10-22 密米尔的返演·上篇：物资还锁着，点了不切；不能看关卡名变没变，要看哪个按钮是实心的。"""

    def setUp(self):
        clear = ast.parse((Path(__file__).resolve().parents[1] / "src/tasks/ClearMapTask.py").read_text(encoding="utf-8"))
        extra = [
            n
            for n in clear.body
            if (isinstance(n, ast.FunctionDef) and n.name == "difficulty_fill")
            or (
                isinstance(n, ast.Assign)
                and any(isinstance(x, ast.Name) and x.id in ("DIFFICULTY_FILL", "DIFFICULTY_MIN_FILL") for x in n.targets)
            )
        ]
        ns["cv2"] = cv2
        exec(compile(ast.Module(body=extra, type_ignores=[]), "ClearMapTask", "exec"), ns)

    def frame(self, filled, color=(0, 110, 240)):
        img = np.full((H, W, 3), 30, np.uint8)  # 暗底
        for x in (2128, 2379):
            img[1320:1395, x - 40 : x + 160] = (79, 79, 79)  # 没选中的灰按钮（实测 V≈79）
        x = 2128 if filled == "剧情" else 2379
        img[1320:1395, x - 40 : x + 160] = color  # 默认橙色实心按钮（BGR）
        return img

    def test_filled_button_is_selected(self):
        tabs = boxes([("剧情", 2128, 1339), ("物资", 2379, 1339)])
        for want in ("剧情", "物资"):
            self.assertEqual(ns["selected_event_tab"](self.frame(want), tabs, H), want)

    def test_muted_green_button_is_selected(self):
        """实录 2026-10-22 纪念日礼赞：选中的「剧情」是灰绿色（HSV S≈70 V≈174），S>90 认不出，被当成切不过去先推了物资。"""
        tabs = boxes([("剧情", 2128, 1339), ("物资", 2379, 1339)])
        muted = cv2.cvtColor(np.uint8([[[60, 70, 174]]]), cv2.COLOR_HSV2BGR)[0, 0].tolist()
        for want in ("剧情", "物资"):
            self.assertEqual(ns["selected_event_tab"](self.frame(want, muted), tabs, H), want)

    def test_bluish_gray_button_is_selected(self):
        """实录 2026-10-22 沉没夜潮：选中的「剧情」是蓝灰色（S≈26 V≈129），没颜色，只比没选中的（V≈79）亮。"""
        tabs = boxes([("剧情", 2128, 1339), ("物资", 2379, 1339)])
        for want in ("剧情", "物资"):
            self.assertEqual(ns["selected_event_tab"](self.frame(want, (129, 118, 110)), tabs, H), want)

    def test_single_tab_falls_back_to_fill(self):
        tab = boxes([("剧情", 2128, 1339)])
        self.assertEqual(ns["selected_event_tab"](self.frame("剧情"), tab, H), "剧情")
        self.assertIsNone(ns["selected_event_tab"](self.frame("物资"), tab, H))

    def test_no_filled_button(self):
        img = np.full((H, W, 3), 60, np.uint8)
        self.assertIsNone(ns["selected_event_tab"](img, boxes([("剧情", 2128, 1339), ("物资", 2379, 1339)]), H))


class EventListDragTest(unittest.TestCase):
    """实录 2026-10-22：拖列表甩出惯性，从「逃离赛博格…烟火迎春归」一下挪到「…乐园 / 沉没夜潮」，中间的「镜茧与囚蝶」被跳过。"""

    def setUp(self):
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "EventMapTask")
        body = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ("drag_event_list", "swipe_event_list")]
        self.methods = dict(ns)
        exec(compile(ast.Module(body=body, type_ignores=[]), str(source), "exec"), self.methods)

    def run_drag(self, screens, direction=1, still=False):
        """screens：每次读列表看到的活动名，从左到右每张隔 600；still=True 表示卡片都没挪（到头了）。"""
        task = Mock()
        task.width = W
        screens = [
            [(SimpleNamespace(name=n, x=600 * i + (0 if still else 150 * k)), 0) for i, n in enumerate(names)]
            for k, names in enumerate(screens)
        ]
        task.read_event_cards.side_effect = screens
        task.swipe_event_list.side_effect = lambda d, scale=1.0: self.methods["swipe_event_list"](task, d, scale)
        return task, self.methods["drag_event_list"](task, direction)

    def test_partial_edge_cards_still_count_as_moved(self):
        """实录 2026-10-22 10:34：前后都只配上中间三张、名字相同，但卡片挪了一张的位置，不能当成到头。"""
        before = [(SimpleNamespace(name=n, x=x), 100) for n, x in (("纪念日礼赞", 1210), ("共诉隐匿时", 1755), ("烟火迎春归", 2300))]
        after = [(SimpleNamespace(name=n, x=x), 100) for n, x in (("纪念日礼赞", 660), ("共诉隐匿时", 1205), ("烟火迎春归", 1750))]
        self.assertTrue(ns["list_moved"](before, after, W))
        self.assertFalse(ns["list_moved"](before, [(SimpleNamespace(name=t.name, x=t.x + 8), p) for t, p in before], W))

    def swipes(self, task):
        return [c.args[:3:2] for c in task.swipe_relative.call_args_list]

    def test_drag_taken_as_click_returns_to_list_and_drags_again(self):
        """实录 2026-10-22 13:29：拖动被当成点击进了「共诉隐匿时」，不能当成列表到头。"""
        task = Mock()
        task.width = W
        screens = [
            [(SimpleNamespace(name=n, x=600 * i), 0) for i, n in enumerate(["纪念日礼赞", "共诉隐匿时", "烟火迎春归", "素银匿信"])],
            [],
            [(SimpleNamespace(name=n, x=600 * i), 0) for i, n in enumerate(["共诉隐匿时", "烟火迎春归", "素银匿信", "镜茧与囚蝶"])],
        ]
        task.read_event_cards.side_effect = screens
        task.on_event_list.return_value = False
        task.swipe_event_list.side_effect = lambda d, scale=1.0: self.methods["swipe_event_list"](task, d, scale)
        cards = self.methods["drag_event_list"](task, 1)
        self.assertEqual("镜茧与囚蝶", cards[-1][0].name)
        task.open_event_list.assert_called_once()

    def test_overshoot_drags_back_half(self):
        task, cards = self.run_drag(
            [
                ["逃离赛博格", "纪念日礼赞", "共诉隐匿时", "烟火迎春归"],
                ["欢乐园", "沉没夜潮", "前进吧，王牌配送员！", "虚境新始"],
                ["烟火迎春归", "镜茧与囚蝶", "欢乐园", "沉没夜潮"],
            ]
        )
        self.assertEqual([t.name for t, _ in cards], ["烟火迎春归", "镜茧与囚蝶", "欢乐园", "沉没夜潮"])
        (a1, b1), (a2, b2) = self.swipes(task)
        self.assertGreater(a1, b1)  # 先往右挪（手往左拖）
        self.assertLess(a2, b2)  # 再往回拖
        self.assertAlmostEqual(abs(a2 - b2), abs(a1 - b1) / 2)
        for c in task.swipe_relative.call_args_list:
            self.assertGreater(c.kwargs["settle_time"], 0)  # 停一下再松手，不甩惯性

    def test_normal_drag_keeps_overlap(self):
        task, cards = self.run_drag([["狂想四重奏", "拂晓的回响", "密米尔的返演·上篇"], ["密米尔的返演·上篇", "密米尔的返演·下篇", "逃离赛博格"]])
        self.assertEqual(len(self.swipes(task)), 1)
        self.assertEqual(cards[0][0].name, "密米尔的返演·上篇")

    def test_list_end_returns_none(self):
        task, cards = self.run_drag([["瑞骋迎春至", "月下安魂曲"], ["瑞骋迎春至", "月下安魂曲"]], still=True)
        self.assertIsNone(cards)


if __name__ == "__main__":
    unittest.main()
