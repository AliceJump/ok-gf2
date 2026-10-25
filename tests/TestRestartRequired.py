"""
游戏启动后弹「资源更新完毕，需要重新启动游戏」（实录 2026-10-20）：
is_main 认出提示框 → 点确认 → 等游戏退出 → 重新拉起 → ensure_main 的超时从重启后重新计时。
只测流程，不依赖 ok 框架：把 BaseGfTask 里相关方法单独抠出来跑在 Mock 上。
"""

import ast
import re
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

source = Path(__file__).resolve().parents[1] / "src/core/BaseGfTask.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BaseGfTask")
wanted = ("_handle_restart_required", "_wait_game_exit", "ensure_main")
methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
consts = [
    n
    for n in tree.body
    if isinstance(n, ast.Assign)
    and any(
        isinstance(t, ast.Name) and t.id in ("restart_required_re", "GAME_RESTART_TITLE_TIMEOUT", "GAME_EXIT_TIMEOUT")
        for t in n.targets
    )
]
ns = {"re": re, "time": time}
exec(compile(ast.Module(body=consts + methods, type_ignores=[]), str(source), "exec"), ns)
handle_restart = ns["_handle_restart_required"]
wait_game_exit = ns["_wait_game_exit"]
ensure_main = ns["ensure_main"]
restart_required_re = ns["restart_required_re"]


def box(name):
    return SimpleNamespace(name=name)


class RestartRequiredRegexTest(unittest.TestCase):
    def test_matches_real_dialog_text(self):
        self.assertTrue(restart_required_re.search("资源更新完毕，需要重新启动游戏"))
        self.assertTrue(restart_required_re.search("需要重启游戏"))

    def test_ignores_normal_screens(self):
        for text in ("点击开始", "是否离开活动层", "本期扩编实练已结束", "重新开始战斗"):
            self.assertIsNone(restart_required_re.search(text), text)


class HandleRestartRequiredTest(unittest.TestCase):
    def make_task(self, dialog=True, exits=True):
        task = Mock()
        task.box = SimpleNamespace(center="center", bottom="bottom")

        def ocr(box=None, match=None, log=False, **kw):
            if box == "center":
                return (
                    [box_("资源更新完毕，需要重新启动游戏")]
                    if dialog and match.search("资源更新完毕，需要重新启动游戏")
                    else []
                )
            if box == "bottom" and dialog:
                return [box_("确认")] if match.search("确认") else []
            return []

        box_ = box
        task.ocr.side_effect = ocr
        task._wait_game_exit.return_value = exits
        task._game_processes.return_value = [] if exits else [task.proc]
        return task

    def test_no_dialog_does_nothing(self):
        task = self.make_task(dialog=False)
        self.assertFalse(handle_restart(task))
        task.click.assert_not_called()
        task._relaunch_game.assert_not_called()

    def test_dialog_confirm_then_relaunch_and_bump_deadline(self):
        task = self.make_task()
        self.assertTrue(handle_restart(task))
        self.assertEqual(task.click.call_args.args[0][0].name, "确认")
        task._wait_game_exit.assert_called_once_with(ns["GAME_EXIT_TIMEOUT"])
        task.proc.kill.assert_not_called()
        task._relaunch_game.assert_called_once()
        self.assertEqual(task._deadline_bump, ns["GAME_RESTART_TITLE_TIMEOUT"])

    def test_game_not_exiting_gets_killed(self):
        task = self.make_task(exits=False)
        self.assertTrue(handle_restart(task))
        task.proc.kill.assert_called_once()
        self.assertEqual(task._wait_game_exit.call_args_list, [call(ns["GAME_EXIT_TIMEOUT"]), call(10)])
        task._relaunch_game.assert_called_once()


class WaitGameExitTest(unittest.TestCase):
    def test_returns_as_soon_as_process_gone(self):
        task = Mock()
        task._game_processes.side_effect = [[1], [1], []]
        self.assertTrue(wait_game_exit(task, 5))
        self.assertEqual(task.sleep.call_count, 2)

    def test_timeout_when_process_stays(self):
        task = Mock()
        task._game_processes.return_value = [1]
        task.sleep.side_effect = lambda s: None
        start = time.time()
        self.assertFalse(wait_game_exit(task, 0.01))
        self.assertLess(time.time() - start, 2)


class EnsureMainDeadlineBumpTest(unittest.TestCase):
    def test_restart_bumps_deadline_instead_of_timing_out(self):
        """超时 1 秒的 ensure_main：第一轮 is_main 重启了游戏并要求顺延，第三轮才回到主页，不应抛「请从游戏主页进入」。"""
        task = Mock()
        calls = {"n": 0}

        def is_main(recheck_time=1, esc=True):
            calls["n"] += 1
            if calls["n"] == 1:
                task._deadline_bump = 100
                return False
            if calls["n"] == 2:
                time.sleep(1.2)  # 原超时（1 秒）已经过了
                return False
            return True

        task.is_main.side_effect = is_main
        task.sleep.side_effect = lambda s: None
        self.assertTrue(ensure_main(task, time_out=1, loading_grace=0))
        self.assertEqual(calls["n"], 3)
        self.assertEqual(task._deadline_bump, 0)
        task.debug_shot.assert_not_called()

    def test_without_bump_still_times_out(self):
        task = Mock()
        task.is_main.return_value = False
        task.ocr.return_value = [box("别的页面")]
        task._is_loading_frame.return_value = False
        task.sleep.side_effect = lambda s: time.sleep(s)
        with self.assertRaises(Exception):
            ensure_main(task, recheck_time=0.1, time_out=0.1, loading_grace=0)


if __name__ == "__main__":
    unittest.main()
