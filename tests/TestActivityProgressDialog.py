"""Replay progress labels from the 2560x1600 daily log without a game window."""

import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

source = Path(__file__).resolve().parents[1] / "src/tasks/daily/daily_activity_mixin.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
method = next(
    n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_dismiss_activity_progress_dialog"
)
namespace = {"re": re}
exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace)
dismiss = namespace["_dismiss_activity_progress_dialog"]


class ProgressDialogTest(unittest.TestCase):
    """区分总览文字与真实奖励清单，覆盖返回键关闭结果。"""

    def task(self, modal=False, blocked=False):
        """建立返回后露出总览、或关闭受阻的有限页面模型。"""
        overview = ["逸趣事件", "宜居值", "工栽培", "逸趣导算进度", "今日逸趣值", "茶歇一刻"]
        task = SimpleNamespace(labels=["逸趣导算进度", "奖励清单"] if modal else overview, backs=0)
        task.box_of_screen = lambda *args: args
        task.wait_ocr = lambda match, **kwargs: [s for s in task.labels if match.search(s)]
        task.log_warning = lambda *args: None

        def back(**kwargs):
            """记录返回次数，关闭成功时恢复仍包含进度标题的总览。"""
            task.backs += 1
            if not blocked:
                task.labels = overview

        task.back = back
        return task

    def test_overview_progress_label_does_not_close_panel(self):
        """总览的共有进度标题不能触发返回键。"""
        task = self.task()
        self.assertTrue(dismiss(task))
        self.assertEqual(0, task.backs)
        self.assertIn("工栽培", task.labels)

    def test_dialog_closes_even_when_overview_still_has_progress_label(self):
        """清单消失即确认关闭，不受总览上残留标题影响。"""
        task = self.task(modal=True)
        self.assertTrue(dismiss(task))
        self.assertEqual(1, task.backs)
        self.assertIn("逸趣导算进度", task.labels)

    def test_blocked_dialog_remains_uncertain(self):
        """清单未消失时停止导航并保留待核查结果。"""
        task = self.task(modal=True, blocked=True)
        self.assertFalse(dismiss(task))
        self.assertEqual(1, task.backs)

    def test_blank_frame_never_sends_back(self):
        """空白识别结果不授权返回，避免关掉未知页面。"""
        task = self.task()
        task.labels = []
        self.assertTrue(dismiss(task))
        self.assertEqual(0, task.backs)
