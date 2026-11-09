"""
「任务完成」结算的经验页（指挥官升级时停着等点一下）。
实录 2026-11-08 前哨战：指挥官 57→58，点掉「任务完成」后停在经验页，没有「点击继续」也没有按钮，
等结算的 skip_dialogs 干等 30 秒，班组记失败；回主页按 ESC 也出不去，一键日常停下。点下方空白处一下就出「重新挑战 / 确认结算」。
"""

import ast
import re
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

source = Path(__file__).resolve().parents[1] / "src/core/BaseGfTask.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BaseGfTask")
wanted = ("skip_dialogs", "_tap_settlement_exp", "_leave_mission_settlement")
methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
funcs = [
    n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("settlement_exp_page", "describe_screen")
]
consts = [
    n
    for n in tree.body
    if isinstance(n, ast.Assign)
    and any(
        isinstance(t, ast.Name)
        and t.id
        in (
            "pop_ups",
            "map_re",
            "stamina_popup_re",
            "battle_ui_re",
            "challenge_button_re",
            "nav_tabs_re",
            "chapter_select_re",
            "story_exit_re",
            "story_blank_re",
            "LOADING_EXTEND",
        )
        for t in n.targets
    )
]
ns = {"re": re, "time": time}
exec(compile(ast.Module(body=consts + funcs + methods, type_ignores=[]), str(source), "exec"), ns)
settlement_exp_page = ns["settlement_exp_page"]

# 实录 2026-11-08 18:49:41 经验页的 OCR
EXP_PAGE = [
    "任务完成",
    "SF-P前哨战",
    "代理人",
    "助战",
    "Lv.60 Δ",
    "恶兆之钥",
    "已达等级上限",
    "OTs-14",
    "Lv.53",
    "卡庇托林",
    "Lv.51",
    "威玛西娜",
    "指挥官等级58六",
    "+1320",
    "108/1320",
]
# 点一下之后的奖励页
REWARD_PAGE = ["任务完成", "SF-P前哨战", "表现与评级", "合格800", "作战奖励", "225", "伤害统计", "重新挑战", "确认结算"]


def box(name, x=0.5, y=0.5):
    return SimpleNamespace(name=name, x=x, y=y)


def find_boxes(boxes, match=None, boundary=None):
    pats = match if isinstance(match, list) else [match]
    return [b for b in boxes if any(p.search(b.name) if hasattr(p, "search") else p == b.name for p in pats)]


class Settlement:
    """经验页只认点击（ESC 没用），点一下进奖励页；奖励页点「确认结算」离开，点「重新挑战」就再打一次。"""

    def __init__(self):
        self.page = "exp"
        self.taps = []
        self.retried = False

    def boxes(self):
        if self.page == "exp":
            return [box(n) for n in EXP_PAGE]
        if self.page == "reward":
            return [box(n) for n in REWARD_PAGE[:-2]] + [box("重新挑战", 0.766, 0.911), box("确认结算", 0.894, 0.911)]
        return [box("前哨战"), box("开始作战")]

    def tap(self, x, y):
        self.taps.append((x, y))
        if self.page == "exp":
            self.page = "reward"
        elif self.page == "reward":
            if abs(x - 0.766) < 0.06 and abs(y - 0.911) < 0.022:
                self.retried = True
            elif abs(x - 0.894) < 0.06 and abs(y - 0.911) < 0.022:
                self.page = "left"


def make_task(screen):
    task = Mock()
    task.ocr.side_effect = lambda *a, **k: screen.boxes()
    task.find_boxes.side_effect = find_boxes
    task._is_loading_frame.return_value = False
    task._is_battle_frame.return_value = False
    task._dismiss_notice.return_value = False
    task.click_relative.side_effect = lambda x, y, **kw: screen.tap(x, y)
    task.click.side_effect = lambda b, **kw: screen.tap(
        (b[0] if isinstance(b, list) else b).x, (b[0] if isinstance(b, list) else b).y
    )
    task._tap_settlement_exp.side_effect = lambda boxes: ns["_tap_settlement_exp"](task, boxes)
    task.sleep.side_effect = lambda s: None
    return task


class SettlementExpPageTest(unittest.TestCase):
    def test_recognizes_recorded_exp_page(self):
        self.assertTrue(settlement_exp_page(EXP_PAGE))

    def test_reward_page_and_other_pages_are_not_exp_page(self):
        self.assertFalse(settlement_exp_page(REWARD_PAGE))
        self.assertFalse(settlement_exp_page(["任务完成", "SF-P前哨战", "代理人"]))  # 刚弹出、还没到经验条
        self.assertFalse(settlement_exp_page(["指挥官等级 57", "整备室", "公共区"]))  # 主页左下角也有指挥官等级

    def test_battle_end_wait_taps_exp_page_then_returns_confirm(self):
        """等结算的那一步（end_match 里有「确认结算」、没有「任务完成」）：经验页点一下，等到「确认结算」。"""
        screen = Settlement()
        task = make_task(screen)
        end = ["开始作战", *ns["pop_ups"], "确认", "确认结算", "继续前进"]
        result = ns["skip_dialogs"](task, end_match=end, time_out=1, has_dialog=False, raise_if_not_found=True)
        self.assertEqual([b.name for b in result], ["确认结算"])
        self.assertEqual(screen.taps, [(0.85, 0.95)])
        self.assertFalse(screen.retried)

    def test_going_home_leaves_both_settlement_pages_without_retrying(self):
        screen = Settlement()
        task = make_task(screen)
        leave = ns["_leave_mission_settlement"]
        self.assertTrue(leave(task))  # 经验页：点空白处
        self.assertEqual(screen.page, "reward")
        self.assertTrue(leave(task))  # 奖励页：点「确认结算」
        self.assertEqual(screen.page, "left")
        self.assertFalse(screen.retried)
        self.assertFalse(leave(task))  # 不在结算页：什么都不做

    def test_tap_spot_is_outside_both_buttons(self):
        # 点空白处的位置要在「重新挑战」「确认结算」按钮外面（按钮 y 约 0.889 到 0.933）
        screen = Settlement()
        screen.page = "reward"
        screen.tap(0.85, 0.95)
        self.assertFalse(screen.retried)
        self.assertEqual(screen.page, "reward")


if __name__ == "__main__":
    unittest.main()
