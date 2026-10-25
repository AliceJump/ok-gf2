"""Chenyan task -> installed interaction -> foreground helper, with a fake desktop."""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np

from src.core.gf_interaction import GfInteraction
from src.patches.input_safety_patch import install_input_safety_patch
from src.tasks.daily.daily_activity_mixin import DailyActivityMixin
from src.tasks.daily.daily_battle_mixin import DailyBattleMixin
from tests import TestForegroundScroll as desktop_tests


class ChenyanScrollTest(unittest.TestCase):
    def setUp(self):
        self.desktop = desktop_tests.ForegroundScrollTest()
        self.desktop.setUp()
        self.addCleanup(self.desktop.doCleanups)
        self.desktop.gui.GetClientRect.return_value = (0, 0, 3840, 2160)
        self.desktop.gui.ClientToScreen.side_effect = lambda hwnd, point: point
        self.assertTrue(install_input_safety_patch())
        backend = object.__new__(GfInteraction)
        backend.hwnd_window = SimpleNamespace(hwnd=10)
        backend.session_mouse_enabled = Mock(return_value=True)
        self.task = SimpleNamespace(
            width=3840,
            height=2160,
            executor=SimpleNamespace(paused=False, interaction=backend),
            is_adb=Mock(return_value=False),
            sleep=Mock(),
            swipe_relative=Mock(),
            log_info=Mock(),
        )
        self.task._scroll_chenyan_list = lambda count: DailyBattleMixin._scroll_chenyan_list(self.task, count)

    def assert_restored(self):
        self.assertEqual(self.desktop.focus, 20)
        self.assertEqual(self.desktop.cursor, (900, 700))

    def test_down_uses_assist_coordinates_and_restores(self):
        self.assertTrue(self.task._scroll_chenyan_list(1))
        self.assertEqual(
            [event for event in self.desktop.events if event[0] == "wheel"], [("wheel", 10, (2496, 1296), -120)] * 3
        )
        self.assert_restored()

    def test_up_uses_positive_wheel_and_restores(self):
        self.assertTrue(self.task._scroll_chenyan_list(-1))
        self.assertEqual(
            [event for event in self.desktop.events if event[0] == "wheel"], [("wheel", 10, (2496, 1296), 120)] * 3
        )
        self.assert_restored()

    def test_assist_coordinates_scale_with_client_size(self):
        for width, height in ((1920, 1080), (2560, 1440), (3840, 2160)):
            with self.subTest(size=(width, height)):
                self.task.width, self.task.height = width, height
                self.desktop.gui.GetClientRect.return_value = (0, 0, width, height)
                self.desktop.events.clear()
                self.assertTrue(self.task._scroll_chenyan_list(1))
                wheels = [event for event in self.desktop.events if event[0] == "wheel"]
                self.assertEqual(wheels, [("wheel", 10, (int(width * 0.65), int(height * 0.60)), -120)] * 3)
                self.assert_restored()

    def test_pause_does_not_send_input(self):
        self.task.executor.paused = True
        self.assertFalse(self.task._scroll_chenyan_list(1))
        self.assertEqual(self.desktop.events, [])

    def test_wheel_error_restores_and_reaches_daily_error_handler(self):
        self.desktop.api.mouse_event.side_effect = RuntimeError("wheel failed")
        with self.assertRaisesRegex(RuntimeError, "wheel failed"):
            self.task._scroll_chenyan_list(1)
        self.assert_restored()

    def test_search_finds_next_page_after_foreground_scroll(self):
        target = SimpleNamespace(name="春田", x=1800, y=900)
        self.task.ocr = Mock(side_effect=[[], [target]])
        self.task._chenyan_list_snapshot = Mock(return_value=np.zeros((144, 256, 3), dtype=np.uint8))
        self.assertIs(DailyBattleMixin._find_chenyan_assist(self.task, "春田"), target)
        self.assertEqual(self.desktop.api.mouse_event.call_count, 3)
        self.assertEqual(self.task.ocr.call_count, 2)
        self.assert_restored()

    def test_unchanged_list_stops_instead_of_scrolling_forever(self):
        self.task.ocr = Mock(return_value=[])
        self.task._chenyan_list_snapshot = Mock(return_value=np.zeros((144, 256, 3), dtype=np.uint8))
        self.assertIsNone(DailyBattleMixin._find_chenyan_assist(self.task, "春田"))
        self.assertEqual(self.desktop.api.mouse_event.call_count, 3)
        self.assertEqual(self.task.ocr.call_count, 2)
        self.assert_restored()

    def test_adb_keeps_swipe_without_touching_desktop(self):
        self.task.is_adb.return_value = True
        self.assertTrue(self.task._scroll_chenyan_list(1))
        self.task.swipe_relative.assert_called_once_with(0.65, 0.72, 0.65, 0.40, duration=0.3)
        self.assertEqual(self.desktop.events, [])


class SupplyScrollTest(unittest.TestCase):
    setUp = ChenyanScrollTest.setUp
    assert_restored = ChenyanScrollTest.assert_restored

    def test_adb_supply_swipes_in_wheel_direction_without_desktop_input(self):
        self.task.is_adb.return_value = True
        for count, start, end in ((-3, 0.72, 0.40), (3, 0.40, 0.72)):
            with self.subTest(count=count):
                self.task.swipe_relative.reset_mock()
                DailyActivityMixin._scroll_supply_menu(self.task, count)
                self.task.swipe_relative.assert_called_once_with(0.12, start, 0.12, end, duration=0.3)
                self.assertEqual(self.desktop.events, [])
                self.assert_restored()

    def test_adb_supply_reset_reaches_top_from_multiple_pages(self):
        self.task.is_adb.return_value = True
        page = [8]

        def swipe(x1, y1, x2, y2, **kwargs):
            page[0] = max(0, page[0] - 1) if y2 > y1 else page[0] + 1

        self.task.swipe_relative.side_effect = swipe
        DailyActivityMixin._scroll_supply_menu(self.task, 30)
        self.assertEqual(page[0], 0)
        self.assertEqual(self.task.swipe_relative.call_count, 10)
        self.assertEqual(self.desktop.events, [])
        self.assertEqual(self.task.sleep.call_args.args, (0.6,))

    def test_supply_scroll_uses_sidebar_coordinates_and_restores(self):
        DailyActivityMixin._scroll_supply_menu(self.task, -3)
        self.assertEqual(
            [event for event in self.desktop.events if event[0] == "wheel"],
            [("wheel", 10, (460, 1296), -120)] * 3,
        )
        self.assert_restored()

    def test_supply_wheel_error_restores_and_propagates(self):
        self.desktop.api.mouse_event.side_effect = RuntimeError("wheel failed")
        with self.assertRaisesRegex(RuntimeError, "wheel failed"):
            DailyActivityMixin._scroll_supply_menu(self.task, -3)
        self.assert_restored()

    def test_sidebar_coordinates_scale_with_client_size(self):
        for width, height in ((1920, 1080), (2560, 1440), (3840, 2160)):
            with self.subTest(size=(width, height)):
                self.task.width, self.task.height = width, height
                self.desktop.gui.GetClientRect.return_value = (0, 0, width, height)
                self.desktop.events.clear()
                DailyActivityMixin._scroll_supply_menu(self.task, -3)
                wheels = [event for event in self.desktop.events if event[0] == "wheel"]
                self.assertEqual(wheels, [("wheel", 10, (int(width * 0.12), int(height * 0.60)), -120)] * 3)
                self.assert_restored()


if __name__ == "__main__":
    unittest.main(verbosity=2)
