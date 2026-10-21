"""
竞技场打完后的两种卡住（实录 2026-10-20）：
段位晋升通知「您已晋升至新锐·三…」盖住结算页 → ESC 关掉；
「对战胜利」结算页只有「确认」能关 → 点确认。
只测流程，不依赖 ok 框架：把 BaseGfTask 里相关方法单独抠出来跑在 Mock 上。
"""

import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

source = Path(__file__).resolve().parents[1] / "src/core/BaseGfTask.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BaseGfTask")
wanted = ("_dismiss_notice", "_confirm_battle_result")
methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
consts = [
    n
    for n in tree.body
    if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id in ("rank_up_notice_re", "battle_result_re") for t in n.targets)
]
ns = {"re": re}
exec(compile(ast.Module(body=consts + methods, type_ignores=[]), str(source), "exec"), ns)
dismiss_notice = ns["_dismiss_notice"]
confirm_battle_result = ns["_confirm_battle_result"]
rank_up_notice_re = ns["rank_up_notice_re"]
battle_result_re = ns["battle_result_re"]


def box(name):
    return SimpleNamespace(name=name)


def find_boxes(boxes, match=None, boundary=None):
    return [b for b in boxes if match.search(b.name)]


class RegexTest(unittest.TestCase):
    def test_rank_up_notice_text(self):
        for t in ("您已晋升至新锐·三", "首次晋升至该段位可获得相应补给，补给将通过邮件发放，请注意查收。"):
            self.assertTrue(rank_up_notice_re.search(t), t)
        for t in ("对战胜利", "作战奖励", "确认", "积分：34/51", "任务完成"):
            self.assertIsNone(rank_up_notice_re.search(t), t)

    def test_battle_result_text(self):
        for t in ("对战胜利", "对战失败", "本期扩编实练已结束"):
            self.assertTrue(battle_result_re.search(t), t)
        for t in ("作战奖励", "行动结束", "作战开始", "对战胜利奖励"):
            self.assertIsNone(battle_result_re.search(t), t)


class DismissNoticeTest(unittest.TestCase):
    def make_task(self):
        task = Mock()
        task.find_boxes.side_effect = find_boxes
        return task

    def test_rank_up_notice_is_closed_with_esc(self):
        task = self.make_task()
        boxes = [
            box("03"),
            box("您已晋升至新锐·三"),
            box("首次晋升至该段位可获得相应补给，补给将通过邮件发放，请注意查收。"),
        ]
        self.assertTrue(dismiss_notice(task, boxes))
        task.back.assert_called_once()
        task.debug_shot.assert_called_once()

    def test_other_screens_are_left_alone(self):
        task = self.make_task()
        self.assertFalse(dismiss_notice(task, [box("对战胜利"), box("确认"), box("伤害统计")]))
        task.back.assert_not_called()


class ConfirmBattleResultTest(unittest.TestCase):
    def make_task(self, screen, confirm=True):
        task = Mock()
        task.box = SimpleNamespace(bottom="bottom")

        def ocr(box=None, match=None, log=False, **kw):
            if box == "bottom":
                return [box_("确认")] if confirm and match.search("确认") else []
            return [b for b in screen if match.search(b.name)]

        box_ = box
        task.ocr.side_effect = ocr
        return task

    def test_victory_screen_clicks_confirm(self):
        task = self.make_task(
            [box("03"), box("对战胜利"), box("积分：34/51"), box("作战奖励"), box("伤害统计"), box("确认")]
        )
        self.assertTrue(confirm_battle_result(task))
        self.assertEqual(task.click.call_args.args[0][0].name, "确认")

    def test_defeat_screen_clicks_confirm(self):
        task = self.make_task([box("对战失败"), box("确认")])
        self.assertTrue(confirm_battle_result(task))
        task.click.assert_called_once()

    def test_ended_notice_still_handled(self):
        task = self.make_task([box("本期扩编实练已结束"), box("确认")])
        self.assertTrue(confirm_battle_result(task))

    def test_main_screen_is_not_touched(self):
        task = self.make_task([box("整备室"), box("公共区"), box("活动层")])
        self.assertFalse(confirm_battle_result(task))
        task.click.assert_not_called()

    def test_result_without_confirm_button_returns_false(self):
        task = self.make_task([box("对战胜利")], confirm=False)
        self.assertFalse(confirm_battle_result(task))
        task.click.assert_not_called()


if __name__ == "__main__":
    unittest.main()
