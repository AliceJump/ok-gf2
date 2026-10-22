"""
部署界面的纯逻辑：卡片定位、椎数角标识别、已上场勾选判断、空地格查找。
坐标按 1280x768 实测，偏移统一用画面宽高的比例表达，换分辨率后仍成立。
"""

import os
import re

import cv2
import numpy as np

power_re = re.compile(r"^\d{3,6}$")  # 卡片下方的作战效能
digit_re = re.compile(r"^\d$")  # 地图上已上场单位头顶的编号

# 右侧面板的位置（画面比例）
PANEL_BOX = (0.75, 0.15, 0.995, 0.86)  # 卡片区域
NAME_BOX = (0.05, 0.80, 0.24, 0.90)  # 点中卡片后左下角的人形名字
BUTTON_BOX = (0.74, 0.88, 0.99, 0.995)  # 右下角「部署人形 / 撤回人形」
TAB_BOX = (0.74, 0.0, 0.95, 0.09)  # 「我的人形 / 好友助战」页签（没有助战的关卡只有「可部署人形」）
COUNT_BOX = (0.35, 0.0, 0.65, 0.09)  # 顶部「部署人形 3/4」
MAP_BOX = (0.0, 0.08, 0.72, 0.86)  # 地图区域（排除右侧面板和底部按钮）
# 属性筛选图标：页签中心往下 0.052 画面高，x 按顺序 全部/物理/燃烧/电导/冷凝
FILTER_DY = 0.052
FILTER_X = {"全部": 0.791, "物理": 0.828, "燃烧": 0.867, "电导": 0.906, "冷凝": 0.945}
# 卡片中心相对战力数字中心：往上 0.065 画面高
CARD_DY = -0.065
# 已上场的橙色勾相对战力数字中心：右 0.023 画面宽、上 0.105 画面高
CHECK_DX, CHECK_DY = 0.023, -0.105
# 椎数角标（蓝色小圆）中心相对战力数字中心
BADGE_DX, BADGE_DY = -0.0242, -0.0814
BADGE_WIN = 13  # 角标搜索窗半径，1280x768 下的像素
BADGE_DIGIT_R = 5.5  # 只看圆内这个半径里的白色像素
BADGE_SIZE = 13  # 模板尺寸
BADGE_MIN_IOU = 0.6
# 模板比对时数字笔画的亮度下限：先按原来的 215，比不上再放宽到 170
# （实录 2026-10-21：本机桌面 1280x768 下好友助战第一行角标数字只有 ~200 亮，6/4 都读成 None，助战没选上）
BADGE_WHITES = (215, 170)
BADGE_DIR = os.path.join("assets", "support_badges")
# 蓝圈颜色 (S 下限, V 下限)：先按 1280x768 实测的亮蓝找，找不到再放宽
# （实录 2026-10-20：RDP 会话 2560x1440 下蓝圈是暗青色，V 只有 120~160）
BADGE_DISK_COLORS = ((25, 170), (60, 100))
BADGE_OCR_WHITE = 170  # OCR 前二值化：三通道都高于它算数字笔画
BADGE_OCR_MIN_CONF = 0.5

_badge_templates = None


def _center(box):
    return box.x + box.width / 2, box.y + box.height / 2


def find_cards(boxes, width, height, badge_of=None):
    """
    由 OCR 结果找出卡片：每个战力数字代表一张卡片。
    :param badge_of: 可选，输入战力 box 返回椎数（int / None）
    :return: [{"power": int, "badge": int | None, "center": (x, y), "power_box": box}, ...] 按战力从高到低
    """
    cards = []
    for p in boxes:
        if not power_re.match(p.name):
            continue
        px, py = _center(p)
        badge = badge_of(p) if badge_of else None
        cards.append({"power": int(p.name), "badge": badge, "center": (px, py + CARD_DY * height), "power_box": p})
    cards.sort(key=lambda c: -c["power"])
    return cards


# 「强制出战」字样在战力数字正上方（1280x768 实测：字中心比战力中心高 22px）
forced_re = re.compile(r"强\s*制|制\s*出\s*战")


def mark_forced(cards, labels, width, height):
    """把「强制出战」字样对到它正下方的卡片上：card["forced"] = True。返回被标记的卡片。"""
    out = []
    for c in cards:
        px, py = _center(c["power_box"])
        c["forced"] = any(
            abs(_center(b)[0] - px) < 0.03 * width and -0.05 * height < _center(b)[1] - py < -0.005 * height
            for b in labels
        )
        if c["forced"]:
            out.append(c)
    return out


def check_point(card, width, height):
    """卡片右上角橙色勾的采样点。"""
    px, py = _center(card["power_box"])
    return int(px + CHECK_DX * width), int(py + CHECK_DY * height)


