"""
回主页（BaseGfTask.is_main）遇到剧情对话：右上角「自动 / 跳过 / 全部跳过」时交给 skip_dialogs 跳过剧情。
实录 2026-10-21：停掉推图时正好在放下一章的开场剧情，接着跑一键日常，回主页 90 秒超时报「请从游戏主页进入」。
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
methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "is_main"]
consts = [
    n
    for n in tree.body
    if isinstance(n, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id in ("story_skip_re", "main_marks") for t in n.targets)
]
ns = {"re": re, "fL": Mock()}
exec(compile(ast.Module(body=consts + methods, type_ignores=[]), str(source), "exec"), ns)
is_main = ns["is_main"]


def box(name):
    return SimpleNamespace(name=name)


def make_task(right=(), top_right=()):
    task = Mock()
    task.box = SimpleNamespace(
        top_right="top_right", center="center", bottom="bottom", bottom_left="bl", bottom_right="br"
    )
    task.find_one.return_value = None
    task._handle_restart_required.return_value = False
    task._handle_init_failed.return_value = False
    task._confirm_battle_result.return_value = False

    def ocr(*a, box=None, match=None, **kw):
        if box == "right":
            return list(right)
        if box == "top_right" and match is ns["story_skip_re"]:
            return [b for b in top_right if match.search(b.name)]
        return []

    task.ocr.side_effect = ocr
    return task


class MainStoryTest(unittest.TestCase):
    def test_story_dialog_is_skipped(self):
        task = make_task(top_right=[box("自动跳过"), box("全部跳过")])
        self.assertFalse(is_main(task, esc=True))
        task.skip_dialogs.assert_called_once()
        task.back.assert_not_called()

    def test_main_page_is_not_touched(self):
        task = make_task(right=[box("整备室"), box("公共区")])
        self.assertTrue(is_main(task))
        task.skip_dialogs.assert_not_called()

    def test_other_pages_do_not_trigger_story_skip(self):
        task = make_task(top_right=[box("130/240"), box("33908")])
        is_main(task, esc=True)
        task.skip_dialogs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
