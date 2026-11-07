"""活动物资章节选择回归；只执行 AST 提取的逻辑，不连接游戏设备。"""

import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


def load_activity_logic():
    """加载真实模块常量和方法，隔离 Windows/ok-script 运行时依赖。"""
    source = Path("src/tasks/daily/daily_activity_mixin.py")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, (ast.Assign, ast.FunctionDef, ast.ClassDef))]
    namespace = {"re": re, "map_re": re.compile(r"[A-Z]+-\d+-\d+")}
    common = ast.parse(Path("src/tasks/daily/daily_common_mixin.py").read_text(encoding="utf-8"))
    constants = [node for node in common.body if isinstance(node, ast.Assign)]
    exec(compile(ast.Module(body=constants, type_ignores=[]), "common_constants", "exec"), namespace)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)
    return namespace


def box(name, x=100, y=900):
    """构造带位置的 OCR 框。"""
    return SimpleNamespace(name=name, x=x, y=y, width=100, height=30)


def matches(pattern, name):
    """模拟 OCR 的字符串精确匹配和正则 search 语义。"""
    patterns = pattern if isinstance(pattern, (list, tuple)) else [pattern]
    return any(item.search(name) if hasattr(item, "search") else item == name for item in patterns)


class ActivityChaptersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.logic = load_activity_logic()

    def task(self, screen, nearby=None, click_works=True):
        """仅 OCR/点击为桩；选择流程执行真实方法。"""
        task = self.logic["DailyActivityMixin"]()
        task.box = SimpleNamespace(bottom="bottom", bottom_right="bottom_right")
        task.width, task.height = 1920, 1080
        screen = list(screen)

        def click(target, **kwargs):
            if click_works and re.search(r"[上下中初承转终]\s*[篇筒]\s*$", target.name):
                screen[:] = [b for b in screen if not re.search(r"[上下中初承转终]\s*[篇筒]\s*$", b.name)]

        task.click = Mock(side_effect=click)
        task.log_warning = Mock()
        task.log_info = Mock()
        task.info_set = Mock()
        task.sleep = Mock()
        task.wait_ocr = Mock(side_effect=lambda match, **kwargs: [b for b in screen if matches(match, b.name)])
        task.ocr = task.wait_ocr
        task.wait_ocr_until_count = task.wait_ocr
        task._filter_boxes_near_candidates = Mock(side_effect=lambda chapters, candidates: nearby or [])
        return task

    def test_full_name_and_separator_variants(self):
        parse = self.logic["parse_activity_target"]
        for value in ("静默突触·转篇", " 静默突触 · 转篇 ", "静默突触・转篇", "静默突触：转篇", "静默突触:转篇"):
            with self.subTest(value=value):
                self.assertEqual(("静默突触", "转篇"), parse(value))

    def test_legacy_plain_name_and_empty_config(self):
        parse = self.logic["parse_activity_target"]
        self.assertEqual(("静默突触", None), parse("静默突触"))
        self.assertEqual(("", None), parse("  "))

    def test_chapter_without_activity_name_is_rejected(self):
        with self.assertRaises(ValueError):
            self.logic["parse_activity_target"]("转篇")

    def test_explicit_chapter_clicks_only_requested_tab(self):
        target = box("静默突触·转篇", x=1300)
        task = self.task([box("静默突触·初篇"), target, box("物资")])
        self.assertTrue(task._select_activity_supply_entry("静默突触 · 转篇"))
        self.assertEqual([target], [call.args[0] for call in task.click.call_args_list])

    def test_missing_explicit_chapter_never_falls_back(self):
        task = self.task([box("静默突触·初篇"), box("物资"), box("活动战役")])
        self.assertFalse(task._select_activity_supply_entry("静默突触·转篇"))
        task.click.assert_not_called()

    def test_explicit_chapter_does_not_match_different_activity(self):
        task = self.task([box("其他静默突触·转篇"), box("物资")])
        self.assertFalse(task._select_activity_supply_entry("静默突触·转篇"))
        task.click.assert_not_called()

    def test_new_chapter_names_are_supported(self):
        for chapter in ("承篇", "终篇"):
            with self.subTest(chapter=chapter):
                target = box("静默突触·" + chapter)
                task = self.task([target])
                self.assertTrue(task._select_activity_supply_entry("静默突触·" + chapter))
                task.click.assert_called_once()

    def test_automatic_mode_clicks_unique_supply_chapter_once(self):
        first, target = box("静默突触·初篇"), box("静默突触·转篇", x=1300)
        task = self.task([first, target, box("物资", x=1300)], nearby=[target])
        self.assertTrue(task._select_activity_supply_entry("静默突触"))
        self.assertEqual([target], [call.args[0] for call in task.click.call_args_list])

    def test_ambiguous_automatic_chapters_are_not_clicked_in_sequence(self):
        chapters = [box("静默突触·初篇"), box("静默突触·转篇", x=1300)]
        for nearby in ([], chapters):
            with self.subTest(nearby=bool(nearby)):
                task = self.task([*chapters, box("物资")], nearby=nearby)
                self.assertFalse(task._select_activity_supply_entry("静默突触"))
                task.click.assert_not_called()

    def test_single_chapter_remains_usable(self):
        target = box("静默突触·初篇")
        task = self.task([target])
        self.assertTrue(task._select_activity_supply_entry("静默突触"))
        task.click.assert_called_once()

    def test_progress_text_is_not_a_small_activity_entry(self):
        task = self.task([box("剧情100%物资100%")])
        self.assertFalse(task._select_activity_supply_entry(""))
        task.click.assert_not_called()

    def test_small_activity_with_empty_config_preserves_fallback(self):
        for text in ("活动战役", "物资", "物资模式"):
            with self.subTest(text=text):
                task = self.task([box(text)])
                self.assertTrue(task._select_activity_supply_entry(""))
                task.click.assert_called_once()

    def test_visible_unmatched_chapters_forbid_small_activity_fallback(self):
        task = self.task([box("其他活动·初篇"), box("物资")])
        self.assertFalse(task._select_activity_supply_entry("静默突触"))
        task.click.assert_not_called()

    def test_ocr_spaces_missing_separator_and_common_misread(self):
        for text in ("静 默 突 触 · 转 篇", "静默突触转篇", "静默突触·转筒"):
            with self.subTest(text=text):
                task = self.task([box(text)])
                self.assertTrue(task._select_activity_supply_entry("静默突触·转篇"))
                task.click.assert_called_once()

    def test_duplicate_explicit_targets_fail_closed(self):
        task = self.task([box("静默突触·转篇"), box("静默突触·转篇", x=1300)])
        self.assertFalse(task._select_activity_supply_entry("静默突触·转篇"))
        task.click.assert_not_called()

    def test_empty_configuration_does_not_choose_arbitrary_large_activity(self):
        task = self.task([box("静默突触·初篇"), box("物资")])
        self.assertFalse(task._select_activity_supply_entry(""))
        task.click.assert_not_called()

    def test_invalid_chapter_only_configuration_never_clicks(self):
        task = self.task([box("静默突触·转篇"), box("物资")])
        self.assertFalse(task._select_activity_supply_entry("转篇"))
        task.click.assert_not_called()

    def test_locked_target_is_not_clicked(self):
        target = box("静默突触·转篇")
        task = self.task([target, box("未开放")], nearby=[target])
        self.assertFalse(task._select_activity_supply_entry("静默突触·转篇"))
        task.click.assert_not_called()

    def test_unresponsive_chapter_click_is_not_confirmed(self):
        task = self.task([box("静默突触·转篇"), box("物资")], click_works=False)
        self.assertFalse(task._select_activity_supply_entry("静默突触·转篇"))
        task.click.assert_called_once()