def is_orange_check(frame, x, y, radius=5, ratio=0.4):
    """采样点周围是否主要是橙色（已上场的勾）。frame 为 BGR。"""
    if frame is None:
        return False
    h, w = frame.shape[:2]
    x0, x1 = max(0, x - radius), min(w, x + radius + 1)
    y0, y1 = max(0, y - radius), min(h, y + radius + 1)
    if x0 >= x1 or y0 >= y1:
        return False
    patch = frame[y0:y1, x0:x1].astype(int)
    b, g, r = patch[..., 0], patch[..., 1], patch[..., 2]
    orange = (r > 180) & (g > 90) & (g < 215) & (b < 110) & (r - b > 110)
    return float(orange.mean()) >= ratio


MY_TAB_FILTER_DY = 0.0625  # 「我的人形」页签多一行「使用整备室配置」，筛选图标整体下移


def filter_point(tab_box, attr, width, height, my_tab=False):
    """属性筛选图标的点击位置；属性不在表里就点「全部」。my_tab=True 表示在「我的人形」页签。"""
    _, ty = _center(tab_box)
    dy = FILTER_DY + (MY_TAB_FILTER_DY if my_tab else 0)
    return FILTER_X.get(attr, FILTER_X["全部"]) * width, ty + dy * height


def pick_candidates(cards, min_badge):
    """椎数达标的卡片，保持战力从高到低。"""
    return [c for c in cards if c["badge"] is not None and c["badge"] >= min_badge]


# ------------------------------------------------------------------ 椎数角标
def load_badge_templates(folder=BADGE_DIR):
    """读取 assets/support_badges/*.png（13x13 二值图），文件名 dash 代表没椎（0）。"""
    global _badge_templates
    if _badge_templates is None:
        templates = {}
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                stem, ext = os.path.splitext(name)
                if ext.lower() != ".png":
                    continue
                img = cv2.imread(os.path.join(folder, name), cv2.IMREAD_GRAYSCALE)
                if img is None or img.shape != (BADGE_SIZE, BADGE_SIZE):
                    continue
                templates[0 if stem == "dash" else int(stem)] = img > 127
        _badge_templates = templates
    return _badge_templates


