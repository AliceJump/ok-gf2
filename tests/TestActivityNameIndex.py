"""多活动名称索引和入口失败的编排回归。"""

import unittest
from unittest.mock import Mock

from tests.TestActivityChapters import box, load_activity_logic


class ActivityNameIndexTest(unittest.TestCase):
    def run_activity_names(self, names, count):
        """入口失败仍检查后续活动，且不调用战斗。"""
        run = load_activity_logic()["DailyActivityMixin"].activity
        task = Mock()
        task.config = {"当前物资关卡名称": names}
        task.wait_ocr.return_value = list(range(count))
        task._select_activity_supply_entry.return_value = False
        result = run(task)
        task.fast_combat.assert_not_called()
        self.assertFalse(result)
        return [call.args[0] for call in task._select_activity_supply_entry.call_args_list]

    def test_multiple_activities_use_corresponding_names(self):
        self.assertEqual(["活动甲", "活动乙"], self.run_activity_names("活动甲-活动乙", 2))

    def test_extra_activities_reuse_last_name(self):
        self.assertEqual(["活动甲", "活动乙", "活动乙", "活动乙"], self.run_activity_names("活动甲-活动乙", 4))

    def test_single_name_can_cover_multiple_activities(self):
        self.assertEqual(["活动甲"] * 3, self.run_activity_names("活动甲", 3))

    def test_full_chapter_names_retain_corresponding_activity(self):
        self.assertEqual(["活动甲·转篇", "活动乙·终篇"], self.run_activity_names("活动甲·转篇-活动乙·终篇", 2))

    def flow_task(self):
        """成功进入指定篇章后的编排桩。"""
        task = Mock()
        task.config = {"当前物资关卡名称": "静默突触·转篇"}
        task._select_activity_supply_entry.return_value = True
        task.wait_ocr.side_effect = [["activity"], ["AF-2-5"]]
        task.wait_click_ocr.side_effect = [["limited"], ["supply"]]
        return task

    def test_missing_supply_button_does_not_start_battle(self):
        task = self.flow_task()
        task.wait_click_ocr.side_effect = [["limited"], []]
        self.assertFalse(load_activity_logic()["DailyActivityMixin"].activity(task))
        task.fast_combat.assert_not_called()
        self.assertEqual(1, task.wait_ocr.call_count)
        pattern = task.wait_click_ocr.call_args.kwargs["match"]
        self.assertIsNone(pattern.search("剧情100%物资100%"))

    def test_missing_stage_does_not_start_battle(self):
        task = self.flow_task()
        task.wait_ocr.side_effect = [["activity"], []]
        self.assertFalse(load_activity_logic()["DailyActivityMixin"].activity(task))
        task.fast_combat.assert_not_called()

    def test_confirmed_supply_stage_starts_battle_once(self):
        task = self.flow_task()
        task.fast_combat.return_value = True
        self.assertTrue(load_activity_logic()["DailyActivityMixin"].activity(task))
        task.fast_combat.assert_called_once_with(set_cost=1, battle_max=6, activity=True)
        self.assertEqual("AF-2-5", task.click.call_args.args[0])

    def test_failed_battle_is_reported_as_incomplete(self):
        task = self.flow_task()
        task.fast_combat.return_value = False
        self.assertFalse(load_activity_logic()["DailyActivityMixin"].activity(task))

    def test_small_supply_entry_runs_without_requiring_second_supply_button(self):
        """空配置小活动的真实入口 helper 与 activity 联动，不重复索要物资按钮。"""
        logic = load_activity_logic()["DailyActivityMixin"]
        for text in ("物资", "物资模式"):
            with self.subTest(text=text):
                task = self.flow_task()
                task.config = {"当前物资关卡名称": ""}
                entry = box(text)
                task._select_activity_supply_entry.side_effect = (
                    lambda value: logic._select_activity_supply_entry(task, value)
                )
                task.wait_ocr.side_effect = [["activity"], [], [entry], ["AF-1-5"]]
                task.wait_click_ocr.side_effect = [["limited"]]
                task.fast_combat.return_value = True
                self.assertTrue(logic.activity(task))
                task.wait_click_ocr.assert_called_once()
                task.fast_combat.assert_called_once_with(set_cost=1, battle_max=6, activity=True)
                self.assertIn(entry, [call.args[0] for call in task.click.call_args_list])
                self.assertEqual("AF-1-5", task.click.call_args.args[0])

    def test_small_campaign_entry_still_requires_supply_button(self):
        """活动战役只是中间入口，缺少物资按钮时不能开战。"""
        logic = load_activity_logic()["DailyActivityMixin"]
        task = self.flow_task()
        task.config = {"当前物资关卡名称": ""}
        task._select_activity_supply_entry.side_effect = (
            lambda value: logic._select_activity_supply_entry(task, value)
        )
        task.wait_ocr.side_effect = [["activity"], [], [box("活动战役")]]
        task.wait_click_ocr.side_effect = [["limited"], []]
        self.assertFalse(logic.activity(task))
        self.assertEqual(2, task.wait_click_ocr.call_count)
        task.fast_combat.assert_not_called()

    def test_locked_chapter_does_not_start_battle(self):
        """锁定提示与目标邻近时，整个活动流程不进入战斗。"""
        logic = load_activity_logic()["DailyActivityMixin"]
        task = self.flow_task()
        target = box("静默突触·转篇")
        task._select_activity_supply_entry.side_effect = (
            lambda value: logic._select_activity_supply_entry(task, value)
        )
        task.wait_ocr.side_effect = [["activity"]]
        task.wait_ocr_until_count.return_value = [target]
        task.ocr.return_value = [box("未开启")]
        task._filter_boxes_near_candidates.return_value = [target]
        self.assertFalse(logic.activity(task))
        task.fast_combat.assert_not_called()
        self.assertNotIn(target, [call.args[0] for call in task.click.call_args_list])
        task.wait_click_ocr.assert_called_once()

    def test_unresponsive_chapter_click_does_not_start_battle(self):
        """章节目录仍在时不能误刷默认篇章，即使物资按钮看起来可用。"""
        logic = load_activity_logic()["DailyActivityMixin"]
        task = self.flow_task()
        target = box("静默突触·转篇")
        task._select_activity_supply_entry.side_effect = (
            lambda value: logic._select_activity_supply_entry(task, value)
        )
        task.wait_ocr.side_effect = [["activity"], [target]]
        task.wait_ocr_until_count.return_value = [target]
        task.ocr.return_value = []
        self.assertFalse(logic.activity(task))
        task.fast_combat.assert_not_called()
        self.assertIn(target, [call.args[0] for call in task.click.call_args_list])
        task.wait_click_ocr.assert_called_once()
