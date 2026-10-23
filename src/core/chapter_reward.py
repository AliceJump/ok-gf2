"""
章节收集奖励和心智回溯的画面常量与纯函数（实录 2026-10-22，2560x1440）。

- 主线章节、往期活动每个页签的地图左下角：奖励图标 +「36/48」收集数 +「可领取」（领完是「章节奖励已全部领取」）。
  点开是「收集数」弹窗，三档奖励每档右边是「领取」/ 绿勾（已领）/「未完成」（星数不够：有关卡没推或没三星）。
- 往期活动「剧情」页签左边（第 8 期起）有「心智回溯 13%」卡片，点开是一列剧情：「已归档 / 可观看 / 观看前置剧情以解锁」，
  每条 30 抽卡资源；点行右边的播放按钮进剧情，「全部跳过」也算看完，弹「获得道具」。
- 往期活动列表上还有奖励没领的活动，卡片右上角有个橙色「!」。
"""

import re

import cv2

REWARD_LABEL_BOX = (0.0, 0.86, 0.2, 1.0)  # 左下角「36/48 / 可领取」
claim_label_re = re.compile(r"可\s*领\s*取")
REWARD_POPUP_BOX = (0.19, 0.22, 0.8, 0.76)  # 「收集数」弹窗
popup_title_re = re.compile(r"收\s*集\s*数")
claim_button_re = re.compile(r"^\s*领\s*取\s*$")
unfinished_re = re.compile(r"^\s*未\s*完\s*成\s*$")
got_items_re = re.compile(r"^获\s*得\s*道\s*具$")
close_hint_re = re.compile(r"(?:空\s*白\s*)?处\s*关\s*闭$")

MIND_CARD_BOX = (0.0, 0.3, 0.16, 0.62)  # 活动地图左边的「心智回溯 13%」卡片
mind_card_re = re.compile(r"心\s*智\s*回\s*溯")
percent_re = re.compile(r"(\d{1,3})\s*%")
MIND_LIST_BOX = (0.36, 0.0, 1.0, 1.0)  # 心智回溯的剧情列表在右边
playable_re = re.compile(r"可\s*观\s*看")
mind_row_re = re.compile(r"可\s*观\s*看|已\s*归\s*档|前\s*置\s*剧\s*情")
MIND_PLAY_X = 0.94  # 行右边播放按钮的 x，和「可观看」文字同一高度
MIND_LIST_DRAG = (0.68, 0.8, 0.68, 0.2)  # 往下翻列表（一屏约 5 行，共 8 行左右）
story_skip_all_re = re.compile(r"全\s*部\s*跳\s*过")

# 活动列表卡片右上角的橙色「!」：直径约 0.009 画面宽，中心统一在 0.235 画面高，比卡片下方活动名中心靠右 0.089 画面宽
EVENT_BADGE_Y = (0.20, 0.27)
EVENT_BADGE_DX = 0.089
EVENT_BADGE_TOL = 0.03
BADGE_HSV = ((5, 150, 180), (22, 255, 255))
BADGE_AREA = (4e-5, 3e-4)  # 色块面积占全画面的比例范围（2560x1440 实测约 376 像素）


def mind_replay_percent(boxes):
    """心智回溯卡片：(卡片框, 百分比)；百分比读不到是 None，没有卡片返回 None。"""
    card = next((b for b in boxes if mind_card_re.search(b.name or "")), None)
    if card is None:
        return None
    nums = [int(m.group(1)) for b in boxes if (m := percent_re.search(b.name or "")) and int(m.group(1)) <= 100]
    return card, (nums[0] if nums else None)


def event_badges(frame, width, height):
    """活动列表上橙色「!」的中心 x 列表。"""
    if frame is None:
        return []
    y0, y1 = int(EVENT_BADGE_Y[0] * height), int(EVENT_BADGE_Y[1] * height)
    hsv = cv2.cvtColor(frame[y0:y1], cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, BADGE_HSV[0], BADGE_HSV[1])
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask)
    lo, hi = BADGE_AREA[0] * width * height, BADGE_AREA[1] * width * height
    out = []
    for i in range(1, n):
        w, h, area = stats[i][2], stats[i][3], stats[i][4]
        if lo <= area <= hi and 0.6 <= w / max(h, 1) <= 1.6:
            out.append(float(cents[i][0]))
    return sorted(out)


def card_has_badge(title, badges, width):
    """活动名框对应的卡片右上角有没有「!」。"""
    x = title.x + title.width / 2 + EVENT_BADGE_DX * width
    return any(abs(x - b) <= EVENT_BADGE_TOL * width for b in badges)