def find_badge_disk(frame, x, y, scale=1.0):
    """在 (x, y) 附近找蓝色小圆，返回圆心 (cx, cy)；找不到返回 None。"""
    r = int(round(BADGE_WIN * scale))
    h, w = frame.shape[:2]
    x0, y0 = max(0, int(x) - r), max(0, int(y) - r)
    win = frame[y0 : min(h, int(y) + r), x0 : min(w, int(x) + r)]
    if win.size == 0:
        return None
    hsv = cv2.cvtColor(win, cv2.COLOR_BGR2HSV)
    lo, hi = 9 * scale, 18 * scale
    for s_min, v_min in BADGE_DISK_COLORS:
        blue = ((hsv[..., 0] > 85) & (hsv[..., 0] < 110) & (hsv[..., 1] > s_min) & (hsv[..., 2] > v_min)).astype(
            np.uint8
        )
        blue = cv2.morphologyEx(blue, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        n, _, stats, cents = cv2.connectedComponentsWithStats(blue)
        best = None
        for i in range(1, n):
            area = stats[i, cv2.CC_STAT_AREA]
            bw, bh = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
            if not (60 * scale * scale <= area <= 260 * scale * scale and lo <= bw <= hi and lo <= bh <= hi):
                continue
            cx, cy = cents[i]
            d = (x0 + cx - x) ** 2 + (y0 + cy - y) ** 2
            if best is None or d < best[0]:
                best = (d, x0 + cx, y0 + cy)
        if best is not None:
            return best[1], best[2]
    return None


def badge_digit_mask(frame, cx, cy, scale=1.0, dx=0.0, dy=0.0, white=215):
    """圆内的白色像素，重采样成 13x13 二值图。"""
    r = BADGE_SIZE // 2
    out = np.zeros((BADGE_SIZE, BADGE_SIZE), bool)
    h, w = frame.shape[:2]
    for oy in range(BADGE_SIZE):
        for ox in range(BADGE_SIZE):
            if (ox - r) ** 2 + (oy - r) ** 2 > BADGE_DIGIT_R**2:
                continue
            px = int(round(cx + (dx + ox - r) * scale))
            py = int(round(cy + (dy + oy - r) * scale))
            if 0 <= py < h and 0 <= px < w and frame[py, px].min() > white:
                out[oy, ox] = True
    return out


def _iou(a, b):
    return float((a & b).sum() / max(1, (a | b).sum()))


def badge_ocr_image(frame, cx, cy, scale=1.0):
    """蓝圈裁出来、白字二值化成黑字白底、放大加边，给 OCR 只做识别（不做检测）。"""
    r = int(round(7 * scale))  # 只要圈里，不要圈外的立绘
    h, w = frame.shape[:2]
    crop = frame[max(0, int(cy) - r) : min(h, int(cy) + r), max(0, int(cx) - r) : min(w, int(cx) + r)]
    if crop.size == 0:
        return None
    ink = np.where(crop.min(axis=2) > BADGE_OCR_WHITE, 0, 255).astype(np.uint8)
    yy, xx = np.mgrid[0 : ink.shape[0], 0 : ink.shape[1]]
    ox, oy = int(cx) - max(0, int(cx) - r), int(cy) - max(0, int(cy) - r)
    ink[(xx - ox) ** 2 + (yy - oy) ** 2 > r * r] = 255  # 圈外的卡片底色也是白的，抹掉
    big = cv2.resize(ink, None, fx=5.6 / scale, fy=5.6 / scale, interpolation=cv2.INTER_CUBIC)
    big = cv2.copyMakeBorder(big, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    return cv2.cvtColor(big, cv2.COLOR_GRAY2BGR)


def parse_badge_text(text):
    """OCR 读到的椎数：单个数字 0~6，「—」读成 - / 一 / — 算 0（没椎），其他返回 None。"""
    t = re.sub(r"[\s'\".,`:;|]", "", text or "")
    if t in ("-", "—", "一", "－", "_"):
        return 0
    if len(t) == 1 and t in "0123456":
        return int(t)
    return None


def read_badge(frame, power_box, width, height, templates=None, recognize=None):
    """
    读战力数字左上方蓝圈里的椎数：0 表示「—」，None 表示没找到蓝圈或没认出来。
    :param recognize: 可选，img -> (文字, 置信度)，传了就先用 OCR 读圈里的数字（模板只有 1/4/6/—，
        2560x1440 下笔画粗细也对不上），读不出来再退回模板比对。
    """
    if frame is None:
        return None
    templates = templates if templates is not None else load_badge_templates()
    scale = height / 768
    px, py = _center(power_box)
    disk = find_badge_disk(frame, px + BADGE_DX * width, py + BADGE_DY * height, scale)
    if disk is None:
        return None
    cx, cy = disk
    if recognize is not None:
        img = badge_ocr_image(frame, cx, cy, scale)
        text, conf = recognize(img) if img is not None else (None, 0.0)
        badge = parse_badge_text(text)
        if badge is not None and conf >= BADGE_OCR_MIN_CONF:
            return badge
    if not templates:
        return None
    for white in BADGE_WHITES:
        best, best_score = None, 0.0
        for digit, tpl in templates.items():
            score = max(
                _iou(badge_digit_mask(frame, cx, cy, scale, dx, dy, white), tpl)
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
            )
            if score > best_score:
                best, best_score = digit, score
        if best_score >= BADGE_MIN_IOU:
            return best
    return None


# ------------------------------------------------------------------ 地格
TILE_LOOSE = ((85, 30, 120), (125, 255, 255))  # 泛蓝的地格（含已站人的、颜色淡的）
TILE_STRICT = ((90, 90, 200), (125, 255, 255))  # 高亮的亮蓝地格，通常是选中卡片后可部署的空格


def find_tiles(frame, width, height, strict=False):
    """
    地图上的蓝色地格，返回 [{"center": (x, y), "bbox": (x, y, w, h), "sat": 平均饱和度}, ...]，先上后下、先左后右。
    strict=True 只取高亮的亮蓝地格。
    """
    if frame is None:
        return []
    lo, hi = TILE_STRICT if strict else TILE_LOOSE
    x0, y0, x1, y1 = (
        int(MAP_BOX[0] * width),
        int(MAP_BOX[1] * height),
        int(MAP_BOX[2] * width),
        int(MAP_BOX[3] * height),
    )
    region = frame[y0:y1, x0:x1]
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    # 地格之间是白色细边（饱和度很低），不做闭运算，否则相邻地格会连成一块
    mask = cv2.inRange(hsv, lo, hi)
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask)
    s = height / 768
    tiles = []
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        bx, by, bw, bh = stats[i, :4]
        if area < 800 * s * s or not (60 * s <= bw <= 260 * s) or not (40 * s <= bh <= 200 * s):
            continue
        cx, cy = x0 + bx + bw / 2, y0 + by + bh / 2
        comp = mask[by : by + bh, bx : bx + bw] > 0
        sat = float(hsv[by : by + bh, bx : bx + bw, 1][comp].mean()) if comp.any() else 0.0
        tiles.append({"center": (cx, cy), "bbox": (x0 + bx, y0 + by, int(bw), int(bh)), "sat": sat})
    tiles.sort(key=lambda t: (t["center"][1], t["center"][0]))
    return tiles


def merge_tiles(primary, secondary, min_dist=40):
    """primary 在前，secondary 里离 primary 任一中心不足 min_dist 的去重。"""
    out = list(primary)
    for t in secondary:
        if all(
            (t["center"][0] - o["center"][0]) ** 2 + (t["center"][1] - o["center"][1]) ** 2 >= min_dist**2 for o in out
        ):
            out.append(t)
    return out


def order_tiles(tiles, digit_boxes, height):
    """
    试点地格的顺序：没有单位编号压着的优先，其中颜色更饱和（蓝得更明显，通常是可部署的高亮格）的靠前。
    """
    free = empty_tiles(tiles, digit_boxes, height)
    free_ids = {id(t) for t in free}
    taken = [t for t in tiles if id(t) not in free_ids]
    key = lambda t: -t.get("sat", 0)
    return sorted(free, key=key) + sorted(taken, key=key)


def empty_tiles(tiles, digit_boxes, height):
    """去掉头顶有单位编号（1~4 的小白框）的地格；编号在地格上方约 0.5~1.3 个地格高处。"""
    out = []
    for t in tiles:
        bx, by, bw, bh = t["bbox"]
        occupied = False
        for d in digit_boxes:
            if not digit_re.match(d.name):
                continue
            dx, dy = _center(d)
            if bx - 0.1 * bw <= dx <= bx + 1.1 * bw and by - 1.3 * bh <= dy <= by + 0.6 * bh:
                occupied = True
                break
        if not occupied:
            out.append(t)
    return out


def make_check_frame(width, height, checks):
    """测试用：生成一张黑图并在给定点画橙色方块。"""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    for x, y in checks:
        frame[max(0, y - 6) : y + 7, max(0, x - 6) : x + 7] = (0, 160, 255)
    return frame


# ---------------- 卡片头像识别（免点击认人） ----------------
# 卡片立绘区域相对战力数字中心：左右各 0.02 画面宽，上方 0.10h ~ 0.03h（避开左上角椎数圆标和右上角橙勾）
AVATAR_DX = 0.02
AVATAR_Y0, AVATAR_Y1 = -0.10, -0.03
AVATAR_REF = (52, 54)  # 统一缩放到的 (宽, 高)，1280x768 下正好是原尺寸
AVATAR_DIR = os.path.join("assets", "card_avatars")
AVATAR_THRESHOLD = 0.75
_name_ok = re.compile(r"^[一-鿿A-Za-z0-9\-·]{2,12}$")


def avatar_crop(frame, power_box, width, height, margin=0):
    """
    截取卡片立绘中间一块并缩放到固定尺寸，用来和模板比对。
    :param margin: 四周多截的像素（按 1280 宽的尺度），比对时用它容忍几个像素的定位偏差
    """
    px = power_box.x + power_box.width / 2
    py = power_box.y + power_box.height / 2
    scale = width / 1280
    m = margin * scale
    x0, x1 = int(px - AVATAR_DX * width - m), int(px + AVATAR_DX * width + m)
    y0, y1 = int(py + AVATAR_Y0 * height - m), int(py + AVATAR_Y1 * height + m)
    x0, y0 = max(x0, 0), max(y0, 0)
    crop = frame[y0:y1, x0:x1]
    if crop.size == 0 or crop.shape[0] < 10 or crop.shape[1] < 10:
        return None
    return cv2.resize(crop, (AVATAR_REF[0] + 2 * margin, AVATAR_REF[1] + 2 * margin), interpolation=cv2.INTER_AREA)


AVATAR_MARGIN = 8


def _imread_any(path):
    data = np.fromfile(path, dtype=np.uint8)  # cv2.imread 在 Windows 上读不了中文路径
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def _imwrite_any(path, img):
    ok, buf = cv2.imencode(".png", img)
    if ok:
        buf.tofile(path)
    return ok


_variant_re = re.compile(r"^(.+?)(?:_(\d+))?$")
AVATAR_MAX_VARIANTS = 8


class AvatarBook:
    """
    assets/card_avatars/<人形名>.png：每个人形的卡片立绘模板。
    同一个人形换了皮肤立绘就不一样，所以一个名字可以有多张模板：<人形名>.png、<人形名>_2.png、<人形名>_3.png……
    第一次见到某张卡片时点一下、OCR 左下角名字并自动存模板；名字已有模板但这张立绘都不像，就当新皮肤再存一张。
    """

    def __init__(self, folder=AVATAR_DIR, threshold=AVATAR_THRESHOLD):
        self.folder = folder
        self.threshold = threshold
        self.templates = None  # 名字 -> [模板, ...]

    def load(self):
        if self.templates is None:
            self.templates = {}
            if os.path.isdir(self.folder):
                for fn in sorted(os.listdir(self.folder)):
                    stem, ext = os.path.splitext(fn)
                    if ext.lower() != ".png":
                        continue
                    img = _imread_any(os.path.join(self.folder, fn))
                    if img is not None and img.shape[:2] == (AVATAR_REF[1], AVATAR_REF[0]):
                        name = _variant_re.match(stem).group(1)
                        self.templates.setdefault(name, []).append(img)
        return self.templates

    def match(self, crop):
        """返回 (名字, 相似度)；没有模板或都不像时名字为 None。"""
        best, best_score = None, -1.0
        if crop is None:
            return None, 0.0
        for name, tpls in self.load().items():
            for tpl in tpls:
                score = float(cv2.matchTemplate(crop, tpl, cv2.TM_CCOEFF_NORMED).max())
                if score > best_score:
                    best, best_score = name, score
        if best_score < self.threshold:
            return None, best_score
        return best, best_score

    def learn(self, name, crop):
        """名字合法时存模板：没见过的名字存 <名字>.png；名字有了但这张立绘和已有模板都不像（新皮肤）就存 <名字>_n.png。返回是否新存。"""
        if crop is None or not name or not _name_ok.match(name):
            return False
        have = self.load().get(name, [])
        if have:
            if any(float(cv2.matchTemplate(crop, tpl, cv2.TM_CCOEFF_NORMED).max()) >= self.threshold for tpl in have):
                return False
            if len(have) >= AVATAR_MAX_VARIANTS:
                return False
        os.makedirs(self.folder, exist_ok=True)
        n = len(have) + 1
        while True:
            fn = f"{name}.png" if n == 1 else f"{name}_{n}.png"
            path = os.path.join(self.folder, fn)
            if not os.path.exists(path):
                break
            n += 1
        if _imwrite_any(path, crop):
            self.templates.setdefault(name, []).append(crop.copy())
            return True
        return False


def identify_cards(frame, cards, width, height, book):
    """给每张卡片填上 name / name_score（认不出为 None）。"""
    for c in cards:
        c["avatar"] = avatar_crop(frame, c["power_box"], width, height)
        crop = avatar_crop(frame, c["power_box"], width, height, margin=AVATAR_MARGIN)
        c["name"], c["name_score"] = book.match(crop)
    return cards


# ---------------- 地格识别 v2：菱形模板 ----------------
# 地格是亮蓝色菱形（约 110x84 @1280x768），相邻地格只隔一条白边，连通域会粘在一起，
# 所以改用菱形核在蓝色掩码上做归一化相关找中心；「填充率」= 菱形内蓝色像素占比，空地格接近 1，
# 站了人的地格被立绘挡掉一块，填充率明显更低。
# 空地格会呼吸变暗（V 可低到 160、S 到 50），青绿色地板靠色相（87~95）排除。
# 实录 2026-10-20：竞技场（实兵演习）部署图的地格内部更暗（V 约 130、S 约 155，只有边框亮），V 下限 150 时 5 个地格只认出 1 个
# 还认错，阵容 2/4 就开打；降到 130 后普通关卡的结果不变（填充率略高），竞技场能认全。
TILE_HSV = ((98, 40, 130), (122, 255, 255))
TILE_KERNEL = (110, 84)
TILE_MIN_SCORE = 0.65
TILE_EMPTY_FILL = 0.85


def _diamond(kw, kh):
    ker = np.zeros((kh, kw), np.float32)
    ys, xs = np.mgrid[0:kh, 0:kw]
    ker[(np.abs(xs + 0.5 - kw / 2) / (kw / 2) + np.abs(ys + 0.5 - kh / 2) / (kh / 2)) <= 1] = 1
    return ker


def find_deploy_tiles(frame, width, height, max_n=12):
    """
    返回 [{"center": (x, y), "score": 菱形匹配度, "fill": 填充率}, ...]，按填充率从高到低（空地格在前）。
    """
    if frame is None:
        return []
    s = height / 768
    x0, y0, x1, y1 = (
        int(MAP_BOX[0] * width),
        int(MAP_BOX[1] * height),
        int(MAP_BOX[2] * width),
        int(MAP_BOX[3] * height),
    )
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, TILE_HSV[0], TILE_HSV[1]).astype(np.float32) / 255
    kw, kh = int(TILE_KERNEL[0] * s), int(TILE_KERNEL[1] * s)
    if mask.shape[0] <= kh or mask.shape[1] <= kw:
        return []
    ker = _diamond(kw, kh)
    res = cv2.matchTemplate(mask, ker, cv2.TM_CCORR_NORMED)
    fill = cv2.filter2D(mask, -1, ker / ker.sum(), borderType=cv2.BORDER_CONSTANT)
    out = []
    for _ in range(max_n):
        _, mx, _, loc = cv2.minMaxLoc(res)
        if mx < TILE_MIN_SCORE:
            break
        x, y = loc[0] + kw // 2, loc[1] + kh // 2
        out.append({"center": (x0 + x, y0 + y), "score": round(float(mx), 2), "fill": round(float(fill[y, x]), 2)})
        # 相邻地格中心相距约 (kw/2, kh/2)，压制范围要比这小
        cv2.rectangle(
            res,
            (loc[0] - int(kw * 0.45), loc[1] - int(kh * 0.45)),
            (loc[0] + int(kw * 0.45), loc[1] + int(kh * 0.45)),
            0,
            -1,
        )
    out.sort(key=lambda t: -t["fill"])
    return out


