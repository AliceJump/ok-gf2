"""
战斗中途红色特效被 OCR 读成「任务失败」（实录 2026-10-21 16.0 章英雄难度 HZ-1-4，其实这关后来打赢了）：
只有底部同时有「重新挑战 / 战斗重演」才算真的失败结算页。
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
methods = [
    n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ("_is_failure_page", "_close_failure_page")
]
consts = [
    n
    for n in tree.body
    if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "failure_page_re" for t in n.targets)
]
ns = {"re": re}
exec(compile(ast.Module(body=consts + methods, type_ignores=[]), str(source), "exec"), ns)
is_failure_page, failure_page_re = ns["_is_failure_page"], ns["failure_page_re"]
close_failure_page = ns["_close_failure_page"]


def make_task(texts):
    task = Mock()
    task.box = SimpleNamespace(bottom="bottom")
    task.wait_ocr.side_effect = lambda match=None, **kw: [SimpleNamespace(name=t) for t in texts if match.search(t)]
    task._is_failure_page.side_effect = lambda: is_failure_page(task)
    return task


class FakeFailureTest(unittest.TestCase):
    def test_real_failure_page(self):
        # 实录 12.5 章 LZ-1-5 失败结算页
        self.assertTrue(is_failure_page(make_task(["重新挑战", "战斗重演(9)", "确认"])))

    def test_battle_effect_is_not_failure(self):
        # 实录 16.0 章：战斗中只有特效读出来的「任务失败_99」，底部是回合 / 自动按钮
        self.assertFalse(is_failure_page(make_task(["03/12 回合", "回收物品 1/2"])))

    def test_failure_page_closed_with_confirm(self):
        """实录 2026-11-03 极限峰值：结算页淡入时只认到「任务失败」，点标题关不掉；还在失败结算页就点底部「确认」。"""
        task = make_task(["任务失败", "我方单位全部损毁", "重新挑战", "战斗重演(9)", "确认"])
        close_failure_page(task)
        self.assertEqual("^确认$", task.wait_click_ocr.call_args.kwargs["match"].pattern)
        self.assertEqual("bottom", task.wait_click_ocr.call_args.kwargs["box"])

    def test_closed_failure_page_not_clicked_again(self):
        """已经点过「确认」回到了关卡页，就别再找「确认」。"""
        task = make_task(["激化阶群·子群1", "开始作战"])
        close_failure_page(task)
        task.wait_click_ocr.assert_not_called()

    def test_pattern(self):
        self.assertTrue(failure_page_re.search("重新挑战"))


if __name__ == "__main__":
    unittest.main()
