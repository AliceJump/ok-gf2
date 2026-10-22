"""
实录 2026-10-22 NZ-1-1：1 号单位站在最下面一排，地格被「作战开始」按钮盖住。整理阵容时按标签往下推的点
(1151,1291) 落进按钮，点下去直接开战，脚本还在找作战开始，10 秒后报错停了。地图上的点击都要避开这个按钮。
"""

import unittest
from pathlib import Path

import cv2

from src.core import support_select as ss

FIX = Path(__file__).resolve().parents[1] / "tests/fixtures"
W, H = 1280, 720


class StartButtonGuardTest(unittest.TestCase):
    def test_unit_behind_start_button_is_clicked_above_it(self):
        frame = cv2.imread(str(FIX / "deploy_unit_behind_start_1280x720.jpg"))
        tags = ss.find_unit_tags(frame, W, H)
        raw = ss.unit_tiles_from_tags(tags, H)
        self.assertTrue(any(ss.in_start_button(p, W, H) for p in raw), raw)  # 旧算法会点进按钮
        tiles = ss.unit_tiles_from_tags(tags, H, W)
        self.assertEqual(len(tags), len(tiles))
        self.assertFalse(any(ss.in_start_button(p, W, H) for p in tiles), tiles)
        low = max(tiles, key=lambda p: p[1])
        tag = next(t for t in tags if t[0] == low[0])
        self.assertGreater(low[1], tag[1])  # 还是点在标签下面的人形身上

    def test_tag_inside_button_is_dropped(self):
        self.assertEqual([], ss.unit_tiles_from_tags([(0.5 * W, 0.86 * H, 0.9)], H, W))

    def test_points_outside_button_unchanged(self):
        tags = [(0.2 * W, 0.7 * H, 0.9), (0.5 * W, 0.5 * H, 0.9)]
        self.assertEqual(ss.unit_tiles_from_tags(tags, H), ss.unit_tiles_from_tags(tags, H, W))

    def test_button_region_matches_screen(self):
        self.assertTrue(ss.in_start_button((0.5 * W, 0.91 * H), W, H))  # 作战开始中心
        self.assertTrue(ss.in_start_button((0.368 * W, 0.91 * H), W, H))  # 左边切换按钮
        self.assertFalse(ss.in_start_button((0.5 * W, 0.8 * H), W, H))
        self.assertFalse(ss.in_start_button((0.7 * W, 0.91 * H), W, H))


if __name__ == "__main__":
    unittest.main()