def far_point(tiles, width, height, candidates=((0.45, 0.30), (0.30, 0.50), (0.60, 0.22), (0.25, 0.30), (0.55, 0.60))):
    """地图上离所有地格都远的一个点（相对坐标），用来点一下取消选中。"""
    best, best_d = candidates[0], -1
    for cx, cy in candidates:
        d = min(
            [((cx * width - t["center"][0]) ** 2 + (cy * height - t["center"][1]) ** 2) ** 0.5 for t in tiles] or [1e9]
        )
        if d > best_d:
            best, best_d = (cx, cy), d
    return best


# ---------------- 单位编号标签 ----------------
# 已上场单位头顶有个深色小方块（白边、白色数字），标签中心往下约 0.083 画面高就是它站的地格中心。
UNIT_TAG_DY = 0.083
UNIT_TAG_SCORE = 0.6


def find_unit_tags(frame, width, height, max_n=8):
    """
    我方单位头顶的编号标签（深色方块 + 亮边 + 白色数字 1~5），返回 [(x, y, score), ...]，按匹配度从高到低。
    - 模板按画面高度缩放，中间数字区域用 mask 排除，不管是几号都能匹配；
    - 再核对结构：内部大部分是深色、边框明显比内部亮、中间有白色（三通道都亮）的数字。
      敌人的等级牌数字是黄色的，靠这一条排除。
    实录 2026-10-20 2560x1440：旧模板边框写死 1~2 像素、中间画了个「1」，四个标签一个都没认出来，
    撤人时找不到自己的单位，只点到了敌人。
    """
    if frame is None:
        return []
    s = height / 768
    x0, y0, x1, y1 = (
        int(MAP_BOX[0] * width),
        int(MAP_BOX[1] * height),
        int(MAP_BOX[2] * width),
        int(MAP_BOX[3] * height),
    )
    region = frame[y0:y1, x0:x1]
    g8 = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    gray = g8.astype(np.float32)
    best = sizes = None
    for n0 in (17, 19, 21):
        n = int(round(n0 * s)) | 1
        if gray.shape[0] <= n or gray.shape[1] <= n:
            continue
        b = max(2, int(round(n * 0.14)))
        tpl = np.full((n, n), 200, np.float32)
        tpl[b : n - b, b : n - b] = 40
        mask = np.ones((n, n), np.float32)
        c, q = n // 2, max(2, int(round(n * 0.22)))
        mask[c - q : c + q + 1, c - q : c + q + 1] = 0  # 数字区域不参与比较
        res = np.nan_to_num(cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED, mask=mask), nan=0, posinf=0, neginf=0)
        res = cv2.copyMakeBorder(
            res,
            n // 2,
            gray.shape[0] - res.shape[0] - n // 2,
            n // 2,
            gray.shape[1] - res.shape[1] - n // 2,
            cv2.BORDER_CONSTANT,
            value=0,
        )
        if best is None:
            best, sizes = res, np.full(res.shape, n, np.int32)
        else:
            better = res > best
            best, sizes = np.where(better, res, best), np.where(better, n, sizes)
    if best is None:
        return []
    out = []
    sup = int(round(14 * s))
    for _ in range(max_n + 6):
        _, mx, _, (x, y) = cv2.minMaxLoc(best)
        if mx < UNIT_TAG_SCORE or len(out) >= max_n:
            break
        n = int(sizes[y, x])
        best[max(0, y - sup) : y + sup, max(0, x - sup) : x + sup] = 0
        h, b = n // 2, max(2, int(round(n * 0.14)))
        if y - h < 0 or x - h < 0 or y + h >= g8.shape[0] or x + h >= g8.shape[1]:
            continue
        sq = g8[y - h : y + h + 1, x - h : x + h + 1]
        inner = sq[b + 1 : -b - 1, b + 1 : -b - 1]
        inner_bgr = region[y - h + b + 1 : y + h - b, x - h + b + 1 : x + h - b]
        ring = np.concatenate([sq[:b].ravel(), sq[-b:].ravel(), sq[:, :b].ravel(), sq[:, -b:].ravel()])
        dark = float((inner < 80).mean())
        white = float((inner_bgr.min(axis=2) > 170).mean())
        if dark > 0.55 and 0.02 < white < 0.4 and np.median(ring) > np.median(inner) + 60:
            out.append((x0 + x, y0 + y, round(float(mx), 2)))
    return out


