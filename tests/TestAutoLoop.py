"""用独立游戏状态与虚拟时钟复现自主循环的延迟启动和长战斗。"""

import re
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from src.tasks.daily.daily_public_mixin import DailyPublicMixin
from src.tasks.DailyTaskRunner import DailyTaskRunner


class LoopScreen(DailyPublicMixin):
    def __init__(self, *, duration=900, start_delay=3.5, confirm=False, config=None, blocked=None, hide_start=False):
        self.config = {"公共区/调度室": True, "自主循环": True, "购买免费礼包": True, **(config or {})}
        self.box = SimpleNamespace(
            _claim="claim", left="left", top="top", center="center", bottom="bottom", bottom_left="bottom_left"
        )
        self.now = 0.0
        self.duration = duration
        self.start_delay = start_delay
        self.confirm = confirm
        self.hide_start = hide_start
        self.blocked = blocked
        self.page = "public"
        self.start_at = None
        self.started_at = None
        self.infos = {}
        self.screenshots = []
        self.shop_visits = 0
        self.start_clicks = 0
        self.home_during_loop = 0

    def sleep(self, seconds):
        self.now += seconds
        self._update()

    def next_frame(self):
        self.sleep(0.1)

    def _update(self):
        if self.start_at is not None and self.now >= self.start_at and self.started_at is None:
            self.started_at = self.start_at
            self.page = "running"
        if self.started_at is not None and self.page == "running" and self.now >= self.started_at + self.duration:
            self.page = "ended"

    def ocr(self, *, match, box=None, **kwargs):
        self._update()
        labels = {
            "public": ["委托", "自主循环"],
            "menu": ["开始循环"],
            "confirm": ["开始循环", "确认"],
            "running": ["循环进行中—"],
            "ended": ["循环结束"],
            "settlement": ["确认"],
        }.get(self.page, [])
        # 确认按钮位于中心，不能用底部框误读。
        if self.page == "confirm" and box == "bottom_left":
            labels = ["开始循环"]
        patterns = match if isinstance(match, list) else [match]
        return [
            SimpleNamespace(name=label)
            for label in labels
            if any(
                pattern.search(label) if isinstance(pattern, re.Pattern) else pattern == label for pattern in patterns
            )
        ]

    def wait_ocr(self, *, match, time_out=5, box=None, **kwargs):
        deadline = self.now + time_out
        while True:
            if found := self.ocr(match=match, box=box):
                return found
            if self.now >= deadline:
                return None
            self.sleep(min(0.5, deadline - self.now))

    def wait_click_ocr(self, *, match, time_out=5, box=None, after_sleep=0, **kwargs):
        if not (found := self.wait_ocr(match=match, time_out=time_out, box=box)):
            return None
        label = found[0].name
        if label != self.blocked:
            if label == "自主循环":
                self.page = "menu"
            elif label == "开始循环":
                self.start_clicks += 1
                if self.confirm:
                    self.page = "confirm"
                else:
                    self.start_at = self.now + self.start_delay
                    if self.hide_start:
                        self.page = "loading"
            elif label == "确认" and self.page == "confirm":
                self.page = "loading"
                self.start_at = self.now + self.start_delay
            elif label == "循环结束":
                self.page = "settlement"
            elif label == "确认" and self.page == "settlement":
                self.page = "public"
        self.sleep(after_sleep)
        return found

    def find_feature(self, **kwargs):
        return [object(), object()]

    def click_box_by_match_position(self, *args, **kwargs):
        pass

    def click(self, *args, **kwargs):
        pass

    def wait_pop_up(self, **kwargs):
        pass

    def back(self, **kwargs):
        pass

    def info_set(self, key, value):
        self.infos[key] = value

    def log_info(self, *args, **kwargs):
        pass

    def tr(self, text):
        return text

    def screenshot(self, name):
        self.screenshots.append(name)

    def ensure_main(self, **kwargs):
        if self.page in {"running", "loading", "menu", "confirm", "settlement", "ended"}:
            self.home_during_loop += 1
            raise RuntimeError("请从游戏主页进入")

    def shopping(self):
        self.shop_visits += 1


