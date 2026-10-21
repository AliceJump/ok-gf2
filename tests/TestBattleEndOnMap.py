"""
实录 2026-10-20：改成真实鼠标输入后，skip_dialogs 在等结算时的角落点击把「任务完成」结算页点过去了，
等到的直接是选关页面；而选关页面右上角是货币「+」，再点就弹「物品详情」。
战斗结束的判定要认选关页面，选关页面上不做角落点击，「物品详情」按弹窗 ESC 关掉。
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
methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "skip_dialogs"]
funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("battle_over_on_map", "describe_screen")]
consts = [
    n
    for n in tree.body
    if isinstance(n, ast.Assign)
    and any(
        isinstance(t, ast.Name)
        and t.id
        in (
            "pop_ups",
            "map_re",
            "stamina_popup_re",
            "battle_ui_re",
            "challenge_button_re",
            "nav_tabs_re",
            "chapter_select_re",
        )
        for t in n.targets
    )
]
ns = {"re": re, "time": __import__("time")}
exec(compile(ast.Module(body=consts + funcs + methods, type_ignores=[]), str(source), "exec"), ns)
battle_over_on_map, skip_dialogs, pop_ups, map_re = (
    ns["battle_over_on_map"],
    ns["skip_dialogs"],
    ns["pop_ups"],
    ns["map_re"],
)


def box(name):
    return SimpleNamespace(name=name)


def find_boxes(boxes, match=None, boundary=None):
    pats = match if isinstance(match, list) else [match]
    out = []
    for b in boxes:
        for p in pats:
            if p.search(b.name) if hasattr(p, "search") else p == b.name:
                out.append(b)
                break
    return out


class BattleOverTest(unittest.TestCase):
    def test_map_cards_mean_battle_is_over(self):
        self.assertTrue(battle_over_on_map([box("9-7"), box("BH-9-1")]))
        self.assertTrue(battle_over_on_map([box("确认"), box("SL-9-2")]))

    def test_result_pages_are_not_over(self):
        self.assertFalse(battle_over_on_map([box("任务完成")]))
        self.assertFalse(battle_over_on_map([box("继续前进")]))
        self.assertFalse(battle_over_on_map([]))
        self.assertFalse(battle_over_on_map(None))

    def test_item_detail_dialog_is_a_pop_up(self):
        self.assertIn("物品详情", pop_ups)


class ChapterSelectEndTest(unittest.TestCase):
    def test_chapter_select_page_means_battle_is_over(self):
        self.assertTrue(battle_over_on_map([box("章节进度"), box("确认")]))


class SkipDialogsOnMapTest(unittest.TestCase):
    def make_task(self, boxes):
        task = Mock()
        task.ocr.return_value = boxes
        task.find_boxes.side_effect = find_boxes
        task._is_loading_frame.return_value = False
        task._is_battle_frame.return_value = False
        task._dismiss_notice.return_value = False
        return task

    def test_no_corner_clicks_on_stage_select_page(self):
        task = self.make_task([box("9-7"), box("BH-9-1"), box("普通")])
        self.assertIsNone(
            skip_dialogs(task, end_match=["任务完成"], time_out=0.01, has_dialog=True, raise_if_not_found=False)
        )
        task.click_relative.assert_not_called()
        task.click.assert_not_called()

    def test_no_corner_clicks_on_navigation_pages(self):
        # 实录 2026-10-20：章节选择页 / 模拟作战页右上角是「模拟作战」页签，点了会跑进模拟作战
        for page in (
            [box("剧情战役"), box("往期活动"), box("Supply Missions"), box("模拟作战"), box("章节进度"), box("确认")],
            [box("剧情战役"), box("往期活动"), box("模拟作战"), box("心智勘测"), box("首领挑战"), box("实兵演习")],
        ):
            task = self.make_task(page)
            skip_dialogs(task, end_match=[map_re], time_out=0.01, has_dialog=True, raise_if_not_found=False)
            task.click_relative.assert_not_called()

    def test_unknown_page_still_gets_corner_clicks(self):
        task = self.make_task([box("……")])
        skip_dialogs(task, end_match=["任务完成"], time_out=0.01, has_dialog=True, raise_if_not_found=False)
        task.click_relative.assert_called()

    def test_loading_screen_extends_timeout(self):
        """实录 2026-10-21：回地图的「资源加载中 30%」比 time_out 还久，加载页要顺延超时，不能判卡住。"""
        start = ns["time"].time()
        loading = [box("11.008625-4431-226"), box("30%"), box("资源加载中")]
        task = self.make_task([])
        task.ocr.side_effect = lambda *a, **k: (
            loading if ns["time"].time() - start < 0.3 else [box("VS-1-10"), box("普通")]
        )
        task._is_loading_frame.side_effect = lambda boxes: boxes is loading
        task.sleep.side_effect = lambda s: ns["time"].sleep(0.02)
        result = skip_dialogs(task, end_match=[map_re], time_out=0.05, has_dialog=True, raise_if_not_found=True)
        self.assertEqual([b.name for b in result], ["VS-1-10"])
        task.click_relative.assert_not_called()

    def test_loading_grace_is_bounded(self):
        task = self.make_task([box("资源加载中"), box("30%")])
        task._is_loading_frame.return_value = True
        start = ns["time"].time()
        self.assertIsNone(
            skip_dialogs(
                task, end_match=[map_re], time_out=0.05, loading_grace=0.1, has_dialog=True, raise_if_not_found=False
            )
        )
        self.assertLess(ns["time"].time() - start, 1)

    def test_chapter_select_without_progress_text_ends_by_nav_tabs(self):
        """实录 2026-10-21 15.0 章：看完剧情落在章节选择页，「章节进度」没读到、只读到页签，不能干等到超时。"""
        page = [box("剧情战役"), box("の"), box("往期活动"), box("Supply Missions"), box("模拟作战")]
        task = self.make_task(page)
        end = [map_re, ns["chapter_select_re"], ns["nav_tabs_re"]]
        result = skip_dialogs(task, end_match=end, time_out=5, has_dialog=True, raise_if_not_found=True)
        self.assertIn("剧情战役", [b.name for b in result])
        task.click_relative.assert_not_called()

    def test_map_in_end_match_returns_map_boxes(self):
        task = self.make_task([box("9-7"), box("普通")])
        result = skip_dialogs(
            task, end_match=["任务完成", map_re], time_out=1, has_dialog=True, raise_if_not_found=False
        )
        self.assertEqual([b.name for b in result], ["9-7"])
        task.click_relative.assert_not_called()


if __name__ == "__main__":
    unittest.main()
