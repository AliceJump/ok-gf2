"""
阵容整理：规划（纯函数）+ 观察-执行-再观察循环（模拟部署界面，注入失手）。
实录 2026-10-20：借到 6 椎威玛西娜时，自己的威玛西娜和上一关留下的助战翡图萨都在场上。
"""

import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import ok.util.config
except ImportError:  # mac 上没装 ok 框架：只需要 ConfigOption 这个壳
    ok = types.ModuleType("ok")
    util = types.ModuleType("ok.util")
    config = types.ModuleType("ok.util.config")
    config.ConfigOption = lambda *a, **k: SimpleNamespace(args=a, kwargs=k)
    ok.util, util.config = util, config
    sys.modules.update({"ok": ok, "ok.util": util, "ok.util.config": config})

from src.core.base_mixin.lineup_mixin import LineupMixin
from src.core.lineup_plan import LineupState, Unit, deploy_count_from_boxes, plan_lineup


def own(name, power, deployed=False):
    return Unit(name, power, deployed=deployed)


def sup(name, power=0):
    return Unit(name, power, deployed=True, support=True)


def actions(steps):
    return [(s.action, s.unit.name) for s in steps]


class PlanTest(unittest.TestCase):
    def test_real_case_old_support_and_same_name(self):
        """场上 春田/贝丝蒂/威玛西娜 + 旧助战翡图萨 4/4，借 6 椎威玛西娜：两个都撤，上助战，补一个战力最高的。"""
        state = LineupState(
            4,
            4,
            own=[
                own("威玛西娜", 4522, True),
                own("春田", 3224, True),
                own("贝丝蒂", 3207, True),
                own("琼玖", 5409),
                own("罗蕾莱", 1408),
            ],
            supports_on_map=[sup("翡图萨")],
        )
        steps = plan_lineup(state, Unit("威玛西娜", 24871, support=True))
        self.assertEqual(
            actions(steps),
            [("withdraw", "翡图萨"), ("withdraw", "威玛西娜"), ("deploy", "威玛西娜"), ("deploy", "琼玖")],
        )
        self.assertTrue(steps[2].unit.support)
        self.assertFalse(steps[3].unit.support)

    def test_same_name_only(self):
        state = LineupState(
            4,
            4,
            own=[
                own("威玛西娜", 4522, True),
                own("春田", 3224, True),
                own("贝丝蒂", 3207, True),
                own("琼玖", 5409, True),
                own("罗蕾莱", 1408),
            ],
        )
        self.assertEqual(
            actions(plan_lineup(state, Unit("威玛西娜", 1, support=True))),
            [("withdraw", "威玛西娜"), ("deploy", "威玛西娜")],
        )

    def test_full_without_conflict_drops_weakest(self):
        state = LineupState(3, 3, own=[own("A", 900, True), own("B", 500, True), own("C", 700, True), own("D", 800)])
        self.assertEqual(actions(plan_lineup(state, Unit("X", 1, support=True))), [("withdraw", "B"), ("deploy", "X")])

    def test_not_full_just_adds_support_then_fills(self):
        state = LineupState(4, 2, own=[own("A", 900, True), own("B", 500, True), own("C", 700), own("D", 800)])
        self.assertEqual(actions(plan_lineup(state, Unit("X", 1, support=True))), [("deploy", "X"), ("deploy", "D")])

    def test_support_already_there_only_fills(self):
        state = LineupState(
            4, 3, own=[own("A", 900, True), own("B", 500, True), own("C", 700)], supports_on_map=[sup("威玛西娜")]
        )
        self.assertEqual(actions(plan_lineup(state, Unit("威玛西娜", 1, support=True))), [("deploy", "C")])

    def test_done(self):
        state = LineupState(2, 2, own=[own("A", 900, True), own("C", 700)], supports_on_map=[sup("X")])
        self.assertEqual(plan_lineup(state, Unit("X", 1, support=True)), [])
        self.assertEqual(plan_lineup(LineupState(2, 2, own=[own("A", 9, True), own("B", 8, True)])), [])

    def test_fill_skips_same_name_and_excluded(self):
        state = LineupState(3, 1, own=[own("A", 900, True), own("威玛西娜", 950), own("C", 700), own("D", 600)])
        support = Unit("威玛西娜", 1, support=True)
        self.assertEqual(actions(plan_lineup(state, support)), [("deploy", "威玛西娜"), ("deploy", "C")])
        self.assertEqual(
            actions(plan_lineup(state, None, exclude={("威玛西娜", 950)})), [("deploy", "C"), ("deploy", "D")]
        )

    def test_unknown_capacity_does_not_fill_blindly(self):
        state = LineupState(None, None, own=[own("威玛西娜", 4522, True), own("C", 700)])
        self.assertEqual(
            actions(plan_lineup(state, Unit("威玛西娜", 1, support=True))),
            [("withdraw", "威玛西娜"), ("deploy", "威玛西娜")],
        )