# 底部「作战开始」和它左边的切换按钮。站在最下面一排的单位，地格被按钮盖住，按标签往下推的点会落进按钮里，
# 实录 2026-10-22 NZ-1-1：整理阵容时点 1 号单位的地格 (1151,1291) 直接点中了作战开始，人没核对完就开战了。
START_BUTTON_BOX = (0.34, 0.86, 0.61, 0.96)


def in_start_button(point, width, height):
    x0, y0, x1, y1 = START_BUTTON_BOX
    return x0 * width <= point[0] <= x1 * width and y0 * height <= point[1] <= y1 * height


def unit_tiles_from_tags(tags, height, width=None):
    """标签下方的地格中心；给了 width 时，被作战开始按钮挡住的改点按钮上沿上面的人形身体，还挡着就不点。"""
    out = []
    for x, y, _ in tags:
        point = (x, y + UNIT_TAG_DY * height)
        if width is not None and in_start_button(point, width, height):
            point = (x, max(y + 0.02 * height, (START_BUTTON_BOX[1] - 0.01) * height))
            if in_start_button(point, width, height):
                continue
        out.append(point)
    return out


# ------------------------------------------------------------------ 换人决策


# ------------------------------------------------------------------ 支援单位（第 9 章起，实录 2026-10-20）
# 部署界面顶部多一行「支援 2/3」，底部中间多一对「部署人形 / 部署支援」页签，支援点是带 ♜ 图标的蓝色地格，
# 右侧面板「可部署支援单位」是一排 Lv.20 的工事/炮塔/地雷卡片，右下角按钮是「部署支援单位 / 撤回支援单位」。
# 第一次进第 9 章时可露凯的「通信中」引导挡在部署界面上：先点红框支援点 → 对话推进 → 点高亮的「部署支援单位」。
SUPPORT_COUNT_BOX = (0.33, 0.06, 0.67, 0.14)  # 顶部第二行「支援 2/3」（第一行「人形 4/4」在 0.05 以上）
SUPPORT_TAB_BOX = (0.38, 0.80, 0.64, 0.88)  # 底部中间「部署人形 / 部署支援」页签
SUPPORT_TAB_XY = {"部署人形": (0.452, 0.839), "部署支援": (0.547, 0.839)}  # OCR 漏读时按固定位置点
TUTORIAL_BOX = (0.16, 0.08, 0.60, 0.20)  # 可露凯头像右边的名字牌和橙色指示文字（左边的作战目标不在这个范围里）
SUPPORT_CARD_DY = -0.055  # 卡片中心相对「Lv.20」标签中心：往上 0.055 画面高
SUPPORT_CHECK_DX, SUPPORT_CHECK_DY = 0.022, -0.112  # 已部署的橙色勾相对「Lv.20」标签中心
# 引导红框是粉红色细边 + 橙色角标（饱和度 70~130），蓝地格色相在 100 附近、单位血条是纯红（饱和度 200+），互不混淆
TUTORIAL_TILE_HSV = (((0, 50, 170), (12, 170, 255)), ((165, 50, 170), (180, 170, 255)))
TUTORIAL_TILE_MAX_FILL = 0.5  # 红框是空心的：连通域面积 / 外接框面积要小，实心色块不算
support_lv_re = re.compile(r"L[vV]\.?\s*\d+")
support_count_label_re = re.compile(r"支\s*援")
tutorial_text_re = re.compile(r"可露凯|通信中|点击.*部署|提醒|提示|支援单位")


