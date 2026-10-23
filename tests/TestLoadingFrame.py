"""加载页识别（资源加载中 / 艾莫号移动中）的纯逻辑测试。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ok import Box

from src.core.BaseGfTask import BaseGfTask


class TestLoadingFrame(unittest.TestCase):
    """_is_loading_frame 只依赖 OCR 结果，直接用未绑定方法测。"""

    def setUp(self):
        from src.core.BaseGfTask import BaseGfTask

        self.is_loading = BaseGfTask._is_loading_frame

    def boxes(self, *names):
        return [Box(0, 0, 1, 1, name=n) for n in names]

    def test_loading_screens(self):
        self.assertTrue(self.is_loading(None, []))
        self.assertTrue(
            self.is_loading(None, self.boxes("18%", "资源加载中", "//.008625", "罗联污染区勘测维护及环境分析情报组"))
        )
        self.assertTrue(self.is_loading(None, self.boxes("42%")))

    def test_tutorial_popup_is_not_loading(self):
        self.assertFalse(
            self.is_loading(
                None,
                self.boxes(
                    "60%", "25%", "60%", "20%", "显示此次伤害的具体信息，包括稳态减伤、掩体减伤、降防率以及暴击率。"
                ),
            )
        )

    def test_battle_ui_is_not_loading(self):
        self.assertFalse(self.is_loading(None, self.boxes("01/12 回合", "击杀所有敌方单位 5/8", "行动结束", "115%")))


class TestElmoLoadingFrame(unittest.TestCase):
    # 之前这个类和上面的 TestLoadingFrame 重名，把它的用例盖掉了（Ran 34 而不是 37）
    def test_elmo_transition_is_loading(self):
        # 实录：离开活动层的「艾莫号」过场有一大段介绍文字，之前因为文字多于 3 条被当成非加载页
        names = ["艾莫号是指挥官所拥有的陆地行动单元，结构复杂", "NOW LOADING.", "移动中...69%", "ELMO", "TIME"]
        boxes = [Box(10, 10 + i * 30, 100, 20, name=n) for i, n in enumerate(names)]
        self.assertTrue(BaseGfTask._is_loading_frame(None, boxes))
        self.assertTrue(BaseGfTask._is_loading_frame(None, [Box(0, 0, 10, 10, name="资源加载中")]))
        self.assertTrue(BaseGfTask._is_loading_frame(None, []))
        tutorial = [Box(0, 0, 10, 10, name=n) for n in ["60%", "25%", "伤害", "关闭", "技能说明"]]
        self.assertFalse(BaseGfTask._is_loading_frame(None, tutorial))
