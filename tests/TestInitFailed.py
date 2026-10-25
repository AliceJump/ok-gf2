"""
拉起游戏后停在「用户中心初始化失败 请您稍后再试」+「重试」（实录 2026-10-22）：
is_main 认出提示框 → 点重试 → ensure_main 的超时顺延；连续点满上限后不再顺延。
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
methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_handle_init_failed"]
consts = [
    n
    for n in tree.body
    if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id in ("init_failed_re", "INIT_RETRY_EXTEND", "INIT_RETRY_MAX") for t in n.targets)
]
ns = {"re": re}
exec(compile(ast.Module(body=consts + methods, type_ignores=[]), str(source), "exec"), ns)
handle_init_failed = ns["_handle_init_failed"]
init_failed_re = ns["init_failed_re"]


def box(name):
    return SimpleNamespace(name=name)


def make_task(dialog=True, button=True):
    task = Mock()
    task.box = SimpleNamespace(center="center")
    task._init_retries = 0
    task._deadline_bump = 0

    box_ = globals()["box"]
    task.ocr.side_effect = lambda box=None, match=None, log=False, **kw: (
        [box_("用户中心初始化失败")]
        if box == "center" and dialog and match.search("用户中心初始化失败")
        else ([box_("重试")] if box is None and dialog and button and match.search("重试") else [])
    )
    return task


class InitFailedRegexTest(unittest.TestCase):
    def test_matches_real_dialog_text(self):
        self.assertTrue(init_failed_re.search("用户中心初始化失败"))
        self.assertTrue(init_failed_re.search("请您稍后再试"))

    def test_ignores_normal_screens(self):
        for text in ("点击开始", "请求服务器", "资源更新完毕，需要重新启动游戏", "重新开始战斗"):
            self.assertIsNone(init_failed_re.search(text), text)


class HandleInitFailedTest(unittest.TestCase):
    def test_no_dialog_does_nothing(self):
        task = make_task(dialog=False)
        self.assertFalse(handle_init_failed(task))
        task.click.assert_not_called()

    def test_dialog_without_button_does_nothing(self):
        task = make_task(button=False)
        self.assertFalse(handle_init_failed(task))
        task.click.assert_not_called()

    def test_clicks_retry_and_bumps_deadline(self):
        task = make_task()
        self.assertTrue(handle_init_failed(task))
        self.assertEqual(task.click.call_args.args[0][0].name, "重试")
        self.assertEqual(task._init_retries, 1)
        self.assertEqual(task._deadline_bump, ns["INIT_RETRY_EXTEND"])

    def test_stops_bumping_after_max_retries(self):
        task = make_task()
        task._init_retries = ns["INIT_RETRY_MAX"]
        self.assertTrue(handle_init_failed(task))
        task.click.assert_called_once()
        self.assertEqual(task._deadline_bump, 0)


if __name__ == "__main__":
    unittest.main()
