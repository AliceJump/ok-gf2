import re
import time
from collections import Counter

from ok import Logger

from src.core.BaseGfTask import BaseGfTask, chapter_select_re, map_re, nav_tabs_re, pop_ups
from src.core.stage_card import MEDAL_BOX, has_clear_badge, medal_re, parse_medals
from src.image.hsv_config import HSVRange as hR

logger = Logger.get_logger(__name__)


# 未解锁提示：主线是「完成前置关卡解锁」，往期活动是「需要完成前置关卡」（实录 2026-10-22 狂想四重奏 MA-1-5）
LOCKED_WORDS = ["完成前置关卡解锁", "需要完成前置关卡"]
PANEL_WORDS = ["特殊奖励", "观看", "挑战"] + LOCKED_WORDS
# 面板底部按钮：实机上 OCR 常把「观看」只框出一个「观」（0.81），所以第二个字可有可无
BUTTON_RE = [re.compile(r"^观\s*看?$"), re.compile(r"^挑\s*战?$")]
BUTTON_MIN_Y = 0.85  # 按钮在面板最底下，只认 y 在这以下的框，避免描述文字里的字混进来

# ------------------------------------------------------------------ 章节选择页（持续推进用，实录 2026-10-20）
# 从章节地图按 ESC 回到章节选择页：左边一列章节标题，当前章前面有「9.0」这样的高亮角标，后面的章节往下排，
# 未解锁的带锁、点了没有任何反应；右下是「章节进度 57% / 27/48 / 一句简介」和「确认」。
CHAPTER_LIST_MAX_X = 0.2  # 章节标题都在画面左边 20% 以内
CHAPTER_LIST_MAX_Y = 0.85  # 再往下是「猎人评定 / 同调演练」入口
CHAPTER_BADGE_MAX_X = 0.015  # 当前章的「9.0」角标贴着左边（x≈13/2560）；其他章前面的「C-11.0」小字在 x≈69
chapter_badge_re = re.compile(r"\d+\s*\.\s*\d\s*$")
chapter_title_re = re.compile(r"[\u4e00-\u9fff]{2,}")
chapter_noise_re = re.compile(r"^C\s*-|猎人评定|同调演练|剧情战役|往期活动|模拟作战|补给作战")
chapter_select_words = ["章节进度"]

CHAPTER_VERIFY_ROUNDS = 4  # 推完一章后按「章节进度」核对，最多回去再扫几轮
CHAPTER_MAX_PASSES = 6  # 一章最多从头扫几遍（每遍推过关才会再扫，正常两遍就停）
STAGE_MAX_ATTEMPTS = 2  # 同一关一次推图里最多打几次
ENSURE_MAP_TRIES = 4  # 看不到关卡时最多恢复几次
PASS_MAX_STEPS = 300  # 一遍扫描最多处理多少步（防止死循环）
MAP_DRAG_Y = 0.2  # 拖地图时按住的高度：卡片都在 0.3~0.75，这一带是空白背景，不会点到卡片
# 打完/看完一关后「回到选关」的标志：地图卡片、章节选择页的「章节进度」、或作战页顶上的页签。
# 实录 2026-10-21 15.0 章：看完剧情落在章节选择页，「章节进度」四个字 OCR 没读到、页签读到了，白等了 120 秒
BACK_TO_MAP = [map_re, chapter_select_re, nav_tabs_re]
STATUS_TEXT = {
    "cleared": "已通关（面板没有首通奖励）, 跳过",
    "locked": "未解锁, 先推其他关卡",
    "nopanel": "没读到关卡面板, 跳过",
    "unknown": "面板反复读不到按钮, 跳过",
    "skip": "跳过",
}


class ChapterLocked(Exception):
    """本章剩下的关卡都未解锁。"""


def chapter_titles(boxes, width, height):
    """章节选择页左列的章节标题框，从上到下。"""
    out = []
    for b in boxes:
        name = (b.name or "").strip()
        if b.x > CHAPTER_LIST_MAX_X * width or b.y > CHAPTER_LIST_MAX_Y * height or b.y < 0.08 * height:
            continue
        if chapter_noise_re.search(name) or not chapter_title_re.search(name):
            continue
        out.append(b)
    return sorted(out, key=lambda b: b.y)


