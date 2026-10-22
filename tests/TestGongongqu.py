"""
实录 2026-10-22：公共区委托页等调度室按钮的循环不取新帧，一直看点「委托」之前的主页旧帧，
10 秒后「停留过久，返回」，调度室资源没领、也没再次派遣。
"""

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from src.tasks.daily.daily_public_mixin import DailyPublicMixin


class GongongquTest(unittest.TestCase):
    def test_buttons_found_once_page_frame_arrives(self):
        task = Mock()
        task.config = {"自主循环": False}
        task.box = SimpleNamespace(_claim="claim", left="left", top="top", bottom="bottom")
        frames = {"n": 0}
        task.next_frame.side_effect = lambda: frames.update(n=frames["n"] + 1)
        buttons = [SimpleNamespace(name="b0"), SimpleNamespace(name="b1")]
        # 前两帧还是主页（没按钮），第三帧委托页出来
        task.find_feature.side_effect = lambda **kw: buttons if frames["n"] >= 3 else []
        entrust = SimpleNamespace(name="委托")
        task.wait_ocr.side_effect = lambda match=None, **kw: (
            [entrust] if getattr(match, "pattern", None) == "委托" else []
        )
        DailyPublicMixin.gongongqu(task)
        self.assertGreaterEqual(task.next_frame.call_count, 3)
        clicked = [c.args[0] for c in task.click.call_args_list if c.args]
        self.assertIn(buttons[0], clicked)
        self.assertIn(buttons[1], clicked)
        self.assertFalse(any("停留过久" in str(c) for c in task.log_info.call_args_list))


if __name__ == "__main__":
    unittest.main()
