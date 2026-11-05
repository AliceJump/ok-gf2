"""
尘烟前哨战借班组助战：借的人和队里重复时弹「队伍中有相同角色，是否进行替换」。
实录 2026-11-04：战力最高的三个助战都和队里重复，提示没处理，只试三个就放弃；关弹窗只关掉了上层提示，
接着点「确定」落在遮罩上，只是把助战弹窗关了，2 分钟没进战斗，班组记成失败。
"""

import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

source = Path(__file__).resolve().parents[1] / "src/tasks/daily/daily_battle_mixin.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "DailyBattleMixin")
wanted = {"_outpost_pick_support", "_outpost_cancel_duplicate", "_outpost_close_support_popup", "chenyan_outpost"}
methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
names = {"OUTPOST_KIND", "power_re", "support_power_re", "outpost_dup_re", "OUTPOST_SUPPORT_SLOT", "OUTPOST_DUP_DIALOG"}
consts = [
    n
    for n in tree.body
    if (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in names for t in n.targets))
    or (isinstance(n, ast.FunctionDef) and n.name == "power_of")
]
ns = {"re": re}
exec(compile(ast.Module(body=consts + methods, type_ignores=[]), str(source), "exec"), ns)


def rect(x1, y1, x2, y2):
    return SimpleNamespace(x1=x1, y1=y1, x2=x2, y2=y2)


def inside(r, x, y):
    return r.x1 <= x <= r.x2 and r.y1 <= y <= r.y2


def matched(pattern, text):
    return bool(pattern.search(text)) if isinstance(pattern, re.Pattern) else pattern in text


POPUP = rect(0.16, 0.14, 0.84, 0.86)
DUP = rect(0.27, 0.24, 0.73, 0.76)
CARD_POS = [(0.29, 0.44), (0.5, 0.44), (0.71, 0.44), (0.29, 0.61), (0.5, 0.61), (0.71, 0.61)]


class OutpostScreen:
    """前哨战编队页 + 班组助战弹窗 + 「注意」提示；弹窗是模态的，点到外面的遮罩只会关掉最上面一层。"""

    def __init__(self, supports, x_closes=True):
        # supports: [(战力, 是否和队里重复)]
        self.supports = supports
        self.x_closes = x_closes
        self.popup = False
        self.dup = False
        self.selected = None
        self.borrowed = None
        self.replaced = False
        self.started = False

    def texts(self):
        out = [("本次作战使用班组人形助战", 0.64, 0.64), ("助战", 0.915, 0.84), ("确定", 0.877, 0.94)]
        out += [(p, 0.64 + 0.06 * i, 0.8) for i, p in enumerate(["14021", "7354", "6217", "5649"])]
        if self.borrowed:
            out.append((str(self.borrowed), 0.92, 0.8))
        if self.popup:
            out.append(("班组助战", 0.5, 0.18))
            out += [
                (f"心{p}", x, y) for (p, _), (x, y) in zip(self.supports, CARD_POS[: len(self.supports)], strict=True)
            ]
            if self.selected is not None:
                out.append(("入队", 0.73, 0.79))
        if self.dup:
            out += [
                ("注意", 0.5, 0.27),
                ("队伍中有相同角色，是否进行替换", 0.5, 0.48),
                ("取消", 0.4, 0.7),
                ("确认", 0.62, 0.7),
            ]
        return out

    def tap(self, x, y):
        if self.dup:
            if inside(DUP, x, y):
                if abs(x - 0.4) < 0.08 and abs(y - 0.7) < 0.03:
                    self.dup = False
                elif abs(x - 0.62) < 0.08 and abs(y - 0.7) < 0.03:
                    self.replaced = True
            else:
                self.dup = False
            return
        if self.popup:
            if not inside(POPUP, x, y):
                self.popup = False
            elif abs(x - 0.813) < 0.02 and abs(y - 0.178) < 0.03:
                self.popup = not self.x_closes
            elif abs(x - 0.73) < 0.08 and abs(y - 0.79) < 0.03 and self.selected is not None:
                power, dup = self.supports[self.selected]
                if dup:
                    self.dup = True
                else:
                    self.borrowed, self.popup = power, False
            else:
                for i, (cx, cy) in enumerate(CARD_POS[: len(self.supports)]):
                    if abs(x - cx) < 0.1 and abs(y - cy) < 0.05:
                        self.selected = i
            return
        if abs(x - 0.915) < 0.04 and abs(y - 0.84) < 0.03:
            self.popup = True
        elif abs(x - 0.877) < 0.06 and abs(y - 0.94) < 0.03:
            self.started = True


