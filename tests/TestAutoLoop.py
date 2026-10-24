"""
实录 2026-10-23：50 级后主页左下角多了「自主循环」图标，点进去「开始循环」由游戏按队列完成调度室、体力本、竞技场；
没有图标（未解锁）就照手动流程。
"""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np

from src.tasks.daily import daily_public_mixin
from src.tasks.daily.daily_battle_mixin import DailyBattleMixin
from src.tasks.daily.daily_public_mixin import DailyPublicMixin, loop_covers, loop_item_name, white_ratio, yellow_ratio


def box(name):
    return SimpleNamespace(name=name)


def make_task(icon=True, page=True, screens=()):
    """screens：每次 next_frame 之后的 OCR 结果 {"full": [...], "center": [...]}；第一帧给看图标那次。"""
    task = Mock()
    task.config = {"自主循环": True}
    task.box = SimpleNamespace(bottom_left="bl", bottom="b", center="c", _claim="claim", left="l", top="t")
    task.frame = np.zeros((100, 100, 3), np.uint8)
    if icon:
        task.frame[90:95, 20:22] = 255
    task.box_of_screen.return_value = SimpleNamespace(x=19, y=86, width=4, height=7)
    task.has_auto_loop_icon = lambda: DailyPublicMixin.has_auto_loop_icon(task)
    task.read_loop_queue.return_value = {"调度室", "实兵演习"}
    task.wait_ocr.side_effect = lambda match=None, **kw: [box("开始循环")] if match == "开始循环" and page else []
    frames = iter(screens)
    current = {}

    def next_frame():
        current.clear()
        current.update(next(frames, {}))

    def ocr(match=None, box=None, **kw):
        names = current.get("center" if box == "c" else "full", [])
        found = [SimpleNamespace(name=n) for n in names]
        if match is None:
            return found
        if isinstance(match, list):
            return [b for b in found if b.name in match]
        return [b for b in found if match.search(b.name)]

    task.next_frame.side_effect = next_frame
    task.ocr.side_effect = ocr
    return task


