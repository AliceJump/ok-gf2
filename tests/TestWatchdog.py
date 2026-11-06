"""看门狗报警文案与调试截图的纯逻辑测试，不依赖设备与 ok-script 运行时。"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ok import Box

from src.core.BaseGfTask import describe_screen, watchdog_message
from src.core.debug_shot import save_debug_shot


class TestDebugShot(unittest.TestCase):
    def test_save_and_rotate(self):
        frame = np.zeros((72, 128, 3), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as root:
            paths = [
                save_debug_shot(frame, "推图", f"tag{i}", [Box(1, 1, 5, 5, name="n")], root=root, max_files=3)
                for i in range(5)
            ]
            self.assertTrue(all(p.endswith(".jpg") for p in paths))
            self.assertTrue(os.path.exists(paths[-1]))
            remaining = [f for _, _, files in os.walk(os.path.join(root, "推图")) for f in files]
            self.assertEqual(len(remaining), 3)
            self.assertFalse(os.path.exists(paths[0]))

    def test_none_frame(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(save_debug_shot(None, "推图", "x", root=root))


class TestWatchdog(unittest.TestCase):
    def test_message_distinguishes_pause_from_stall(self):
        # 实录：推图卡片的「暂停」按钮被点到，执行线程在 ok-script 的 sleep 里空转 6 分钟，界面上还显示「运行中」
        self.assertIn("任务已暂停", watchdog_message(360, False, True, "x"))
        self.assertIn("F9", watchdog_message(130, True, False, "x"))
        # 实录：游戏窗口被最小化时 ok-script 暂停执行器，恢复窗口后不会自己继续
        self.assertIn("最小化", watchdog_message(130, True, False, "x", window_hidden=True))
        self.assertNotIn("F9", watchdog_message(130, True, False, "x", window_hidden=True))
        self.assertIn(
            "卡在 TaskExecutor.py:385 sleep", watchdog_message(130, False, False, "TaskExecutor.py:385 sleep")
        )

    def test_describe_screen(self):
        self.assertEqual(describe_screen(["任务完成", "继续前进", "确认"]), "结算页")
        self.assertEqual(describe_screen(["部署人形", "4/4", "作战开始"]), "部署界面")
        self.assertEqual(describe_screen(["01/12 回合", "行动结束"]), "战斗中")
        self.assertEqual(describe_screen(["6-1", "SL-6-1", "挑战"]), "选关页面")
        self.assertEqual(describe_screen(["情报拼图补充", "继续前进"]), "体力弹窗")
        self.assertEqual(describe_screen(["随便什么"]), "未知页面")