def box(name, x, y, w=60, h=30):
    return SimpleNamespace(name=name, x=x, y=y, width=w, height=h)


class CountTest(unittest.TestCase):
    def test_objective_counter_is_ignored(self):
        """实录：关卡目标「使用刀的人形 1/3」就在计数下面一行。"""
        boxes = [
            box("部署人形", 975, 50, 130),
            box("4/4", 1190, 50),
            box("作战效能", 1290, 50),
            box("使用刀的人形卫三二四", 975, 125, 250),
            box("1/3", 1490, 125),
        ]
        self.assertEqual(deploy_count_from_boxes(boxes), (4, 4))

    def test_only_objective_counter_reads_nothing(self):
        boxes = [box("部署人形", 975, 50, 130), box("使用刀的人形", 975, 125, 250), box("1/3", 1490, 125)]
        self.assertIsNone(deploy_count_from_boxes(boxes))

    def test_glued_and_misread_slash(self):
        self.assertEqual(deploy_count_from_boxes([box("部署人形3/4", 975, 50, 200)]), (3, 4))
        self.assertEqual(deploy_count_from_boxes([box("部署人形", 975, 50, 130), box("414", 1190, 50)]), (4, 4))
        self.assertEqual(deploy_count_from_boxes([box("2/4", 1190, 50)]), (2, 4))


class FakeScreen(LineupMixin):
    """模拟部署界面：只模拟观察/撤/上这几个动作的效果，可以注入失手。"""

    def __init__(self, cap, own_cards, on_map, support_list=(), fail=()):
        self.cap = cap
        self.own_cards = dict(own_cards)  # 名字 -> 战力
        self.on_map = list(on_map)  # [(名字, 是否助战)]
        self.fail = list(fail)  # 依次消耗的失手：("withdraw", 名字) / ("deploy", 名字) / ("count", None)
        self.log = []
        self._freed_tiles = []
        self._borrowed_support = None

    # 框架接口
    def info_set(self, *a):
        pass

    def log_info(self, msg, notify=False):
        self.log.append(msg)

    def debug_shot(self, *a, **k):
        pass

    def sleep(self, *a):
        pass

    @staticmethod
    def _name_like(a, b):
        return bool(a) and bool(b) and (a in b or b in a)

    def _take_fail(self, kind, name):
        if (kind, name) in self.fail:
            self.fail.remove((kind, name))
            return True
        return False

    # 被替换的三个动作
    map_blind = False  # 点地图认不出助战（实录 LA-1-3）
    count_always_fails = False  # 顶部 n/m 一直读不到（实录 13-1）

    def _observe_lineup(self, need_map=True, want=None):
        if self.count_always_fails:
            self.fail.append(("count", None))
        n = None if self._take_fail("count", None) else len(self.on_map)
        own_on = {name for name, s in self.on_map if not s}
        units = [Unit(name, p, deployed=name in own_on) for name, p in self.own_cards.items()]
        supports = [Unit(name, 0, deployed=True, support=True) for name, s in self.on_map if s] if need_map else []
        known = self._borrowed_support or (want.name if want is not None and want.deployed else None)
        if self.map_blind:
            supports = (
                [Unit(known, 0, deployed=True, support=True)] if known and (n is None or n - len(own_on) == 1) else []
            )
        return LineupState(None if n is None else self.cap, n, units, supports)

    def _withdraw(self, step):
        u = step.unit
        if self._take_fail("withdraw", u.name):
            return False
        self.on_map.remove((u.name, u.support))
        return True

    def _deploy(self, step, want):
        u = step.unit
        if self._take_fail("deploy", u.name) or len(self.on_map) >= self.cap:
            return False
        if any(self._name_like(n, u.name) for n, _ in self.on_map):
            return False  # 游戏不让同名同时上场
        self.on_map.append((u.name, u.support))
        if u.support:
            self._borrowed_support = u.name
        return True


