"""
ensure_main：加载页的时间不算进回主页的超时。
实录 2026-11-08：从极限峰值部署界面回主页，退出作战 14 秒、加载 15 秒，加载刚结束就满 30 秒；
原来只在超时那一刻看一眼画面，那时已经是峰值推定页（不是加载页），直接报「请从游戏主页进入」。
用假时钟按实录时间线跑，不依赖 ok 框架。
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
methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "ensure_main"]


class Clock:
    def __init__(self):
        self.t = 0.0

    def time(self):
        return self.t


class Game:
    """按时间线切画面：battle（战斗菜单/退出确认）→ loading → peak（峰值推定页，按一次返回就到主页）→ main。"""

    IS_MAIN_COST = 4.5  # 实录里每轮 is_main 大约 4.5 秒

    def __init__(self, clock, loading_from, loading_until):
        self.clock = clock
        self.loading_from = loading_from
        self.loading_until = loading_until
        self.backed = False

    def page(self):
        t = self.clock.t
        if self.backed:
            return "main"
        if t < self.loading_from:
            return "battle"
        if t < self.loading_until:
            return "loading"
        return "peak"

    def is_main(self, recheck_time=1, esc=True):
        page = self.page()
        self.clock.t += self.IS_MAIN_COST
        if page == "main":
            return True
        if page == "peak":
            self.backed = True  # is_main 在峰值推定页点了返回
        return False

    def ocr(self, *args, **kwargs):
        texts = {
            "battle": ["退出作战", "确认"],
            "loading": ["87%", "资源加载中", "2067年，由国安局主导的“人形角斗场取缔行动”顺利开展"],
            "peak": ["01", "激化阶群·子群1", "常规峰值", "极限峰值"],
            "main": ["整备室", "公共区"],
        }[self.page()]
        return [SimpleNamespace(name=t) for t in texts]


def make(loading_from, loading_until):
    clock = Clock()
    ns = {"re": re, "time": clock}
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), ns)
    game = Game(clock, loading_from, loading_until)
    task = Mock()
    task._deadline_bump = 0
    task.is_main.side_effect = game.is_main
    task.ocr.side_effect = game.ocr
    task._is_loading_frame.side_effect = lambda boxes: any("资源加载中" in b.name for b in boxes)
    task.sleep.side_effect = lambda s: setattr(clock, "t", clock.t + s)
    return ns["ensure_main"], task, clock


class EnsureMainLoadingTest(unittest.TestCase):
    def test_loading_right_before_deadline_does_not_time_out(self):
        ensure_main, task, clock = make(loading_from=14, loading_until=29.5)
        self.assertTrue(ensure_main(task))
        task.debug_shot.assert_not_called()
        self.assertLess(clock.t, 60)

    def test_stuck_page_without_loading_still_times_out(self):
        ensure_main, task, clock = make(loading_from=1000, loading_until=1000)
        task.is_main.side_effect = lambda **kw: setattr(clock, "t", clock.t + 4.5) or False
        with self.assertRaisesRegex(Exception, "请从游戏主页进入"):
            ensure_main(task)
        self.assertLess(clock.t, 40)
        task.debug_shot.assert_called_once_with("ensure_main_timeout")

    def test_endless_loading_is_capped_by_loading_grace(self):
        ensure_main, task, clock = make(loading_from=0, loading_until=10_000)
        with self.assertRaisesRegex(Exception, "请从游戏主页进入"):
            ensure_main(task, loading_grace=20)
        self.assertLess(clock.t, 30 + 20 + 10)


if __name__ == "__main__":
    unittest.main()
