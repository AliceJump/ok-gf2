"""
每个任务开始前的隐藏步骤 ensure_game_started：
游戏没开 → 拉起 → 进主页；刚拉起 / 停在标题页 → 进主页；早就开着 → 不动。
只测流程，不依赖 ok 框架：把 BaseGfTask 里相关方法单独抠出来跑在 Mock 上。
"""

import ast
import functools
import re
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

source = Path(__file__).resolve().parents[1] / "src/core/BaseGfTask.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BaseGfTask")
wanted = ("ensure_game_started", "_game_process_age", "_on_title_screen")
methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_with_game_started"]
consts = [
    n
    for n in tree.body
    if isinstance(n, ast.Assign)
    and any(
        isinstance(t, ast.Name) and t.id in ("title_start_re", "GAME_LAUNCH_MAIN_TIMEOUT", "GAME_FRESH_SECONDS")
        for t in n.targets
    )
]


class TriggerTask:  # 顶替 ok.TriggerTask，只用来做 isinstance 判断
    pass


ns = {"re": re, "time": time, "functools": functools, "TriggerTask": TriggerTask}
exec(compile(ast.Module(body=consts + funcs + methods, type_ignores=[]), str(source), "exec"), ns)
ensure_game_started = ns["ensure_game_started"]
game_process_age = ns["_game_process_age"]
on_title_screen = ns["_on_title_screen"]
with_game_started = ns["_with_game_started"]
FRESH = ns["GAME_FRESH_SECONDS"]
MAIN_TIMEOUT = ns["GAME_LAUNCH_MAIN_TIMEOUT"]


def proc(age):
    p = Mock()
    p.create_time.return_value = time.time() - age
    return p


def make_task(procs, title=False):
    task = Mock()
    task.box = SimpleNamespace(bottom="bottom")
    task.skip_game_check = False  # Mock 的任意属性都是真值，要显式关掉
    task._game_processes.return_value = procs
    task._game_process_age.side_effect = lambda: game_process_age(task)
    task._on_title_screen.side_effect = lambda: on_title_screen(task)
    task.ocr.side_effect = lambda box=None, match=None, log=False, **kw: (
        [SimpleNamespace(name="点击开始")] if title and box == "bottom" and match.search("点击开始") else []
    )
    return task


class EnsureGameStartedTest(unittest.TestCase):
    def test_game_not_running_is_launched_then_enters_main(self):
        task = make_task([])
        self.assertTrue(ensure_game_started(task))
        task._relaunch_game.assert_called_once()
        task.ensure_main.assert_called_once_with(recheck_time=2, time_out=MAIN_TIMEOUT)

    def test_game_open_for_a_while_not_on_title_does_nothing(self):
        task = make_task([proc(FRESH + 600)])
        self.assertFalse(ensure_game_started(task))
        task._relaunch_game.assert_not_called()
        task.ensure_main.assert_not_called()
        task.ocr.assert_called()  # 看过一眼标题页

    def test_freshly_launched_game_enters_main_without_relaunch(self):
        task = make_task([proc(20)])
        self.assertFalse(ensure_game_started(task))
        task._relaunch_game.assert_not_called()
        task.ensure_main.assert_called_once_with(recheck_time=2, time_out=MAIN_TIMEOUT)

    def test_old_game_sitting_on_title_screen_enters_main(self):
        task = make_task([proc(FRESH + 600)], title=True)
        self.assertFalse(ensure_game_started(task))
        task._relaunch_game.assert_not_called()
        task.ensure_main.assert_called_once()

    def test_unreadable_create_time_counts_as_old(self):
        bad = Mock()
        bad.create_time.side_effect = OSError("gone")
        task = make_task([bad])
        self.assertFalse(ensure_game_started(task))
        task.ensure_main.assert_not_called()

    def test_trigger_task_is_skipped(self):
        class Monitor(TriggerTask):
            pass

        task = Monitor()
        task._game_processes = Mock()
        task.ensure_main = Mock()
        self.assertFalse(ensure_game_started(task))
        task._game_processes.assert_not_called()
        task.ensure_main.assert_not_called()

    def test_custom_timeout_is_passed_through(self):
        task = make_task([])
        ensure_game_started(task, time_out=30)
        task.ensure_main.assert_called_once_with(recheck_time=2, time_out=30)


class RunWrapperTest(unittest.TestCase):
    def test_wrapper_runs_ensure_before_task_body(self):
        order = []

        class FakeTask:
            def ensure_game_started(self):
                order.append("ensure")

            def run(self):
                order.append("run")
                return "done"

        FakeTask.run = with_game_started(FakeTask.run)
        self.assertEqual(FakeTask().run(), "done")
        self.assertEqual(order, ["ensure", "run"])
        self.assertTrue(FakeTask.run._ensures_game)
        self.assertEqual(FakeTask.run.__name__, "run")

    def test_wrapper_is_not_applied_twice(self):
        class FakeTask:
            def run(self):
                return 1

        once = with_game_started(FakeTask.run)
        self.assertTrue(getattr(once, "_ensures_game", False))


if __name__ == "__main__":
    unittest.main()
