"""一键日常单项识别：吃饭「已有 xx 生效中」弹窗、尘烟前哨战编队名与助战战力的纯逻辑测试。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestOutpostPresetName(unittest.TestCase):
    def test_name_match(self):
        from src.tasks.daily.daily_battle_mixin import DailyBattleMixin

        m = DailyBattleMixin._outpost_name_match
        self.assertTrue(m("编队1", "编队1"))
        self.assertTrue(m("编 队1", "编队1"))
        self.assertFalse(m("编队10", "编队1"))
        self.assertFalse(m("编队", "编队1"))
        self.assertFalse(m("编队2", "编队1"))
        self.assertTrue(m("尘烟", "尘烟队"))
        self.assertTrue(m("I尘烟队", "尘烟队"))

    def test_support_power_ocr(self):
        from ok import Box

        from src.tasks.daily.daily_battle_mixin import power_of, support_power_re

        # 实录：班组助战弹窗 OCR 结果
        names = ["海鲜羊", "可露凯", "6", "心25850", "心24871", "LV.60", "V.60", "心18925", "25718"]
        hits = [n for n in names if support_power_re.match(n)]
        self.assertEqual(hits, ["心25850", "心24871", "心18925", "25718"])
        self.assertEqual(power_of(Box(0, 0, 1, 1, name="心25850")), 25850)


class TestFoodAlreadyActive(unittest.TestCase):
    def test_dialog_text_variants(self):
        from src.tasks.daily.daily_activity_mixin import food_active_re

        # 实录弹窗：当前已有 章鱼小丸子 生效中，是否确认更换?（菜名橙色，OCR 可能拆开）
        for text in ["当前已有章鱼小丸子生效中，是否确认更换?", "生效中，是否确认更换?", "是否确认更换"]:
            self.assertIsNotNone(food_active_re.search(text), text)
        for text in ["确认邀请", "下一步", "制作", "取消", "今日不再提示", "当前已有"]:
            self.assertIsNone(food_active_re.search(text), text)