def current_and_next_chapter(boxes, width, height):
    """
    (当前章标题框, 下一章标题框)。当前章按「9.0」角标所在行认，角标没读到就当最上面那个是当前章。
    有新内容的章节前面也有个红色「!」，OCR 读成「018.0」也贴着左边；选中的那个角标是深色底带斜杠「!/19.0」，
    有斜杠的优先（实录 2026-10-21：18.0、19.0、19.5 都带红点，原来取第一个 18.0，把当前章 19.0 当成「下一章」点）。
    """
    titles = chapter_titles(boxes, width, height)
    if not titles:
        return None, None
    badges = [
        b
        for b in boxes
        if b.x <= CHAPTER_BADGE_MAX_X * width
        and chapter_badge_re.search(b.name or "")
        and not (b.name or "").strip().startswith("C")
    ]
    if badges:
        badge = next((b for b in badges if re.search(r"[/／]", b.name)), badges[0])
        by = badge.y + badge.height / 2
        current = min(titles, key=lambda t: abs(t.y + t.height / 2 - by))
    else:
        current = titles[0]
    later = [t for t in titles if t.y > current.y + current.height / 2]
    return current, (later[0] if later else None)


chapter_progress_re = re.compile(r"^\s*\d{1,3}\s*%\s*$|^\s*\d{1,3}\s*/\s*\d{1,3}\s*$")


def parse_chapter_percent(boxes, width):
    """
    章节选择页右侧「章节进度 57%」里的百分比（游戏按本章勋章算，全拿到才是 100%）；读不到返回 None。
    OCR 常把标签和数字粘在一起、竖线读成 1（实录「章节进度1100%」），所以只取紧挨着 % 的最多三位数。
    """
    for b in boxes:
        if b.x < 0.6 * width:
            continue
        if m := re.search(r"(\d{1,3})\s*%", (b.name or "").replace("进度", " ")):
            value = int(m.group(1))
            if value > 100:
                value = int(str(value)[-3:]) if str(value)[-3:] == "100" else int(str(value)[-2:])
            if 0 <= value <= 100:
                return value
    return None


def chapter_display_name(text):
    """「010.0远日点·下篇Q」→「远日点·下篇」：去掉粘进来的角标数字和尾巴上的杂字，只用于日志。"""
    m = re.search(r"[\u4e00-\u9fff][\u4e00-\u9fff·・\s]*[\u4e00-\u9fff]", text or "")
    return m.group(0) if m else (text or "").strip()


def chapter_signature(boxes, width, height):
    """
    选中了哪一章的指纹：右侧「57%」「27/48」两个数字 + 左边角标所在行。
    点锁着的章节什么都不变；简介那句话 OCR 时有时无句号，不拿来比。
    """
    nums = tuple(
        sorted(
            (b.name or "").replace(" ", "")
            for b in boxes
            if b.x > 0.6 * width and chapter_progress_re.match(b.name or "")
        )
    )
    current, _ = current_and_next_chapter(boxes, width, height)
    return nums, (current.name if current else None)


def button_kind(text):
    """按钮文字 -> watch / challenge / None，容忍只读到第一个字。"""
    text = (text or "").strip().replace(" ", "")
    if text in ("观", "观看"):
        return "watch"
    if text in ("挑", "挑战"):
        return "challenge"
    return None


def classify_panel(has_boxes, locked_hint, special_reward, challenge, watch):
    """
    关卡面板文字 -> (状态, 动作按钮)。
    - 没识别到任何面板文字：nopanel
    - 有「完成前置关卡解锁」/「需要完成前置关卡」：locked
    - 没有「特殊奖励」（首通奖励已领）：cleared
    - 有奖励且有「挑战」/「观看」：challenge / watch
    - 有奖励但按钮还没识别到：unknown，交给调用方重读，绝不能当未解锁跳过
    """
    if not has_boxes:
        return "nopanel", None
    if locked_hint:
        return "locked", None
    if not special_reward:
        return "cleared", None
    if challenge:
        return "challenge", challenge
    if watch:
        return "watch", watch
    return "unknown", None


def canonical_name(name_group):
    """一组 OCR 名字里取一个稳定的关卡名：优先不带 * 的、最短的。"""
    names = sorted((n for n in name_group if isinstance(n, str)), key=lambda n: (n.endswith("*"), len(n), n))
    return names[0] if names else None


