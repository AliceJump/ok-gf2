"""周常首领挑战：没到最高层级先开始作战手动打，到 9 层才自律；挑战权限不够时直接跳过。"""

import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

source = Path(__file__).resolve().parents[1] / "src/tasks/WeeklyTask.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
namespace = {"re": re}
for node in tree.body:
    if isinstance(node, ast.Assign) and any(getattr(t, "id", "").startswith(("boss_", "BOSS_")) for t in node.targets):
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "WeeklyTask")
methods = [
    n
    for n in cls.body
    if isinstance(n, ast.FunctionDef) and n.name in {"boss_fast", "_boss_level", "_boss_ticket_enough", "_boss_battle"}
]
exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), namespace)


class BossPage:
    """首领挑战页：左上角层级、右下角挑战权限；每场作战按 levels_per_win 升层。"""

    boss_fast = namespace["boss_fast"]
    _boss_level = namespace["_boss_level"]
    _boss_ticket_enough = namespace["_boss_ticket_enough"]
    _boss_battle = namespace["_boss_battle"]

    def __init__(self, level=4, tickets=3, levels_per_win=1, lose=False, level_text=True, start_works=True):
        self.level = level
        self.tickets = tickets
        self.levels_per_win = levels_per_win
        self.lose = lose
        self.level_text = level_text
        self.start_works = start_works
        self.in_deploy = False
        self.battles = 0
        self.zilv = 0
        self.kinds = []
        self.logs = []
        self.home = False
        self.shots = []

    def wait_click_ocr(self, *, match, **kwargs):
        if match == "开始作战":
            self.in_deploy = self.start_works
        return True

    def wait_ocr(self, *, match, **kwargs):
        if match is namespace["boss_level_re"]:
            if self.in_deploy:
                return []
            return [SimpleNamespace(name=f"当前层级{self.level}/9")] if self.level_text else []
        if match is namespace["boss_cost_re"]:
            return [SimpleNamespace(name=f"消耗{self.tickets}/1")]
        return [SimpleNamespace(name="常规挑战")]

    def set_lineup_kind(self, kind):
        self.kinds.append(kind)

    def auto_battle(self, **kwargs):
        """打一场消耗一张挑战权限；打输时按 BattleLost 的文字抛出。"""
        self.in_deploy = False
        self.tickets -= 1
        self.battles += 1
        if self.lose:
            raise Exception("任务失败, 没打过!")
        self.level = min(9, self.level + self.levels_per_win)

    def fast_combat(self, **kwargs):
        self.zilv += 1

    def wait_pop_up(self, **kwargs):
        pass

    def ensure_main(self, **kwargs):
        self.home = True

    def screenshot(self, name=None, **kwargs):
        self.shots.append(name)

    def info_set(self, *args):
        pass

    def log_info(self, message, **kwargs):
        self.logs.append(message)

    def run(self):
        # 只跑「常规挑战」之后的部分：前面的导航点击在桩里都是成功
        self.boss_fast()
        return self


class BossChallengeTest(unittest.TestCase):
    def test_top_level_uses_zilv(self):
        page = BossPage(level=9).run()
        self.assertEqual((0, 1), (page.battles, page.zilv))
        self.assertTrue(page.home)

    def test_climbs_with_manual_battles_then_zilv(self):
        """4 层、权限够：手动打到 9 层，再自律。"""
        page = BossPage(level=4, tickets=10).run()
        self.assertEqual(5, page.battles)
        self.assertEqual(9, page.level)
        self.assertEqual(1, page.zilv)
        self.assertEqual(["首领挑战", None] * 5, page.kinds)

    def test_no_ticket_skips_without_clicking(self):
        """实录 2026-10-25：消耗 0/1 时点开始作战/自律都没反应，直接跳过。"""
        page = BossPage(level=4, tickets=0).run()
        self.assertEqual((0, 0), (page.battles, page.zilv))
        self.assertTrue(any("挑战权限不够" in m for m in page.logs))

    def test_tickets_run_out_mid_climb(self):
        page = BossPage(level=4, tickets=2).run()
        self.assertEqual(2, page.battles)
        self.assertEqual(0, page.zilv)

    def test_level_not_raised_stops_spending_tickets(self):
        """挑战目标没全完成时层级不升，不再重复消耗挑战权限。"""
        page = BossPage(level=4, tickets=5, levels_per_win=0).run()
        self.assertEqual(1, page.battles)
        self.assertEqual(0, page.zilv)

    def test_lost_battle_stops(self):
        page = BossPage(level=4, tickets=5, lose=True).run()
        self.assertEqual(1, page.battles)
        self.assertEqual(0, page.zilv)
        self.assertEqual(["首领挑战", None], page.kinds)

    def test_start_without_response_does_not_wait_for_battle(self):
        """实录 2026-10-25：权限没认出来时点「开始作战」没反应，原来进自动战斗干等 120 秒后报错。"""
        page = BossPage(level=4, tickets=1, start_works=False).run()
        self.assertEqual((0, 0), (page.battles, page.zilv))
        self.assertEqual(["boss_start_no_response"], page.shots)
        self.assertTrue(page.home)

    def test_unreadable_level_falls_back_to_zilv(self):
        page = BossPage(level_text=False).run()
        self.assertEqual((0, 1), (page.battles, page.zilv))


if __name__ == "__main__":
    unittest.main()