class AutoLoopTest(unittest.TestCase):
    def run_daily(self, task):
        runner = DailyTaskRunner(task, [("公共区/调度室", task.gongongqu), ("购买免费礼包", task.shopping)])
        with patch("src.tasks.daily.daily_public_mixin.time.time", side_effect=lambda: task.now):
            runner.run()
        return runner

    def test_delayed_start_is_accepted_without_reclicking_missing_start_button(self):
        task = LoopScreen(duration=15)
        runner = self.run_daily(task)
        self.assertEqual("完成", runner.final_summary["status"])
        self.assertEqual(1, task.start_clicks)
        self.assertEqual(1, task.shop_visits)
        self.assertEqual(0, task.home_during_loop)

    def test_confirmed_start_waits_for_end_before_next_task(self):
        task = LoopScreen(duration=15, confirm=True, start_delay=0)
        runner = self.run_daily(task)
        self.assertEqual("完成", runner.final_summary["status"])
        self.assertGreaterEqual(task.now, task.started_at + 15)
        self.assertEqual(1, task.shop_visits)

    def test_start_button_disappearing_waits_for_loading_without_confirmation(self):
        task = LoopScreen(duration=15, start_delay=10, hide_start=True)
        self.run_daily(task)
        self.assertEqual(1, task.start_clicks)
        self.assertEqual(1, task.shop_visits)
        self.assertGreaterEqual(task.now, task.started_at + 15)

    def test_long_battle_can_finish_after_ten_minutes(self):
        task = LoopScreen(start_delay=0)
        self.run_daily(task)
        self.assertGreaterEqual(task.now, task.started_at + 900)
        self.assertEqual(1, task.shop_visits)

    def test_wait_limit_can_be_extended_per_config(self):
        task = LoopScreen(duration=4000, start_delay=0, config={"自主循环等待上限（分钟）": 120})
        self.run_daily(task)
        self.assertEqual(1, task.shop_visits)

    def test_loop_ending_during_start_transition_is_still_settled(self):
        task = LoopScreen(duration=0, start_delay=0)
        self.run_daily(task)
        self.assertEqual("public", task.page)
        self.assertEqual(1, task.shop_visits)

    def test_disabled_auto_loop_does_not_start_battle(self):
        task = LoopScreen(config={"自主循环": False})
        self.run_daily(task)
        self.assertEqual(0, task.start_clicks)
        self.assertEqual(1, task.shop_visits)

    def test_timeout_is_attributed_to_public_area_without_home_navigation(self):
        task = LoopScreen(duration=10000, start_delay=0, config={"自主循环等待上限（分钟）": 1})
        runner = DailyTaskRunner(task, [("公共区/调度室", task.gongongqu), ("购买免费礼包", task.shopping)])
        with (
            patch("src.tasks.daily.daily_public_mixin.time.time", side_effect=lambda: task.now),
            self.assertRaisesRegex(TimeoutError, "自主循环"),
        ):
            runner.run()
        self.assertEqual("公共区/调度室", runner.final_summary["current_task"])
        self.assertEqual(0, task.shop_visits)
        self.assertEqual(0, task.home_during_loop)
        self.assertEqual("running", task.page)
        self.assertLess(task.now, 90)

    def test_failed_start_stops_before_shop_and_records_public_area(self):
        task = LoopScreen(blocked="开始循环")
        with self.assertRaisesRegex(RuntimeError, "自主循环"):
            self.run_daily(task)
        self.assertEqual(0, task.shop_visits)
        self.assertEqual(0, task.home_during_loop)

    def test_failed_entry_stops_before_starting_battle(self):
        task = LoopScreen(blocked="自主循环")
        with self.assertRaisesRegex(RuntimeError, "自主循环入口"):
            self.run_daily(task)
        self.assertEqual(0, task.start_clicks)
        self.assertEqual(0, task.home_during_loop)

    def test_failed_start_confirmation_stops_before_next_task(self):
        task = LoopScreen(confirm=True, blocked="确认")
        with self.assertRaisesRegex(RuntimeError, "自主循环启动确认"):
            self.run_daily(task)
        self.assertIsNone(task.started_at)
        self.assertEqual(0, task.home_during_loop)

    def test_failed_settlement_does_not_advance_to_shop(self):
        task = LoopScreen(duration=15, start_delay=0, blocked="确认")
        with self.assertRaisesRegex(RuntimeError, "自主循环"):
            self.run_daily(task)
        self.assertEqual(0, task.home_during_loop)
        self.assertEqual(0, task.shop_visits)

    def test_invalid_limit_fails_before_starting_loop(self):
        for value in (0, -1, 241, "invalid", None):
            with self.subTest(value=value):
                task = LoopScreen(config={"自主循环等待上限（分钟）": value})
                with self.assertRaisesRegex(ValueError, "自主循环"):
                    self.run_daily(task)
                self.assertEqual(0, task.start_clicks)
