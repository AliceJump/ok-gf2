"""
实录 2026-10-20 BH-9-4（本关至少需要出击 4 人）：第 4 个空格被助战大机甲挡住一部分，菱形模板没认出来，
脚本把有人的格子当成唯一空格反复点，阵容停在 3/4，点作战开始只闪「本关至少需要出击4人!」。
补人时用宽松蓝色连通域兜底找空格；作战开始后认出这句提示就再补一次人，补不满就明确报错。
"""

import re
import unittest
from pathlib import Path

import cv2

from src.core import support_select as ss

FIX = Path(__file__).resolve().parents[1] / "tests/fixtures"


class HiddenTileTest(unittest.TestCase):
    def test_fallback_finds_tile_next_to_big_unit(self):
        frame = cv2.imread(str(FIX / "deploy_hidden_tile_1280x720.jpg"))
        known = [t["center"] for t in ss.find_deploy_tiles(frame, 1280, 720)]
        occupied = ss.unit_tiles_from_tags(ss.find_unit_tags(frame, 1280, 720), 720)
        extra = ss.fallback_empty_tiles(frame, 1280, 720, known, occupied)
        self.assertTrue(any(abs(x - 626) < 25 and abs(y - 560) < 25 for x, y in extra), extra)
        for x, y in extra:  # 不会和已知候选重复
            self.assertTrue(all((x - kx) ** 2 + (y - ky) ** 2 >= (0.03 * 720) ** 2 for kx, ky in known))

    def test_must_deploy_toast_text(self):
        source = (Path(__file__).resolve().parents[1] / "src/core/BaseGfTask.py").read_text(encoding="utf-8")
        pattern = re.search(r'must_deploy_re = re.compile\(r"([^"]+)"\)', source).group(1)
        self.assertTrue(re.search(pattern, "本关至少需要出击4人!"))
        self.assertIsNone(re.search(pattern, "还有可部署的单位，是否开始作战"))


if __name__ == "__main__":
    unittest.main()