OWN = {"威玛西娜": 4522, "春田": 3224, "贝丝蒂": 3207, "琼玖": 5409, "罗蕾莱": 1408}
WANT = Unit("威玛西娜", 24871, support=True)


class ReconcileTest(unittest.TestCase):
    def test_real_case_in_one_round(self):
        s = FakeScreen(4, OWN, [("春田", False), ("贝丝蒂", False), ("威玛西娜", False), ("翡图萨", True)])
        self.assertTrue(s.reconcile_lineup(WANT))
        self.assertCountEqual(s.on_map, [("春田", False), ("贝丝蒂", False), ("威玛西娜", True), ("琼玖", False)])

    def test_withdraw_fails_once_then_next_round_fixes(self):
        s = FakeScreen(
            4,
            OWN,
            [("春田", False), ("贝丝蒂", False), ("威玛西娜", False), ("翡图萨", True)],
            fail=[("withdraw", "威玛西娜")],
        )
        self.assertTrue(s.reconcile_lineup(WANT))
        self.assertIn(("威玛西娜", True), s.on_map)
        self.assertNotIn(("威玛西娜", False), s.on_map)
        self.assertEqual(len(s.on_map), 4)

    def test_own_card_fails_next_strongest_fills(self):
        s = FakeScreen(
            4,
            OWN,
            [("春田", False), ("贝丝蒂", False), ("威玛西娜", False)],
            fail=[("deploy", "琼玖"), ("deploy", "琼玖")],
        )
        self.assertTrue(s.reconcile_lineup(WANT))
        self.assertIn(("罗蕾莱", False), s.on_map)
        self.assertIn(("威玛西娜", True), s.on_map)

    def test_support_cannot_be_placed_refills_own(self):
        s = FakeScreen(
            4,
            OWN,
            [("春田", False), ("贝丝蒂", False), ("威玛西娜", False), ("琼玖", False)],
            fail=[("deploy", "威玛西娜")] * 3,
        )
        self.assertTrue(s.reconcile_lineup(WANT))
        self.assertEqual(len(s.on_map), 4)
        self.assertFalse(any(sup_ for _, sup_ in s.on_map))
        self.assertTrue(any("没能上场" in m for m in s.log))

    def test_count_unreadable_first_round(self):
        s = FakeScreen(4, OWN, [("春田", False)], fail=[("count", None)])
        self.assertTrue(s.reconcile_lineup(None))
        self.assertEqual(len(s.on_map), 4)

    def test_support_kept_by_game_but_map_scan_blind(self):
        """好友助战列表里要借的卡已打勾：就算点地图没认出来，也不白撤人。"""
        s = FakeScreen(4, OWN, [("春田", False), ("贝丝蒂", False), ("罗蕾莱", False), ("威玛西娜", True)])
        s.map_blind = True
        want = Unit("威玛西娜", 24871, deployed=True, support=True)
        self.assertTrue(s.reconcile_lineup(want))
        self.assertCountEqual(s.on_map, [("春田", False), ("贝丝蒂", False), ("罗蕾莱", False), ("威玛西娜", True)])

    def test_count_unreadable_support_checked_does_nothing(self):
        """实录 2026-10-20 13-1：顶部只读到「4」，助战在场且好友列表里打了勾——什么都不该做。"""
        s = FakeScreen(4, OWN, [("OTs-14", False), ("春田", False), ("贝丝蒂", False), ("威玛西娜", True)])
        s.map_blind = True
        s.count_always_fails = True
        deployed = []
        orig = s._deploy
        s._deploy = lambda step, want: deployed.append(step.unit.name) or orig(step, want)
        s.reconcile_lineup(Unit("威玛西娜", 24871, deployed=True, support=True))
        self.assertEqual(deployed, [])
        self.assertEqual(len(s.on_map), 4)

    def test_keep_existing_support(self):
        s = FakeScreen(4, OWN, [("春田", False), ("贝丝蒂", False), ("琼玖", False), ("威玛西娜", True)])
        self.assertTrue(s.reconcile_lineup(WANT))
        self.assertEqual(s._borrowed_support, "威玛西娜")
        self.assertEqual(len(s.on_map), 4)