def parse_support_count(names):
    """
    顶部「支援 2/3」那一行的 OCR 文字 → (2, 3)。
    没有「支援」标签（普通关卡）返回 None；有标签但计数读不出来返回 (None, None)——
    实录 2026-10-20：继续前进后的第 2、3 波，「0/3」被半透明面板后面的敌人名字/血条挡住，只读到「支援」「3」。
    """
    if not any(support_count_label_re.search(n) for n in names):
        return None
    for n in names:
        # 和 BaseGfTask.parse_deploy_count 同样的容错：斜杠常被读成 1/l/I
        m = re.search(r"(\d)\s*[/|\\]\s*(\d)", n) or re.fullmatch(r"(\d)[1lI](\d)", n.strip())
        if m and int(m.group(2)) >= int(m.group(1)):
            return int(m.group(1)), int(m.group(2))
    return None, None


def tutorial_step(names):
    """
    引导对话框里的文字 → 下一步：
    - 提到「部署点」：点红框支援点 → "tile"
    - 提到「部署支援单位」：点右下角按钮 → "button"
    - 其他对话（提醒/提示）：点对话框推进 → "advance"
    - 没有引导文字：None
    """
    if not any(tutorial_text_re.search(n) for n in names):
        return None
    text = "".join(names)
    if "部署点" in text:
        return "tile"
    # 实录：开场白「战前部署支援单位可以让作战效率大幅提高」也含这几个字，只有「点击部署支援单位」才是点按钮
    if re.search(r"点击.{0,3}部署支援单位", text):
        return "button"
    return "advance"