class Game:
    def __init__(self, screen):
        self.screen = screen
        self.box = SimpleNamespace(center=rect(0.25, 0.25, 0.75, 0.75), bottom_right=rect(0.5, 0.5, 1, 1))
        self.log_info = Mock()
        self.debug_shot = Mock()

    def __getattr__(self, name):
        if name in ns:
            return ns[name].__get__(self, Game)
        raise AttributeError(name)

    def box_of_screen(self, x1, y1, x2, y2):
        return rect(x1, y1, x2, y2)

    def ocr(self, box=None, match=None, **kw):
        found = [
            SimpleNamespace(name=t, x=x, y=y) for t, x, y in self.screen.texts() if box is None or inside(box, x, y)
        ]
        return [b for b in found if match is None or matched(match, b.name)]

    def wait_ocr(self, match=None, box=None, **kw):
        return self.ocr(box=box, match=match) or None

    def wait_click_ocr(self, match=None, box=None, **kw):
        found = self.ocr(box=box, match=match)
        if found:
            self.click_box(found[0])
        return found or None

    def click_box(self, b, **kw):
        self.screen.tap(b.x, b.y)

    def click_relative(self, x, y, **kw):
        self.screen.tap(x, y)

    def next_frame(self):
        pass


class OutpostSupportTest(unittest.TestCase):
    def test_duplicates_are_cancelled_then_next_support_is_borrowed(self):
        screen = OutpostScreen([(25850, True), (25718, True), (24871, True), (23501, False), (21818, True)])
        self.assertTrue(Game(screen)._outpost_pick_support())
        self.assertEqual(screen.borrowed, 23501)
        self.assertFalse(screen.dup)
        self.assertFalse(screen.replaced)

    def test_all_duplicates_close_the_popup_for_real(self):
        screen = OutpostScreen([(25850, True), (25718, True), (24871, True)])
        game = Game(screen)
        self.assertFalse(game._outpost_pick_support())
        self.assertFalse(screen.popup)
        self.assertFalse(screen.dup)
        self.assertFalse(screen.replaced)
        self.assertFalse(screen.started)

    def test_popup_that_will_not_close_stops_instead_of_clicking_the_mask(self):
        screen = OutpostScreen([(25850, True)], x_closes=False)
        with self.assertRaisesRegex(Exception, "关不掉"):
            Game(screen)._outpost_pick_support()
        self.assertFalse(screen.started)

    def test_support_already_in_slot_is_kept(self):
        screen = OutpostScreen([(25850, False)])
        screen.borrowed = 22222
        self.assertTrue(Game(screen)._outpost_pick_support())
        self.assertFalse(screen.popup)

    def test_no_support_turns_toggle_off_and_fields_five_own(self):
        task = Mock()
        task.box = SimpleNamespace(top_right="tr", bottom_right="br", bottom="b")
        task.wait_ocr.side_effect = lambda match=None, **kw: None if isinstance(match, re.Pattern) else [match]
        task._outpost_set_support_toggle.side_effect = [True, False]
        task._outpost_pick_support.return_value = False
        task._lineup_kind = None
        ns["support_enabled_for_kind"] = lambda cfg, kind: True
        ns["preset_name_for_kind"] = lambda cfg, kind: "编队1"
        self.assertTrue(ns["chenyan_outpost"](task))
        self.assertEqual([c.args for c in task._outpost_set_support_toggle.call_args_list], [(True,), (False,)])
        self.assertEqual([c.args for c in task._outpost_fill_top_power.call_args_list], [(4,), (5,)])
        task.auto_battle.assert_called_once()

    def test_borrowed_support_keeps_four_own(self):
        task = Mock()
        task.box = SimpleNamespace(top_right="tr", bottom_right="br", bottom="b")
        task.wait_ocr.side_effect = lambda match=None, **kw: None if isinstance(match, re.Pattern) else [match]
        task._outpost_set_support_toggle.return_value = True
        task._outpost_pick_support.return_value = True
        task._lineup_kind = None
        ns["support_enabled_for_kind"] = lambda cfg, kind: True
        ns["preset_name_for_kind"] = lambda cfg, kind: "编队1"
        ns["chenyan_outpost"](task)
        task._outpost_set_support_toggle.assert_called_once_with(True)
        task._outpost_fill_top_power.assert_called_once_with(4)


if __name__ == "__main__":
    unittest.main()