class LocateCardTest(unittest.TestCase):
    """实录 2026-10-20：面板里在场的卡片排前面，撤下威玛西娜后顺序变了，按旧坐标点到了威玛西娜。"""

    def test_card_found_by_power_after_reorder(self):
        s = FakeScreen(4, OWN, [])
        s._open_own_tab = lambda: None
        s._scan_cards = lambda: [
            {"name": "春田", "power": 3224, "center": (100, 100)},
            {"name": "OTs-14", "power": 5409, "center": (200, 100)},
            {"name": "威玛西娜", "power": 4522, "center": (300, 100)},
        ]
        stale = Unit("OTs-14", 5409, ref={"center": (300, 100)})
        self.assertEqual(s._locate_own_card(stale)["center"], (200, 100))
        self.assertIsNone(s._locate_own_card(Unit("X", 1)))


class VisionTest(unittest.TestCase):
    def test_freed_tile_from_frame_diff(self):
        import numpy as np

        from src.core.support_select import freed_tile

        w, h = 1280, 720
        before = np.full((h, w, 3), 60, np.uint8)
        before[300:420, 500:560] = 200  # 站在地格上的人形立绘，脚在 y≈420
        after = np.full((h, w, 3), 60, np.uint8)
        x, y = freed_tile(before, after, w, h)
        self.assertAlmostEqual(x, 530, delta=5)
        self.assertGreater(y, 380)
        self.assertIsNone(freed_tile(before, before.copy(), w, h))

    def test_unit_tags_found_at_2560(self):
        """实录 2026-10-20：2560x1440 下旧模板（边框写死 1~2 像素、中间画个「1」）四个编号标签一个都没认出来。"""
        import cv2

        from src.core.support_select import find_unit_tags

        frame = cv2.imread(str(Path(__file__).resolve().parent / "fixtures" / "deploy_unit_tags_2560x1440.jpg"))
        tags = find_unit_tags(frame, 2560, 1440)
        for want in [(820, 735), (671, 670), (1269, 755), (1100, 684)]:  # 标签 1、4、3、2
            self.assertTrue(any(abs(x - want[0]) <= 8 and abs(y - want[1]) <= 8 for x, y, _ in tags), (want, tags))

    def test_dark_badge_disk_found_at_2560(self):
        """实录 2026-10-20 RDP 会话 2560x1440：蓝圈是暗青色（V 120~160），旧阈值 V>170 一个都找不到。"""
        import cv2

        from src.core.support_select import BADGE_DX, BADGE_DY, find_badge_disk, parse_badge_text

        crop = cv2.imread(str(Path(__file__).resolve().parent / "fixtures" / "support_panel_dark_badge_2560x1440.jpg"))
        self.assertIsNotNone(crop)
        frame = cv2.copyMakeBorder(crop, 0, 0, 1920, 0, cv2.BORDER_CONSTANT)
        # 第一行三张卡的战力数字中心（6 椎、6 椎、4 椎）
        for px, py in ((2063, 399), (2249, 399), (2435, 399)):
            disk = find_badge_disk(frame, px + BADGE_DX * 2560, py + BADGE_DY * 1440, 1440 / 768)
            self.assertIsNotNone(disk, (px, py))
            self.assertAlmostEqual(disk[1], 274, delta=6)
        self.assertEqual(parse_badge_text("'4"), 4)
        self.assertEqual(parse_badge_text("-"), 0)
        self.assertIsNone(parse_badge_text("12"))


if __name__ == "__main__":
    unittest.main()
