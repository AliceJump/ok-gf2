"""推图关卡名、排序与面板状态的纯逻辑测试，不依赖设备与 ok-script 运行时。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ok import Box

from src.core.BaseGfTask import map_re, parse_deploy_count
from src.tasks.ClearMapTask import (
    BUTTON_RE,
    button_kind,
    canonical_name,
    classify_panel,
    merge_maps,
    order_maps,
)


class TestMapRe(unittest.TestCase):
    def test_names(self):
        for name in ["3-1", "SL-3-2", "BH-3-4", "ABC-12-3", "2-5*", "SL-2-1"]:
            self.assertIsNotNone(map_re.search(name), name)
        for name in ["420/240", "300/240", "01/12 回合", "2-", "推荐等级13", "3020"]:
            self.assertIsNone(map_re.search(name), name)


class TestOrderMaps(unittest.TestCase):
    def test_left_to_right_keeps_groups_aligned(self):
        maps = [Box(300, 10, 10, 10, name="SL-2-1"), Box(500, 10, 10, 10, name="2-6"), Box(100, 10, 10, 10, name="2-4")]
        groups = [{"SL-2-1"}, {"2-6"}, {"2-4"}]
        ordered = order_maps(maps, groups)
        self.assertEqual([m.name for m, _ in ordered], ["2-4", "SL-2-1", "2-6"])
        self.assertEqual([g for _, g in ordered], [{"2-4"}, {"SL-2-1"}, {"2-6"}])

    def test_merge_then_order(self):
        maps = [
            Box(800, 100, 10, 10, name="2-5"),
            Box(805, 103, 10, 10, name="2-5*"),
            Box(100, 100, 10, 10, name="2-3"),
        ]
        merged, groups = merge_maps(maps, x_threshold=40, y_threshold=40)
        ordered = order_maps(merged, groups)
        self.assertEqual([m.name for m, _ in ordered], ["2-3", "2-5"])
        self.assertEqual(ordered[1][1], {"2-5", "2-5*"})
        self.assertEqual(canonical_name(ordered[1][1]), "2-5")

    def test_canonical_name(self):
        self.assertEqual(canonical_name({"SL-3-2", "SL-3-2*"}), "SL-3-2")
        self.assertIsNone(canonical_name(set()))


class TestPanelParsing(unittest.TestCase):
    def test_classify_panel(self):
        # SL-5-3 实录：面板动画里只先认出「特殊奖励」，按钮还没出来 -> unknown，不能当未解锁
        self.assertEqual(classify_panel(True, False, True, [], []), ("unknown", None))
        self.assertEqual(classify_panel(True, False, True, [], ["观看"]), ("watch", ["观看"]))
        self.assertEqual(classify_panel(True, False, True, ["挑战"], []), ("challenge", ["挑战"]))
        self.assertEqual(classify_panel(True, True, True, [], []), ("locked", None))
        self.assertEqual(classify_panel(True, False, False, [], []), ("cleared", None))
        self.assertEqual(classify_panel(False, False, False, [], []), ("nopanel", None))

    def test_button_kind(self):
        # SL-5-3 实录：右半屏 OCR 只框出「观」(0.81)
        self.assertEqual(button_kind("观"), "watch")
        self.assertEqual(button_kind("观看"), "watch")
        self.assertEqual(button_kind("挑 战"), "challenge")
        self.assertEqual(button_kind("挑"), "challenge")
        self.assertIsNone(button_kind("观看者"))
        self.assertIsNone(button_kind(""))
        self.assertTrue(any(r.match("观") for r in BUTTON_RE))
        self.assertTrue(any(r.match("挑战") for r in BUTTON_RE))
        self.assertFalse(any(r.match("观看者") for r in BUTTON_RE))

    def test_parse_deploy_count(self):
        self.assertEqual(parse_deploy_count("4/4作战效能"), (4, 4))
        self.assertEqual(parse_deploy_count("3 / 5"), (3, 5))
        self.assertEqual(parse_deploy_count("414"), (4, 4))
        self.assertIsNone(parse_deploy_count("412"))  # 4/4 读成 412：总数小于已上场，不可信
        self.assertEqual(parse_deploy_count("012"), (0, 2))
        self.assertEqual(parse_deploy_count("3l4"), (3, 4))
        self.assertIsNone(parse_deploy_count("35733"))
        self.assertIsNone(parse_deploy_count("部署人形"))
