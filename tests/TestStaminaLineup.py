"""体力弹窗、自律灰色、按关卡类型选编队/助战、助战卡片识别的纯逻辑测试，不依赖设备与 ok-script 运行时。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ok import Box

from src.core.BaseGfTask import (
    has_forbidden_restore_text,
    popup_texts,
    stamina_popup_re,
    stamina_tab_points,
    stamina_value,
    tab_count,
)
from src.core.support_select import (
    check_point,
    empty_tiles,
    filter_point,
    find_cards,
    is_orange_check,
    make_check_frame,
    pick_candidates,
    read_badge,
)


class TestStaminaPopup(unittest.TestCase):
    """按 1280x768 窗口实测的「情报拼图补充」弹窗布局：标题中心 (614, 215)，页签中心 y=323，x=488/612/738。"""

    def setUp(self):
        self.h = 768
        self.title = Box(548, 203, 132, 24, name="情报拼图补充")

    def test_title_regex(self):
        for name in ["情报拼图补充", "情报拼圖补充", "体力不足"]:
            self.assertIsNotNone(stamina_popup_re.search(name), name)
        for name in ["继续前进", "情报", "补充"]:
            self.assertIsNone(stamina_popup_re.search(name), name)

    def test_tab_points(self):
        pts = stamina_tab_points(self.title, self.h)
        self.assertEqual(len(pts), 3)
        for (x, y), (ex, ey) in zip(pts, [(488, 323), (612, 323), (738, 323)], strict=True):
            self.assertAlmostEqual(x, ex, delta=6)
            self.assertAlmostEqual(y, ey, delta=6)

    def test_forbidden_text(self):
        self.assertTrue(has_forbidden_restore_text(["使用坍塌晶条恢复情报拼图"]))
        self.assertTrue(has_forbidden_restore_text(["购买", "确认"]))
        self.assertFalse(has_forbidden_restore_text(["快速取出调度室储存情报拼图", "取出数量 0", "确认", "取消"]))
        # 实录：第二页签是接入密钥，是正常体力道具，不能被「兑换」两个字误伤
        self.assertFalse(
            has_forbidden_restore_text(["消耗接入密钥兑换", "消耗1接入密钥，获得60情报拼图", "取消", "确认"])
        )

    def test_popup_texts_excludes_background(self):
        boxes = [
            Box(500, 450, 220, 20, name="快速取出调度室储存情报拼图"),
            Box(1030, 70, 60, 20, name="81/240"),  # 右上角体力
            Box(40, 360, 40, 20, name="4-3"),  # 弹窗外的关卡卡片
            Box(730, 530, 40, 20, name="确认"),
        ]
        self.assertEqual(popup_texts(boxes, self.title, self.h), ["快速取出调度室储存情报拼图", "确认"])

    def test_stamina_value_ignores_coin_tail(self):
        from src.core.BaseGfTask import stamina_value

        boxes = [Box(1075, 20, 30, 20, name="60"), Box(1150, 20, 70, 20, name="147/240")]
        self.assertEqual(stamina_value(boxes, 768), 147)
        self.assertIsNone(stamina_value([Box(1075, 20, 30, 20, name="760")], 768))

    def test_stamina_value(self):
        # 实录：接入密钥兑换后弹窗还开着，右上角 9/240 变成 69/240，靠这个数判断成功
        boxes = [
            Box(1085, 22, 46, 18, name="9/240"),
            Box(600, 345, 28, 16, name="136"),
            Box(730, 530, 40, 20, name="确认"),
        ]
        self.assertEqual(stamina_value(boxes, self.h), 9)
        self.assertEqual(stamina_value([Box(1085, 22, 50, 18, name="69 /240")], self.h), 69)
        self.assertIsNone(stamina_value([Box(1085, 400, 46, 18, name="9/240")], self.h))  # 不在顶部
        self.assertIsNone(stamina_value([Box(1085, 22, 46, 18, name="确认")], self.h))

    def test_tab_count(self):
        boxes = [
            Box(600, 345, 28, 16, name="121"),
            Box(720, 345, 36, 16, name="6140"),
            Box(1140, 70, 50, 20, name="6140"),
        ]
        self.assertEqual(tab_count(boxes, 612, 323, self.h), 121)
        self.assertEqual(tab_count(boxes, 738, 323, self.h), 6140)
        self.assertIsNone(tab_count(boxes, 488, 323, self.h))


class TestPresetByKind(unittest.TestCase):
    def test_kind_falls_back_to_default(self):
        from src.core.lineup_config import preset_name_for_kind

        cfg = {"编队名": "编队1", "竞技场编队": "编队3", "体力本编队": "  ", "班组编队": "", "活动编队": "编队5"}
        self.assertEqual(preset_name_for_kind(cfg, "竞技场"), "编队3")
        self.assertEqual(preset_name_for_kind(cfg, "体力本"), "编队1")
        self.assertEqual(preset_name_for_kind(cfg, "班组"), "编队1")
        self.assertEqual(preset_name_for_kind(cfg, "活动"), "编队5")
        self.assertEqual(preset_name_for_kind(cfg, "推图"), "编队1")
        self.assertEqual(preset_name_for_kind(cfg, None), "编队1")
        self.assertEqual(preset_name_for_kind({"编队名": ""}, "竞技场"), "")
        self.assertEqual(preset_name_for_kind({"编队名": "编队1", "尘烟前哨战编队": "尘烟队"}, "尘烟前哨战"), "尘烟队")
        self.assertEqual(preset_name_for_kind({"编队名": "编队1", "推图编队": "推图队"}, None), "推图队")


class TestSupportByKind(unittest.TestCase):
    def test_default_global_scope_priority(self):
        from src.core.lineup_config import support_enabled_for_kind

        # 内置默认开
        self.assertTrue(support_enabled_for_kind({}, None))
        self.assertTrue(support_enabled_for_kind({}, "尘烟前哨战"))
        # 全局关 -> 沿用全局的场景都不借
        self.assertFalse(support_enabled_for_kind({"借好友助战": False}, "尘烟前哨战"))
        self.assertFalse(support_enabled_for_kind({"借好友助战": False, "推图助战": "沿用全局"}, None))
        # 场景单独设置优先于全局
        self.assertTrue(support_enabled_for_kind({"借好友助战": False, "尘烟前哨战助战": "开"}, "尘烟前哨战"))
        self.assertFalse(support_enabled_for_kind({"借好友助战": True, "推图助战": "关"}, None))
        # 没有好友助战的场景永远不借
        self.assertFalse(support_enabled_for_kind({"借好友助战": True}, "竞技场"))
        self.assertFalse(support_enabled_for_kind({"借好友助战": True}, "未知场景"))

    def test_option_has_scope_keys(self):
        from src.core.lineup_config import SCOPES, lineup_option

        for s in SCOPES:
            self.assertIn(f"{s['name']}编队", lineup_option.default_config)
            self.assertEqual(f"{s['name']}助战" in lineup_option.default_config, s["support"])


class TestZilvLocked(unittest.TestCase):
    def test_gray_gap_rule(self):
        from src.core.BaseGfTask import zilv_locked

        self.assertTrue(zilv_locked(135, 177))  # 实录：灰自律 vs 白挑战
        self.assertFalse(zilv_locked(175, 177))  # 两个都是白的
        self.assertFalse(zilv_locked(120, 130))  # 整体偏暗但差不多亮
        self.assertIsNone(zilv_locked(None, 177))

    def test_real_screenshot(self):
        import cv2
        from ok import Box

        from src.core.BaseGfTask import region_mean_gray, zilv_locked

        frame = cv2.imread(str(Path(__file__).resolve().parent / "fixtures" / "zilv_locked_1280x768.png"))
        self.assertIsNotNone(frame)
        zilv = region_mean_gray(frame, Box(932, 692, 95, 45))
        challenge = region_mean_gray(frame, Box(1040, 692, 188, 45))
        self.assertTrue(zilv_locked(zilv, challenge), (zilv, challenge))
        self.assertFalse(zilv_locked(challenge, challenge))


class TestSupportSelect(unittest.TestCase):
    """按 1280x768 好友助战面板实测：战力中心 (1033,198)/(1126,198)/(1213,198)，第二行各下移 112。"""

    W, H = 1280, 768
    FIXTURE = Path(__file__).resolve().parent / "fixtures" / "support_panel_1280x768.png"

    def boxes(self):
        return [
            Box(1015, 190, 36, 16, name="25871"),
            Box(1108, 190, 36, 16, name="17405"),
            Box(1195, 190, 36, 16, name="17342"),
            Box(1015, 302, 36, 16, name="16083"),
            Box(1108, 302, 36, 16, name="5274"),
            Box(1195, 302, 36, 16, name="2830"),
        ]

    def test_find_cards_sorted_with_badge_reader(self):
        badges = {"25871": 6, "17405": 0, "17342": 1, "16083": 4, "5274": 1, "2830": None}
        cards = find_cards(self.boxes(), self.W, self.H, badge_of=lambda b: badges[b.name])
        self.assertEqual(
            [(c["power"], c["badge"]) for c in cards],
            [(25871, 6), (17405, 0), (17342, 1), (16083, 4), (5274, 1), (2830, None)],
        )
        c6 = cards[0]
        self.assertAlmostEqual(c6["center"][0], 1033, delta=3)
        self.assertAlmostEqual(c6["center"][1], 198 - 0.065 * self.H, delta=3)

    def test_pick_candidates(self):
        badges = {"25871": 6, "17405": 0, "17342": 1, "16083": 4, "5274": 1, "2830": None}
        cards = find_cards(self.boxes(), self.W, self.H, badge_of=lambda b: badges[b.name])
        self.assertEqual([c["power"] for c in pick_candidates(cards, 6)], [25871])
        self.assertEqual([c["power"] for c in pick_candidates(cards, 4)], [25871, 16083])
        self.assertEqual(pick_candidates(cards, 7), [])

    def test_read_badge_from_real_panel(self):
        import cv2

        frame = cv2.imread(str(self.FIXTURE))
        self.assertIsNotNone(frame)
        expected = {"25871": 6, "17405": 0, "17342": 1, "16083": 4, "5274": 1, "2830": 1}
        for b in self.boxes():
            self.assertEqual(read_badge(frame, b, self.W, self.H), expected[b.name], b.name)
        # 没有蓝圈的位置读不到
        self.assertIsNone(read_badge(frame, Box(600, 400, 36, 16, name="1234"), self.W, self.H))

    def test_orange_check(self):
        cards = find_cards(self.boxes(), self.W, self.H)
        c = cards[0]
        x, y = check_point(c, self.W, self.H)
        self.assertAlmostEqual(x, 1062, delta=3)
        self.assertAlmostEqual(y, 117, delta=3)
        frame = make_check_frame(self.W, self.H, [(x, y)])
        self.assertTrue(is_orange_check(frame, x, y))
        self.assertFalse(is_orange_check(frame, *check_point(cards[3], self.W, self.H)))
        self.assertFalse(is_orange_check(None, x, y))

    def test_filter_point_my_tab_lower(self):
        tab = Box(950, 20, 100, 30)
        _, y1 = filter_point(tab, "全部", 1280, 768)
        _, y2 = filter_point(tab, "全部", 1280, 768, my_tab=True)
        self.assertAlmostEqual(y2 - y1, 0.0625 * 768, places=3)

    def test_filter_point(self):
        tab = Box(1100, 22, 110, 16, name="好友助战")
        x, y = filter_point(tab, "物理", self.W, self.H)
        self.assertAlmostEqual(x, 1060, delta=4)
        self.assertAlmostEqual(y, 70, delta=4)
        x_all, _ = filter_point(tab, None, self.W, self.H)
        self.assertAlmostEqual(x_all, 1012, delta=4)

    def test_identify_cards_from_real_panel(self):
        import cv2

        from src.core.support_select import AvatarBook, identify_cards

        frame = cv2.imread(str(self.FIXTURE))
        cards = [
            {"power_box": Box(x, y, 40, 16, name="1")}
            for x, y in [(1015, 190), (1108, 190), (1195, 190), (1015, 302), (1108, 302), (1195, 302)]
        ]
        identify_cards(frame, cards, 1280, 768, AvatarBook())
        self.assertEqual([c["name"] for c in cards], ["威玛西娜"] * 5 + [None])
        self.assertEqual(cards[0]["avatar"].shape, (54, 52, 3))

    def test_avatar_book_learn(self):
        import os
        import tempfile

        import numpy as np

        from src.core.support_select import AvatarBook

        with tempfile.TemporaryDirectory() as d:
            book = AvatarBook(d)
            rng = np.random.default_rng(0)
            crop = rng.integers(0, 255, (54, 52, 3), dtype=np.uint8)
            self.assertFalse(book.learn("Lv.60", crop))
            self.assertTrue(book.learn("春田", crop))
            self.assertFalse(book.learn("春田", crop))  # 同一张立绘不重复存
            skin = rng.integers(0, 255, (54, 52, 3), dtype=np.uint8)
            self.assertTrue(book.learn("春田", skin))  # 换皮肤的立绘另存一张
            self.assertFalse(book.learn("春田", skin))
            self.assertEqual(sorted(os.listdir(d)), ["春田.png", "春田_2.png"])
            fresh = AvatarBook(d)
            self.assertEqual(fresh.match(crop)[0], "春田")
            self.assertEqual(fresh.match(skin)[0], "春田")
            self.assertEqual(len(fresh.load()["春田"]), 2)

    def test_find_deploy_tiles(self):
        import cv2

        from src.core.support_select import TILE_EMPTY_FILL, far_point, find_deploy_tiles

        row = cv2.imread(str(self.FIXTURE.parent / "deploy_empty_row_1280x768.jpg"))
        tiles = find_deploy_tiles(row, 1280, 768)
        good = [t for t in tiles if t["fill"] >= TILE_EMPTY_FILL]
        self.assertEqual(len(good), 4, tiles)
        for want in [(721, 492), (650, 553), (849, 397), (789, 443)]:
            self.assertTrue(
                any(abs(t["center"][0] - want[0]) <= 12 and abs(t["center"][1] - want[1]) <= 12 for t in good),
                (want, tiles),
            )

        one = cv2.imread(str(self.FIXTURE.parent / "deploy_one_empty_1280x768.jpg"))
        tiles = find_deploy_tiles(one, 1280, 768)
        self.assertLessEqual(abs(tiles[0]["center"][0] - 843), 12, tiles)
        self.assertLessEqual(abs(tiles[0]["center"][1] - 491), 12, tiles)
        self.assertGreaterEqual(tiles[0]["fill"], 0.95)
        x, y = far_point(tiles, 1280, 768)
        self.assertTrue(
            all(((x * 1280 - t["center"][0]) ** 2 + (y * 768 - t["center"][1]) ** 2) ** 0.5 > 150 for t in tiles)
        )

    def test_find_unit_tags(self):
        import cv2

        from src.core.support_select import find_unit_tags, unit_tiles_from_tags

        one = cv2.imread(str(self.FIXTURE.parent / "deploy_one_empty_1280x768.jpg"))
        tags = find_unit_tags(one, 1280, 768)
        for want in [(773, 461), (705, 398), (781, 356), (623, 445)]:
            self.assertTrue(any(abs(x - want[0]) <= 6 and abs(y - want[1]) <= 6 for x, y, _ in tags), (want, tags))
        self.assertLessEqual(len(tags), 6, tags)
        tiles = unit_tiles_from_tags(tags, 768)
        self.assertEqual(len(tiles), len(tags))
        self.assertTrue(all(abs(ty - y - 0.083 * 768) < 1 for (x, y, _), (tx, ty) in zip(tags, tiles)))

        row = cv2.imread(str(self.FIXTURE.parent / "deploy_empty_row_1280x768.jpg"))
        self.assertEqual(find_unit_tags(row, 1280, 768), [])

    def test_empty_tiles(self):
        tiles = [
            {"center": (182, 365), "bbox": (121, 331, 126, 71)},  # 头顶有 3
            {"center": (85, 384), "bbox": (36, 345, 121, 116)},  # 空
            {"center": (249, 434), "bbox": (181, 388, 137, 98)},  # 头顶有 2
        ]
        digits = [Box(182, 280, 18, 18, name="3"), Box(252, 342, 18, 18, name="2"), Box(1030, 70, 30, 20, name="4")]
        self.assertEqual([t["center"] for t in empty_tiles(tiles, digits, self.H)], [(85, 384)])