class AutoLoopTest(unittest.TestCase):
    def setUp(self):
        self._timeout = daily_public_mixin.AUTO_LOOP_TIMEOUT
        daily_public_mixin.AUTO_LOOP_TIMEOUT = 2  # 帧用完后不会无限等

    def tearDown(self):
        daily_public_mixin.AUTO_LOOP_TIMEOUT = self._timeout

    def test_white_ratio(self):
        frame = np.zeros((10, 10, 3), np.uint8)
        frame[0:5] = 255
        self.assertAlmostEqual(white_ratio(frame, SimpleNamespace(x=0, y=0, width=10, height=10)), 0.5)

    def test_no_icon_falls_back_without_clicking(self):
        task = make_task(icon=False)
        self.assertFalse(DailyPublicMixin.auto_loop(task))
        task.click_relative.assert_not_called()

    def test_icon_but_no_page_falls_back(self):
        task = make_task(page=False)
        self.assertFalse(DailyPublicMixin.auto_loop(task))
        task.click_relative.assert_called_once()
        task.click.assert_not_called()

    def test_runs_until_loop_end(self):
        task = make_task(screens=[{}, {"center": ["是否开始循环", "确认"]}, {}, {"full": ["循环结束"]}])
        self.assertTrue(DailyPublicMixin.auto_loop(task))
        clicked = [c.args[0] for c in task.click.call_args_list]
        self.assertEqual(clicked[0][0].name, "开始循环")
        self.assertEqual(clicked[1][0].name, "确认")
        task.ensure_main.assert_called()

    def test_unsafe_dialog_not_confirmed(self):
        task = make_task(screens=[{}, {"center": ["是否消耗坍塌晶条", "确认", "取消"]}])
        self.assertFalse(DailyPublicMixin.auto_loop(task))
        self.assertEqual(len(task.click.call_args_list), 1)  # 只点了「开始循环」

    def test_loop_records_queue_only_when_finished(self):
        task = make_task(screens=[{}, {"full": ["循环结束"]}])
        self.assertTrue(DailyPublicMixin.auto_loop(task))
        self.assertEqual(task._auto_loop_items, {"调度室", "实兵演习"})
        task = make_task(screens=[{}, {"center": ["是否消耗坍塌晶条", "确认", "取消"]}])
        task._auto_loop_items = None
        self.assertFalse(DailyPublicMixin.auto_loop(task))
        self.assertIsNone(task._auto_loop_items)

    def test_yellow_badge_and_names(self):
        frame = np.zeros((10, 10, 3), np.uint8)
        frame[:, :5] = (0, 220, 255)  # BGR 亮黄
        self.assertAlmostEqual(yellow_ratio(frame, 0, 0, 10, 10), 0.5)
        self.assertEqual(loop_item_name("实兵演"), "实兵演习")
        self.assertEqual(loop_item_name("开始循环"), None)
        self.assertEqual(loop_item_name("20"), None)

    def test_loop_covers(self):
        task = SimpleNamespace(_auto_loop_items=None)
        self.assertFalse(loop_covers(task, "体力"))
        task._auto_loop_items = {"实兵演习"}
        self.assertTrue(loop_covers(task, "体力"))  # 体力默认被循环用掉
        self.assertTrue(loop_covers(task, "实兵演习"))
        self.assertFalse(loop_covers(task, "调度室"))
        self.assertFalse(loop_covers(Mock(), "体力"))  # 没跑过循环（Mock 属性不是集合）

    def test_gongongqu_skips_dispatch_only_when_queue_has_dispatch(self):
        for items, dispatched in (({"调度室"}, False), ({"实兵演习"}, True), (None, True)):
            task = Mock()
            task.config = {"自主循环": True}

            def run_loop(items=items, task=task):
                task._auto_loop_items = items
                return items is not None

            task.auto_loop.side_effect = run_loop
            task.box = SimpleNamespace(_claim="claim", left="l", top="t", bottom="b")
            task.wait_ocr.return_value = []
            DailyPublicMixin.gongongqu(task)
            self.assertEqual(task.wait_ocr.called, dispatched, items)

    def test_gongongqu_without_loop_config(self):
        task = Mock()
        task.config = {"自主循环": False}
        task.box = SimpleNamespace(_claim="claim", left="l", top="t", bottom="b")
        task.wait_ocr.return_value = []
        DailyPublicMixin.gongongqu(task)
        task.auto_loop.assert_not_called()

    def test_battle_and_arena_follow_loop_queue(self):
        task = Mock()
        task._auto_loop_items = {"实兵演习"}
        DailyBattleMixin.battle(task)  # 循环跑完：体力默认用掉
        DailyBattleMixin.arena(task)
        task.set_lineup_kind.assert_not_called()
        for method in (DailyBattleMixin.battle, DailyBattleMixin.arena):
            task = Mock()
            task._auto_loop_items = None  # 循环没跑完 / 没解锁
            task.wait_click_ocr.side_effect = StopIteration  # 进了正常流程就停
            with self.assertRaises(StopIteration):
                method(task)
            task.set_lineup_kind.assert_called_once()

    def test_guild_skips_only_covered_parts(self):
        task = Mock()
        task._auto_loop_items = {"每日要务", "班组奖励"}
        task.box = SimpleNamespace(_group="g", bottom_right="br")
        task.wait_ocr.return_value = [SimpleNamespace(name="班组")]
        task.chenyan.return_value = True
        DailyBattleMixin.guild(task)
        task.chenyan.assert_called_once()  # 尘烟前线没在列队里，照常打
        matches = [c.kwargs.get("match") for c in task.wait_click_ocr.call_args_list]
        self.assertNotIn(["要务"], matches)
        self.assertNotIn(["补给"], matches)


if __name__ == "__main__":
    unittest.main()
