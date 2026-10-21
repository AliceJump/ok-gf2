"""
选关地图上关卡卡片的状态，直接看卡片本身（不点开面板）。

- 通关的卡片右上角有橙色圆形对勾角标（主线、支线、剧情点都有）；没通关的没有。
  这是「已通关」的正面证据。旧逻辑是点开面板、没读到「特殊奖励」就当已通关，面板动画慢一帧就会误判。
- 左下角「63/69」是本章勋章数，用来在推完一章后核对有没有漏（勋章只算战斗关的挑战目标，剧情点不算）。
"""

import re

import cv2
import numpy as np

# 对勾角标相对关卡名文字框：在文字框右端上方。实测 2560x1440：LA-1-17 文字框右端 x=642、顶 y=672，
# 角标中心 (667, 641)，直径约 36（0.025h）
BADGE_REGION = (-0.012, 0.03, -0.05, 0.005)  # (x0 相对右端, x1 相对右端) 按画面宽；(y0, y1) 相对顶端按画面高
BADGE_HSV = ((4, 150, 190), (20, 255, 255))
BADGE_SIZE = (0.014, 0.036)  # 角标外接框边长范围（画面高的比例）
BADGE_MIN_AREA = 0.35  # 橙色像素占外接框的比例下限（中间白色对勾不算）

MEDAL_BOX = (0.0, 0.85, 0.2, 0.95)  # 左下角「63/69」
medal_re = re.compile(r"(\d{1,3})\s*[/|]\s*(\d{1,3})")


def has_clear_badge(frame, box, width, height):
    """关卡名文字框 box 右上方有没有橙色对勾角标。"""
    if frame is None:
        return False
    right, top = box.x + box.width, box.y
    x0 = max(0, int(right + BADGE_REGION[0] * width))
    x1 = min(width, int(right + BADGE_REGION[1] * width))
    y0 = max(0, int(top + BADGE_REGION[2] * height))
    y1 = min(height, int(top + BADGE_REGION[3] * height))
    if x1 <= x0 or y1 <= y0:
        return False
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    lo, hi = BADGE_HSV
    mask = cv2.inRange(hsv, np.array(lo), np.array(hi))
    n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    smin, smax = BADGE_SIZE[0] * height, BADGE_SIZE[1] * height
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if smin <= w <= smax and smin <= h <= smax and area >= BADGE_MIN_AREA * w * h:
            return True
    return False


def parse_medals(texts):
    """左下角勋章计数「63/69」→ (63, 69)；读不到返回 None。"""
    for t in texts:
        if m := medal_re.search(t or ""):
            got, total = int(m.group(1)), int(m.group(2))
            if 0 < total <= 300 and got <= total:
                return got, total
    return None