def find_tutorial_tile(frame, width, height):
    """地图上被引导红框圈住的支援点中心 (x, y)；没有返回 None。"""
    if frame is None:
        return None
    s = height / 768
    x0, y0, x1, y1 = (
        int(MAP_BOX[0] * width),
        int(MAP_BOX[1] * height),
        int(MAP_BOX[2] * width),
        int(MAP_BOX[3] * height),
    )
    hsv = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2HSV)
    mask = None
    for lo, hi in TUTORIAL_TILE_HSV:
        m = cv2.inRange(hsv, lo, hi)
        mask = m if mask is None else (mask | m)
    k = max(3, int(15 * s)) | 1
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask)
    best = None
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        bw, bh = stats[i, 2], stats[i, 3]
        # 红框外接框实测 92x61（1280x768 比例）；右上角敌方标记只有 68x38，别认成它
        if area < 400 * s * s or not (75 * s <= bw <= 300 * s) or not (48 * s <= bh <= 220 * s):
            continue
        if area / float(bw * bh) > TUTORIAL_TILE_MAX_FILL:
            continue
        if best is None or area > best[0]:
            # 用外接框中心而不是质心：红框上还带着橙色角标，质心会被拉偏
            bx, by = stats[i, 0], stats[i, 1]
            best = (area, (x0 + bx + bw / 2, y0 + by + bh / 2))
    return (int(best[1][0]), int(best[1][1])) if best else None


