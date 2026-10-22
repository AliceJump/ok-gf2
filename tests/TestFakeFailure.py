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
methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_is_failure_page"]
consts = [
    n
    for n in tree.body
    if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "failure_page_re" for t in n.targets)
]
ns = {"re": re}
exec(compile(ast.Module(body=consts + methods, type_ignores=[]), str(source), "exec"), ns)
is_failure_page, failure_page_re = ns["_is_failure_page"], ns["failure_page_re"]


def make_task(texts):
    task = Mock()
    task.box = SimpleNamespace(bottom="bottom")
    task.wait_ocr.side_effect = lambda match=None, **kw: [SimpleNamespace(name=t) for t in texts if match.search(t)]
    return task


class FakeFailureTest(unittest.TestCase):
    def test_real_failure_page(self):
        # 实录 12.5 章 LZ-1-5 失败结算页
        self.assertTrue(is_failure_page(make_task(["重新挑战", "战斗重演(9)", "确认"])))

    def test_battle_effect_is_not_failure(self):
        # 实录 16.0 章：战斗中只有特效读出来的「任务失败_99」，底部是回合 / 自动按钮
        self.assertFalse(is_failure_page(make_task(["03/12 回合", "回收物品 1/2"])))

    def test_pattern(self):
        self.assertTrue(failure_page_re.search("重新挑战"))


if __name__ == "__main__":
    unittest.main()
