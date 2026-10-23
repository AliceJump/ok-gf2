"""
部署界面空地格识别（support_select.find_deploy_tiles）：
实录 2026-10-20，竞技场部署图的地格内部比普通关卡暗（V 约 130），要能认出来，且空地格排在被挡住的前面。
用合成图测，不依赖真实截图。
"""

import unittest

import cv2
import numpy as np

from src.core import support_select as ss

W, H = 1280, 768


def _diamond_pts(cx, cy, kw=110, kh=84):
    return np.array([[cx, cy - kh // 2], [cx + kw // 2, cy], [cx, cy + kh // 2], [cx - kw // 2, cy]], np.int32)


def make_frame(tiles, bgr):
    """深色地板上画几个地格菱形；tiles = [(cx, cy, 被挡住的比例)]"""
    frame = np.full((H, W, 3), (30, 25, 28), np.uint8)
    for cx, cy, blocked in tiles:
        cv2.fillPoly(frame, [_diamond_pts(cx, cy)], bgr)
        if blocked:
            # 立绘挡住上半部分
            cv2.rectangle(frame, (cx - 40, cy - 60), (cx + 40, int(cy - 42 + blocked * 84)), (40, 40, 40), -1)
    return frame


class DeployTilesTest(unittest.TestCase):
    def assert_found(self, frame, expected):
        tiles = ss.find_deploy_tiles(frame, W, H)
        centers = [t["center"] for t in tiles]
        for cx, cy in expected:
            self.assertTrue(
                any(abs(x - cx) < 10 and abs(y - cy) < 10 for x, y in centers),
                f"没认出 ({cx},{cy})，认出的是 {centers}",
            )
        return tiles

    def test_bright_tiles_of_normal_stage(self):
        frame = make_frame([(300, 400, 0), (420, 400, 0)], (230, 120, 60))  # 亮蓝 V≈230
        self.assert_found(frame, [(300, 400), (420, 400)])

    def test_dark_tiles_of_arena(self):
        frame = make_frame([(300, 400, 0), (420, 400, 0), (540, 400, 0)], (130, 73, 51))  # 竞技场实测 BGR，V≈130
        tiles = self.assert_found(frame, [(300, 400), (420, 400), (540, 400)])
        self.assertTrue(all(t["fill"] >= ss.TILE_EMPTY_FILL for t in tiles[:3]), tiles)

    def test_blocked_tile_sorts_after_empty_ones(self):
        frame = make_frame([(300, 400, 0.5), (420, 400, 0)], (130, 73, 51))
        tiles = self.assert_found(frame, [(300, 400), (420, 400)])
        self.assertEqual(tiles[0]["center"][0], 420)
        self.assertLess(tiles[1]["fill"], tiles[0]["fill"])

    def test_floor_is_not_a_tile(self):
        frame = np.full((H, W, 3), (32, 23, 28), np.uint8)
        self.assertEqual(ss.find_deploy_tiles(frame, W, H), [])


if __name__ == "__main__":
    unittest.main()