def support_card_points(lv_boxes, width, height):
    """右侧面板「Lv.20」标签 → 卡片中心和勾选采样点，先上后下、先左后右。"""
    cards = []
    for b in lv_boxes:
        if not support_lv_re.search(b.name):
            continue
        cx, cy = _center(b)
        cards.append(
            {
                "center": (int(cx), int(cy + SUPPORT_CARD_DY * height)),
                "check": (int(cx + SUPPORT_CHECK_DX * width), int(cy + SUPPORT_CHECK_DY * height)),
                "lv": b.name,
            }
        )
    cards.sort(key=lambda c: (round(c["center"][1] / (0.05 * height)), c["center"][0]))
    return cards


def support_point_candidates(frame, width, height):
    """
    支援点候选，按先后顺序试点：菱形模板认出来的地格在前，宽松蓝色连通域兜底在后（按饱和度从高到低）。
    实录 2026-10-20 9-7：支援点是一格亮蓝色、中间圆形图标、还被敌人血条压着一角，菱形模板认不出，
    宽松连通域能找到（顺带会多一块蓝色水面，点了按钮不变就跳过，无害）。
    """
    primary = find_deploy_tiles(frame, width, height)
    loose = sorted(find_tiles(frame, width, height), key=lambda t: -t.get("sat", 0))
    return [t["center"] for t in merge_tiles(primary, loose, min_dist=0.03 * height)]


def fallback_empty_tiles(frame, width, height, known, occupied, min_dist_ratio=0.03):
    """
    补人的兜底候选：宽松蓝色连通域里离已知候选和有人的格子都远的，按饱和度从高到低。
    实录 2026-10-20 BH-9-4：第 4 个空格被助战大机甲挡住一部分，菱形模板没认出来，脚本把有人的格子当成唯一空格，
    每张卡都点到春田身上；宽松连通域能找到那个空格。
    """
    gap = (min_dist_ratio * height) ** 2
    taken = list(known) + list(occupied)
    out = []
    for t in sorted(find_tiles(frame, width, height), key=lambda t: -t.get("sat", 0)):
        c = t["center"]
        if all((c[0] - x) ** 2 + (c[1] - y) ** 2 >= gap for x, y in taken):
            out.append(c)
            taken.append(c)
    return out


# ------------------------------------------------------------------ 撤下单位后空出来的地格
FREED_DIFF = 40  # 灰度差超过它算变化
FREED_MIN_AREA = 0.0015  # 变化块至少占画面面积这么多（人形立绘消失是一大块）


def freed_tile(before, after, width, height):
    """
    撤下一个单位前后两帧对比，返回空出来的地格中心 (x, y)，没找到返回 None。
    立绘消失的那块变化最大；人站在地格上，地格中心取变化块最下面 30% 像素的重心。
    不靠地格颜色/编号标签（2560x1440 下这两种识别都不稳），分辨率无关。
    """
    if before is None or after is None or before.shape != after.shape:
        return None
    x0, y0, x1, y1 = (
        int(MAP_BOX[0] * width),
        int(MAP_BOX[1] * height),
        int(MAP_BOX[2] * width),
        int(MAP_BOX[3] * height),
    )
    a = cv2.cvtColor(before[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    b = cv2.cvtColor(after[y0:y1, x0:x1], cv2.COLOR_BGR2GRAY)
    diff = (cv2.absdiff(a, b) > FREED_DIFF).astype(np.uint8)
    k = max(3, int(round(5 * height / 768)))
    diff = cv2.morphologyEx(diff, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    diff = cv2.morphologyEx(diff, cv2.MORPH_CLOSE, np.ones((k * 3, k * 3), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(diff)
    if n <= 1:
        return None
    i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[i, cv2.CC_STAT_AREA] < FREED_MIN_AREA * width * height:
        return None
    ys, xs = np.nonzero(labels == i)
    cut = np.percentile(ys, 70)
    low = ys >= cut
    return x0 + float(xs[low].mean()), y0 + float(ys[low].mean())
