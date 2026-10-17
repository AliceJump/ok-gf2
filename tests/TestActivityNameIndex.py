import ast
import re
import unittest
from pathlib import Path
from unittest.mock import Mock


class ActivityNameIndexTest(unittest.TestCase):
    def run_activity_names(self, names, count):
        source = Path("src/tasks/daily/daily_activity_mixin.py")
        tree = ast.parse(source.read_text(encoding="utf-8"))
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "activity")
        namespace = {"re": re, "chapter_suffix_re": r"(?:上|中|下|初|转)篇"}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
        task = Mock()
        task.config = {"当前物资关卡名称": names}
        task.wait_ocr.side_effect = [list(range(count))] + [[]] * count
        task.wait_ocr_until_count.return_value = []
        namespace["activity"](task)
        task.fast_combat.assert_not_called()
        return [call.kwargs["match"][0].pattern for call in task.wait_ocr_until_count.call_args_list]

    def test_multiple_activities_use_corresponding_names(self):
        patterns = self.run_activity_names("活动甲-活动乙", 2)
        self.assertEqual(["活动甲", "活动乙"], [pattern.split("[")[0] for pattern in patterns])

    def test_extra_activities_reuse_last_name(self):
        patterns = self.run_activity_names("活动甲-活动乙", 4)
        self.assertEqual(["活动甲", "活动乙", "活动乙", "活动乙"], [p.split("[")[0] for p in patterns])

    def test_single_name_can_cover_multiple_activities(self):
        patterns = self.run_activity_names("活动甲", 3)
        self.assertEqual(["活动甲"] * 3, [p.split("[")[0] for p in patterns])