def order_maps(maps, name_groups):
    """把关卡和对应的名字组配对后按 x 从左到右排序，返回 [(map, name_group), ...]。"""
    return sorted(zip(maps, name_groups, strict=True), key=lambda item: item[0].x)


def revealed_new(before, after, direction, min_shift=40, same_tol=60):
    """
    挪完视野后，要去的那一边有没有冒出之前没见过的卡片（direction=1 右边，-1 左边）。
    先按两帧都有的卡片量出地图挪了多少：没往要去的方向挪够 min_shift 就是到头了，不管名字。
    新卡片 = 名字没见过、并且（扣掉挪动量后）位置上之前也没有卡片的；同一位置换了个名字只是 OCR 读花了。
    - 不比名字集合：屏幕边上半张卡的名字 OCR 时有时无；
    - 不只看位置变没变：章节起点的第一张卡在屏幕中间，点它会把视野往右带，下一次往左拖又回来，
      看起来一直在「动」（实录 2026-10-20：回章节起点时反复点 BA-1-1）；
    - 实录 2026-10-21 15.0 章：最右的 VS-1-11 读成 VS-1-11 / )VS-1-11 / 1-0 / -1-10，地图其实没动，
      每次都当成冒出了新卡片，在章节末尾拖了 7 分钟。
    """
    seen = {}
    for card, group in before:
        for name in group:
            seen.setdefault(name, card)
    shifts = []
    for card, group in after:
        common = group & seen.keys()
        if common:
            shifts.append(card.x - seen[next(iter(common))].x)
    shift = sorted(shifts)[len(shifts) // 2] if shifts else 0
    if shifts and shift * direction > -min_shift:
        return False
    new = [
        card.x
        for card, group in after
        if not (group & seen.keys())
        and not any(abs(card.x - shift - old.x) < same_tol and abs(card.y - old.y) < same_tol for old, _ in before)
    ]
    if not new:
        return False
    common_x = [card.x for card, group in after if group & seen.keys()]
    if not common_x:
        return True
    return min(new) < min(common_x) if direction < 0 else max(new) > max(common_x)


class ClearMapTask(BaseGfTask):
    LINEUP_TASK = True  # 每关开战前都整理阵容（切编队、补满；借助战看开关）

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "推图"
        self.description = (
            "停在任意关卡页面或章节选择页启动即可，先回章节起点从左到右推完未通关的关卡，推完自动进下一章"
        )
        self.default_config.update(
            {
                "普通OCR": True,
                "除杂色OCR1": True,
                "除杂色OCR2": True,
                "战斗内点击自动": False,
                "推完继续下一章": True,
            }
        )
        self.config_description.update(
            {
                "普通OCR": (
                    "普通OCR：不做任何图像预处理，直接识别关卡名称\n"
                    "适用场景：背景和关卡卡片颜色与白色差异明显，文字清晰可辨"
                ),
                "除杂色OCR1": (
                    "除杂色OCR1（标准白色）：过滤掉非纯白色区域后再识别\n"
                    "适用场景：关卡卡片文字为标准白色，背景较复杂干扰识别"
                ),
                "除杂色OCR2": (
                    "除杂色OCR2（宽松白灰色）：同时保留白色与浅灰色区域后再识别\n"
                    "适用场景：关卡卡片文字为白色或浅灰色，或普通OCR/除杂色OCR1均无法识别时"
                ),
                "战斗内点击自动": (
                    "进入战斗后若检测到「行动结束」，自动点击右上角的自动战斗按钮\n"
                    "默认关闭，依赖游戏内全局自动（设置→其他→自动战斗设置）；未开全局自动时再打开"
                ),
                "推完继续下一章": (
                    "本章能推的都推完（或剩下的都没解锁）后，回章节选择页进入下一章继续推\n"
                    "下一章没解锁（带锁、点了没反应）就正常结束"
                ),
            }
        )
        self.processors = []

    # ------------------------------------------------------------------ 扫描
    def scan_maps(self):
        """识别当前屏幕上的关卡卡片，返回按 x 排序的 [(box, name_group), ...]。"""
        self.next_frame()
        maps = []
        for p in self.processors:
            maps.extend(self.ocr(match=map_re, log=True, frame_processor=p))
        maps, groups = merge_maps(maps, x_threshold=40 / 1920 * self.width, y_threshold=40 / 1080 * self.height)
        ordered = order_maps(maps, groups)
        self.log_debug(f"maps: {[m for m, _ in ordered]}")
        self.debug_shot("scan", [m for m, _ in ordered])
        return ordered

    # ------------------------------------------------------------------ 面板
    def inspect_card(self, card, name):
        """
        点开卡片读右侧面板，返回 (状态, 动作按钮)。
        状态：cleared / locked / challenge / watch / nopanel / unknown
        面板是带动画弹出来的，「特殊奖励」往往比底部按钮先出现，所以看到奖励却没看到按钮时多读几帧再下结论。
        """
        self.click(card, after_sleep=1)
        boxes = self.wait_ocr(box="right", match=PANEL_WORDS, time_out=3, log=True) or []
        status, action = self.panel_status(boxes)
        for _ in range(3):
            if status != "unknown":
                break
            # 有「特殊奖励」却没按钮：单独在右下角找按钮，容忍 OCR 只读到「观」/「挑」
            btn_boxes = self.ocr(box="bottom_right", match=BUTTON_RE, log=True) or []
            for b in btn_boxes:
                kind = button_kind(b.name)
                if kind and b.y >= self.height * BUTTON_MIN_Y:
                    self.log_info(f"右下角按钮读到 '{b.name}'，按 {kind} 处理", notify=False)
                    status, action = kind, [b]
                    break
            if status != "unknown":
                break
            self.sleep(0.6)
            self.next_frame()
            boxes = self.ocr(box="right", match=PANEL_WORDS, log=True) or []
            status, action = self.panel_status(boxes)
        self.debug_shot(f"panel_{name}", boxes)
        return status, action

    def panel_status(self, boxes):
        """按面板上识别到的文字判断关卡状态；只看到「特殊奖励」没看到按钮算 unknown，不能当作未解锁。"""
        # wait_ocr 的 match 会经过 OCR 纠错表展开（現看/観看 → 观看），
        # 但 find_boxes 是精确比较，这里要用同样展开过的匹配列表
        locked_hint = self.find_boxes(boxes, match=self.fix_match_regex(LOCKED_WORDS))
        special_reward = self.find_boxes(boxes, match=self.fix_match_regex(["特殊奖励"]))
        challenge = self.find_boxes(boxes, match=self.fix_match_regex(["挑战"]))
        watch = self.find_boxes(boxes, match=self.fix_match_regex(["观看"]))
        return classify_panel(bool(boxes), bool(locked_hint), bool(special_reward), challenge, watch)

    def close_map_panel(self):
        """关卡面板打开时才按返回；选关页面没有面板时按返回会直接退出到章节页面。"""
        self.sleep(0.5)
        if self.ocr(box="right", match=[re.compile("推荐等级"), "挑战目标", "特殊奖励", "敌方单位"]):
            self.back(after_sleep=1.5)

    # ------------------------------------------------------------------ 主流程
    def run(self):
        processors = []
        if self.config.get("普通OCR", True):
            processors.append(None)  # None 表示不做预处理，直接识别
        if self.config.get("除杂色OCR1", True):
            processors.append(self.make_hsv_isolator(hR.WHITE))  # 标准白色过滤
        if self.config.get("除杂色OCR2", True):
            processors.append(self.make_hsv_isolator(hR.WHITE_GRAY))  # 宽松白灰色过滤
        if not processors:
            processors = [None, self.make_hsv_isolator(hR.WHITE), self.make_hsv_isolator(hR.WHITE_GRAY)]
        self.processors = processors

        self.log_info("推图开始", notify=False)
        self.reset_lineup("推图")  # 每次启动任务只在第一场整理阵容，之后沿用
        self.start_watchdog()
        try:
            self._run_sweep()
        finally:
            self.stop_watchdog()

    def _run_sweep(self):
        # 停在章节选择页、作战的其他页签、部署界面、战斗中或结算页都可以启动：ensure_map 会先回到选关地图
        self.ensure_map()

        total = 0
        for _ in range(30):
            count, locked = self.finish_chapter()
            total += count
            if locked and not self.config.get("推完继续下一章", True):
                err = ChapterLocked(f"剩余关卡都未解锁({locked}), 请检查前置关卡后再启动")
                err.count = count
                raise err
            if not self.config.get("推完继续下一章", True):
                break
            nxt = self.enter_next_chapter()
            if not nxt:
                if locked:
                    self.log_info(f"本章还有未解锁的 {locked}；下一章也没解锁，推图结束", notify=True)
                break
            self.log_info(f"进入下一章「{nxt}」继续推图", notify=True)
            self.ensure_map()
        self.log_info(f"推图完成, 本次推进 {total} 关", notify=True)

    # ------------------------------------------------------------------ 持续推进
    def open_chapter_select(self):
        """从章节地图按 ESC 回到章节选择页。"""
        for _ in range(3):
            if self.wait_ocr(match=chapter_select_words, box="bottom_right", time_out=3, raise_if_not_found=False):
                return True
            self.back(after_sleep=2)
        return bool(self.ocr(match=chapter_select_words, box="bottom_right"))

    def chapter_percent(self):
        """回章节选择页读当前章节的完成度百分比（不进下一章，停在章节选择页）。"""
        self.close_map_panel()
        if not self.open_chapter_select():
            return None
        self.sleep(1)
        boxes = self.ocr(log=True)
        self.debug_shot("chapter_progress", boxes)
        return parse_chapter_percent(boxes, self.width)

    def reenter_from_chapter_select(self):
        """
        打完 / 看完一关后游戏退回了章节选择页：点「确认」进回选中的章节。返回是否进去了。
        停在「模拟作战 / 往期活动 / 补给作战」页签时先点「剧情战役」页签回到章节选择页。
        """
        if not self.ocr(match=chapter_select_words, box="bottom_right"):
            tab = self.ocr(box="top", match=re.compile(r"^剧情战役$"))
            if not tab:
                return False
            self.log_info("停在作战的其他页签上，切回「剧情战役」", notify=True)
            self.click(tab, after_sleep=2)
            if not self.wait_ocr(match=chapter_select_words, box="bottom_right", time_out=5, raise_if_not_found=False):
                return False
        self.log_info("回到了章节选择页，点确认进回章节继续推", notify=True)
        self.debug_shot("back_on_chapter_select")
        if not self.wait_click_ocr(
            match=self.fix_match_regex(["确认"]),
            box="bottom_right",
            time_out=5,
            after_sleep=3,
            raise_if_not_found=False,
        ):
            return False
        self.skip_dialogs(end_match=map_re, time_out=120, has_dialog=True, raise_if_not_found=False)
        return True

    def enter_next_chapter(self):
        """
        回章节选择页，点当前章下面那一章：右侧章节信息变了说明已选中（解锁了），点「确认」进去并跳过开场剧情；
        信息没变（锁着，点了没反应）或已经是最后一章就返回 None，停在章节选择页。返回新章节名。
        """
        self.info_set("current_task", "进入下一章")
        self.close_map_panel()
        if not self.open_chapter_select():
            self.log_info("没回到章节选择页，不继续下一章", notify=True)
            return None
        self.sleep(1)
        boxes = self.ocr(log=True)
        self.debug_shot("chapter_select", boxes)
        current, nxt = current_and_next_chapter(boxes, self.width, self.height)
        if nxt is None:
            self.log_info(f"「{current.name if current else '?'}」后面没有下一章了", notify=True)
            return None
        before = chapter_signature(boxes, self.width, self.height)
        self.click(nxt, after_sleep=1.5)
        self.next_frame()
        after_boxes = self.ocr(log=True)
        if chapter_signature(after_boxes, self.width, self.height) == before:
            self.log_info(f"下一章「{chapter_display_name(nxt.name)}」还没解锁（点了没反应）", notify=True)
            self.debug_shot("next_chapter_locked", after_boxes)
            return None
        confirm = self.find_boxes(after_boxes, match=self.fix_match_regex(["确认"]))
        if not confirm:
            self.log_info(f"选中了「{nxt.name}」但没找到「确认」", notify=True)
            return None
        self.click(confirm, after_sleep=3)
        # 新章节开头常有剧情 / 动画，跳过直到看到关卡卡片
        self.skip_dialogs(end_match=map_re, time_out=180, has_dialog=True, raise_if_not_found=False)
        return chapter_display_name(nxt.name)

    def resume_battle(self, time_out=1200):
        """
        从非选关页面接管：部署界面 / 战斗中 / 继续前进 → 走 auto_battle；结算页点确认；任务失败则报错。
        回到选关页面返回 True，认不出当前页面返回 False。
        """
        self.info_set("current_task", "接管当前战斗")
        start = time.time()
        unknown = 0
        while time.time() - start < time_out:
            self.next_frame()
            boxes = self.ocr()
            if self.find_boxes(boxes, match=map_re):
                return True
            if (
                self.find_boxes(boxes, match="作战开始")
                or self._is_battle_frame(boxes)
                or self.find_boxes(boxes, match="继续前进")
            ):
                self.log_info("当前在部署界面或战斗中，先打完这一关再继续推图", notify=True)
                self.auto_battle(
                    end_match=BACK_TO_MAP, has_dialog=True, need_click_auto=self.config.get("战斗内点击自动", False)
                )
                self.reenter_from_chapter_select()
                self.close_map_panel()
                return True
            if self.find_boxes(boxes, match="任务失败"):
                self.debug_shot("resume_failed", boxes)
                raise Exception("任务失败, 没打过!")
            if confirm := self.find_boxes(boxes, match=self.fix_match_regex(["确认", "确认结算"])):
                self.click(confirm, after_sleep=2)
                continue
            if self.find_boxes(boxes, match=pop_ups):
                self.back(after_sleep=1)
                continue
            # 结算页第一段只有人物和「任务完成」，点一下才出奖励页（奖励页的「确认」走上面的分支）
            # （实录 2026-10-21：重启后停在剧情→结算页，这里没认「任务完成」，和 skip_dialogs 互相踢皮球卡了 15 分钟）
            if done := self.find_boxes(boxes, match="任务完成"):
                self.click(done, after_sleep=2)
                continue
            # 认不出的页面多半是剧情对话（没有可识别文字），按 skip_dialogs 的方式点右上角跳过
            unknown += 1
            self.log_info("当前页面没有可识别的按钮，按剧情处理尝试跳过", notify=False)
            found = self.skip_dialogs(
                end_match=[map_re, "作战开始", "继续前进", "任务完成", "任务失败", "确认", "确认结算"],
                time_out=90,
                has_dialog=True,
                raise_if_not_found=False,
            )
            if (not found and unknown >= 2) or unknown >= 6:
                # 跳过剧情一直等到的是这里也处理不了的画面，别原地转圈，交回给 ensure_map 走别的恢复方式
                self.debug_shot("resume_unknown", boxes)
                return False
        return False

    # ------------------------------------------------------------------ 推一章：反复整章扫，直到一遍下来什么都没推
    def clear_chapter(self):
        """
        推完当前章节。不靠「进度游标」推断哪些关处理过，每一遍都只看画面：
        1. 回章节起点，从左往右整章扫一遍：卡片右上有对勾 = 已通关，直接跳过（不点面板）；
           没对勾的点开面板：能挑战/观看就打，未解锁就先放着；
        2. 这一遍推过任何关，就再从头扫一遍（推过的关可能解锁了任何位置的支线）；
        3. 一遍下来一关都没推 = 本章推完（不动点）；剩下没对勾的都是未解锁的。
        同一关最多打两次（打完还没对勾说明识别或战斗有问题，别死循环）。
        画面上看不到关卡（剧情、结算、章节选择页、弹窗……）一律交给 ensure_map 回到地图，不当成错误。
        :return: (本章推进的关数, 剩下未解锁的关卡名列表)
        """
        attempts = Counter()
        total = 0
        locked = []
        for pass_no in range(1, CHAPTER_MAX_PASSES + 1):
            played, locked = self.chapter_pass(attempts)
            total += played
            self.log_info(f"第 {pass_no} 遍扫完：推了 {played} 关，未解锁 {sorted(locked) or '无'}", notify=False)
            if played == 0:
                break
        medals = self.chapter_medals()
        if medals and medals[0] < medals[1]:
            self.log_info(
                f"本章勋章 {medals[0]}/{medals[1]}（有关卡没拿满挑战目标或还没解锁），未解锁 {sorted(locked) or '无'}",
                notify=True,
            )
        elif medals:
            self.log_info(f"本章勋章 {medals[0]}/{medals[1]}，全部拿到", notify=False)
        return total, sorted(locked)

    def finish_chapter(self):
        """
        推完当前章节，并用游戏自己的「章节进度」核对，不只信自己扫没扫全：
        扫到不动点后回章节选择页看百分比，不到 100% 就进回去再推一轮；某一轮一关都没推还是不到 100%，
        说明剩下的是没拿满的挑战目标或真没解锁的关，通知出来再继续（实录 2026-10-20 第 11、12.5 章：
        某一遍中途被弹回章节选择页、视野没回到右边就以为扫完了，漏了好几关）。
        :return: (推进的关数, 未解锁的关卡名)
        """
        total = 0
        locked = []
        idle = 0  # 连续几轮一关都没推
        for check in range(CHAPTER_VERIFY_ROUNDS):
            count, locked = self.clear_chapter()
            total += count
            percent = self.chapter_percent()
            if percent is None:
                self.log_info("章节选择页没读到「章节进度」，按扫描结果算本章推完", notify=True)
                break
            if percent >= 100:
                self.log_info(f"章节进度 100%，本章推完（本次推进 {total} 关）", notify=True)
                break
            idle = idle + 1 if count == 0 else 0
            if idle >= 2:
                self.log_info(
                    f"章节进度 {percent}%：连续两轮整章扫都没有能推的关了（未解锁 {locked or '无'}），"
                    f"剩下的多半是没拿满的挑战目标，继续下一章",
                    notify=True,
                )
                break
            self.log_info(f"章节进度只有 {percent}%，进回本章再扫一轮", notify=True)
            if not self.reenter_from_chapter_select():
                self.ensure_map()
        return total, locked

    def chapter_pass(self, attempts):
        """从章节起点往右扫一遍，推掉所有能推的关。返回 (这一遍推的关数, 这一遍看到的未解锁关卡名)。"""
        self.info_set("current_task", "从左到右推图")
        self.go_to_chapter_start()
        handled = set()  # 这一遍已经看过的关卡名（含 OCR 的别名）
        locked = set()
        locked_groups = []  # 这一遍判成未解锁的卡；推掉一关后放回去重看（本章是一关开一关时不用等下一遍）
        done = set()
        unknown_tries = Counter()
        played = 0
        for _ in range(PASS_MAX_STEPS):
            ordered = self.ensure_map()
            pending = [(card, group) for card, group in ordered if not (group & handled)]
            todo = []
            for card, group in pending:
                if has_clear_badge(self.frame, card, self.width, self.height):
                    handled.update(group)
                else:
                    todo.append((card, group))
            if not todo:
                # 屏幕上的都看过了：视野往右挪；连续两次挪不动才算这一遍扫到头（偶尔一次拖动/点击没生效）
                moved = self.scroll_map(1, ordered)
                if moved is None:
                    moved = self.scroll_map(1, self.ensure_map())
                if moved is None:
                    return played, locked - done
                continue
            card, group = todo[0]
            name = canonical_name(group) or "unknown"
            status, action = self.inspect_card(card, name)
            if status == "unknown" and unknown_tries[name] < 2:
                unknown_tries[name] += 1
                self.log_info(
                    f"{name} 面板上没读到挑战/观看按钮，关掉面板重读第 {unknown_tries[name]} 次", notify=False
                )
                self.close_map_panel()
                continue
            if status in ("challenge", "watch") and attempts[name] >= STAGE_MAX_ATTEMPTS:
                self.log_info(f"{name} 已经打过 {attempts[name]} 次还是没通关标记，这次推图不再打它", notify=True)
                status = "skip"
            if status not in ("challenge", "watch"):
                if status == "locked":
                    locked.add(name)
                    locked_groups.append(group)
                self.log_info(f"{name} {STATUS_TEXT.get(status, status)}", notify=False)
                handled.update(group)
                self.close_map_panel()
                continue
            attempts[name] += 1
            self.click(action, after_sleep=2)
            # 看完/打完游戏可能退回地图、章节选择页，甚至停在剧情或结算上；结束条件宽一点，剩下的交给 ensure_map
            if status == "challenge":
                self.auto_battle(
                    end_match=BACK_TO_MAP,
                    has_dialog=True,
                    need_click_auto=self.config.get("战斗内点击自动", False),
                )
            else:
                self.skip_dialogs(end_match=BACK_TO_MAP, raise_if_not_found=False)
            played += 1
            handled.update(group)
            done.update(group)
            for g in locked_groups:
                handled -= g - done
            locked_groups.clear()
            self.close_map_panel()
        raise Exception(f"一遍扫描超过 {PASS_MAX_STEPS} 步还没扫完, 请检查游戏画面")

    def ensure_map(self, tries=ENSURE_MAP_TRIES):
        """
        保证当前在选关地图上，返回扫描到的卡片。看不到关卡时按通用的顺序恢复：
        章节选择页 → 点确认进回去；部署/战斗/结算/剧情 → resume_battle 收尾；都不是 → ESC 关掉可能的弹层。
        实录 2026-10-20：看完第 11 章最后的剧情点 LS-1-7 后停在一个没有关卡卡片的画面，旧逻辑直接报错停了，
        右边下排的 LZ-1-4 / LZ-1-6 没推。
        """
        for attempt in range(tries):
            ordered = self.scan_maps()
            if ordered:
                return ordered
            self.log_info(f"画面上没有关卡卡片，尝试回到选关地图（第 {attempt + 1} 次）", notify=False)
            self.debug_shot("no_map_cards")
            if self.reenter_from_chapter_select():
                continue
            if self.resume_battle(time_out=300):
                continue
            self.back(after_sleep=2)
        ordered = self.scan_maps()
        if not ordered:
            raise Exception("回不到选关地图, 请检查游戏画面")
        return ordered

    def chapter_medals(self):
        """左下角本章勋章「63/69」。"""
        boxes = self.ocr(*MEDAL_BOX, match=medal_re) or []
        return parse_medals([b.name for b in boxes])

    def scroll_map(self, direction, ordered):
        """
        把视野往右（direction=1）或往左（-1）挪，返回挪完后的扫描结果；没挪动（已到头）返回 None。
        先用真实鼠标拖地图（一次能挪三四张卡）；拖了没动（PostMessage 模式拖不动，或已到头）再退回老办法：
        点最边上的卡片，游戏会把它滚到屏幕左边。
        挪到头的判断见 revealed_new。
        """
        y = MAP_DRAG_Y
        start, end = (0.75, 0.25) if direction > 0 else (0.25, 0.75)
        self.swipe_relative(start, y, end, y, duration=0.6)
        self.sleep(1)
        after = self.ensure_map()
        if revealed_new(ordered, after, direction):
            return after
        edge, group = ordered[-1] if direction > 0 else ordered[0]
        if direction > 0 and edge.x <= self.width * 0.55:
            return None  # 最右的卡片已经在屏幕左半边，右边没有了
        if direction < 0 and edge.x >= self.width * 0.45:
            return None  # 最左的卡片已经在屏幕中间，左边没有了
        self.click(edge, after_sleep=1.5)
        self.close_map_panel()
        after = self.ensure_map()
        return after if revealed_new(ordered, after, direction) else None

    def go_to_chapter_start(self):
        """一直往左挪视野，直到挪不动（到达章节起点）。"""
        self.info_set("current_task", "回到章节起点")
        ordered = self.ensure_map()
        for _ in range(40):
            ordered = self.scroll_map(-1, ordered)
            if ordered is None:
                return


def merge_maps(maps, x_threshold=40, y_threshold=40):
    merged = []  # 存最终的 map 对象
    merged_names = []  # 存每个合并组的所有 name

    for m in maps:
        for i, exist in enumerate(merged):
            if abs(m.x - exist.x) < x_threshold and abs(m.y - exist.y) < y_threshold:
                # 坐标取平均
                exist.x = int((exist.x + m.x) / 2)
                exist.y = int((exist.y + m.y) / 2)
                # 将当前 map 的名字加入该组
                merged_names[i].add(m.name)
                break
        else:
            merged.append(m)
            merged_names.append({m.name})  # 新组，名字放入 set

    return merged, merged_names
