import functools
import os
import re
import sys
import threading
import time
import traceback
from difflib import SequenceMatcher

from ok import BaseTask, Box, Logger, TaskDisabledException, TriggerTask, find_boxes_by_name

from src.core.base_mixin.lineup_mixin import LineupMixin
from src.core.base_mixin.runtime_mixin import RuntimeMixin
from src.core.debug_config import DEBUG_OPTION_NAME, KEY_DEBUG_SHOT
from src.core.debug_shot import save_debug_shot
from src.core.lineup_config import (
    LINEUP_OPTION_NAME,
    preset_name_for_kind,
    support_enabled_for_kind,
)
from src.core.lineup_plan import deploy_count_from_boxes, parse_count_text
from src.core.stamina_config import KEY_AUTO_POTION, STAMINA_OPTION_NAME
from src.core.support_select import (
    BUTTON_BOX,
    COUNT_BOX,
    NAME_BOX,
    PANEL_BOX,
    SUPPORT_COUNT_BOX,
    SUPPORT_TAB_BOX,
    SUPPORT_TAB_XY,
    TAB_BOX,
    TUTORIAL_BOX,
    AvatarBook,
    fallback_empty_tiles,
    far_point,
    find_cards,
    find_deploy_tiles,
    find_tutorial_tile,
    find_unit_tags,
    identify_cards,
    in_start_button,
    is_orange_check,
    parse_support_count,
    read_badge,
    support_card_points,
    support_lv_re,
    support_point_candidates,
    tutorial_step,
    unit_tiles_from_tags,
)
from src.data.FeatureList import FeatureList as fL
from src.image.frame_processs import isolate_by_hsv_ranges
from src.image.hsv_config import HSVRange as hR
from src.interaction.ScreenPosition import ScreenPosition

logger = Logger.get_logger(__name__)
# 「物品详情」：实录 2026-10-20，真实输入下 skip_dialogs 点右上角会按到选关页面的货币「+」，弹出道具说明，ESC 关掉
pop_ups = ["点击空白处关闭", "点击屏幕任意位置继续", "点击任意位置继续", "新周期开启", "周期已重置", "物品详情"]
number_re = re.compile(r"^\d+$")
stamina_re = re.compile(r"^\d+/\d+")
# 关卡名：可选的字母前缀（SL-/BH-/今后其他组合）+ 章-关，如 3-1、SL-3-2、BH-3-4
map_re = re.compile(r"^[^\d\s]{0,4}\s*\d{1,2}\s*-\s*\d{1,2}\s*\*?$")
# 战斗中界面的标志：右下角「行动结束」或左上角「01/12 回合」计数
battle_ui_re = re.compile(r"行动结束|\d{1,2}\s*/\s*\d{1,2}\s*回合")
# 体力不足弹窗「情报拼图补充」：三个页签从左到右是 调度室储存、情报拼图道具、坍塌晶条
challenge_button_re = re.compile(r"^挑战?$")  # 选关面板右下角的「挑战」按钮，实机偶尔只 OCR 出一个字
stamina_popup_re = re.compile(r"情报拼图补充|情报.{0,3}补充|体力不足|体力补充")
# 活动剧情里的特殊演出页（实录 2026-10-22 密米尔的返演·下篇 PS-1-7）：「掩码列表 / 演算完成」只有一个「终止覆写」按钮，
# 点了是「终止码演算」文字页，底部「点击空白处继续」字很淡 OCR 读不到。剧情的跳过点不掉，要专门点
story_exit_re = re.compile(r"^终止覆写$")
story_blank_re = re.compile(r"^终止码演算$|点击空白处继续")
# 加载页每看到一次，skip_dialogs 的超时至少顺延到这么多秒以后。要比一次取帧可能卡住的时间长：加载页画面不动，
# WGC 不出新帧，next_frame 会卡 10 秒以上（实录 2026-10-22 两次「资源加载中」页 30 秒超时，顺延 5 秒等于没顺延）
LOADING_EXTEND = 30
# 弹窗说明里出现这些字样，说明当前页签会消耗抽卡资源，绝不能点确认
# 第三页签是坍塌晶条（抽卡资源），绝不能用；第二页签「消耗接入密钥兑换」是正常的体力道具，
# 所以禁用词里不能有「兑换」
forbidden_restore_re = re.compile(r"晶条|晶体|钻石|购买|充值|付费")
STAMINA_TAB_DY = 0.14  # 页签行相对弹窗标题中心的垂直偏移，单位：画面高度
STAMINA_TAB_DX = 0.161  # 相邻页签中心的水平间距，单位：画面高度
STAMINA_SAFE_TABS = (0, 1)  # 只允许点前两个页签（储存、道具），第三个是坍塌晶条
PRESET_BOX = (0.75, 0.06, 0.995, 0.86)  # 「使用整备室配置」下拉框及其展开的编队列表
PRESET_HEADER_Y = 0.12  # 下拉框标题在这条线以上，展开后的「整备室配置」选项在以下
PRESET_HEADER_MIN_X = 0.77  # 下拉框标题文字从 x≈0.80 开始
MAX_CONTINUE_STREAK = 8  # 连续点「继续前进」却没进入战斗的次数上限
WATCHDOG_TIMEOUT = 120  # 秒：这么久没有任何进展（没点击、没日志、没换阶段）看门狗就截图报警
WATCHDOG_KILL_LEVEL = 2  # 停滞达到 WATCHDOG_TIMEOUT 的这个倍数、而且不是人为暂停，就自动停止任务
TAB_FALLBACK_XY = {"我的人形": (0.815, 0.039), "好友助战": (0.902, 0.039)}  # 页签 OCR 偶尔漏读时按固定位置点
# 游戏启动后的「资源更新完毕，需要重新启动游戏」提示框（实录 2026-10-20，游戏热更新当天第一次启动）
restart_required_re = re.compile(r"重新启动游戏|重启游戏|需要重启")
GAME_RESTART_TITLE_TIMEOUT = 120  # 秒：重新拉起游戏后等标题页「点击开始」的时间（实机：启动到标题约 50 秒）
GAME_EXIT_TIMEOUT = 20  # 秒：点「确认」后等游戏自己退出的时间，超过就直接结束进程
# 竞技场打完后的通知框 / 结算页（实录 2026-10-20）
rank_up_notice_re = re.compile(r"晋升至|段位可获得|补给将通过邮件发放")  # 「您已晋升至新锐·三」段位晋升通知，ESC 能关
battle_result_re = re.compile(r"^对战(胜利|失败)$|已结束$")  # 「对战胜利 / 对战失败」结算页只有「确认」能关
# 每个任务开始前的隐藏步骤「确保游戏已进入主页」
title_start_re = re.compile(r"点击开始")
story_skip_re = re.compile(r"跳过")  # 剧情对话右上角的「跳过 / 全部跳过」（可能和「自动」连成一个框）
main_marks = ["整备室", "公共区", "活动层", re.compile("招募")]  # 主页右侧的入口文字  # 标题页底部的「点击开始」
GAME_LAUNCH_MAIN_TIMEOUT = 150  # 秒：从拉起游戏到进入主页的上限（实机：启动到标题约 50 秒，再加公告弹窗）
GAME_FRESH_SECONDS = 180  # 秒：游戏进程比这更新，就当成刚被框架拉起、还停在启动/标题页，要走一遍进主页
GAME_CRASH_RETRIES = 3  # 一次任务里游戏进程中途没了（崩溃/被关）时，重新拉起再从头跑的次数上限
GAME_ALIVE_CHECK_INTERVAL = 10  # 秒：next_frame 里隔这么久查一次游戏进程还在不在


class GameCrashed(Exception):
    """任务跑到一半游戏进程没了。"""


class BattleLost(Exception):
    """战斗结算是「任务失败」。"""


# 真的失败结算页底部有「重新挑战 / 战斗重演(9) / 确认」；战斗中途红色特效偶尔会被 OCR 读成「任务失败」
# （实录 2026-10-21 16.0 章英雄难度 HZ-1-4：读到「任务失败」当打输跳过了，其实这关后来打赢了）
failure_page_re = re.compile(r"重新挑战|战斗重演")


def _with_game_started(run):
    """给任务的 run 套一层：先 ensure_game_started（游戏没开就拉起、标题页点进主页），再跑任务本身。"""

    @functools.wraps(run)
    def wrapped(self, *args, **kwargs):
        # 实录 2026-10-22：往期活动推图时挪了一下游戏窗口，游戏崩溃退出，脚本对着失效的窗口句柄一直空点。
        # 跑到一半游戏进程没了：重新拉起游戏、进主页，再从头跑一遍任务（推图类任务会自己找回进度）。
        for attempt in range(GAME_CRASH_RETRIES + 1):
            self.crash_resume = attempt > 0  # 崩溃后重跑：任务可以沿用这次已经做完的进度
            try:
                self.ensure_game_started()
                return run(self, *args, **kwargs)
            except TaskDisabledException:
                raise
            except Exception as e:
                if attempt >= GAME_CRASH_RETRIES or not self._game_gone():
                    raise
                self.log_info(f"游戏进程没了（崩溃或被关闭，{type(e).__name__}），重新拉起游戏后从头接着跑", notify=True)

    wrapped._ensures_game = True
    return wrapped


def box_center(box):
    return box.x + box.width / 2, box.y + box.height / 2


def stamina_tab_points(title_box, height):
    """由弹窗标题位置推算三个页签的中心点，顺序与游戏内一致：储存、道具、晶条。"""
    cx, cy = box_center(title_box)
    y = cy + STAMINA_TAB_DY * height
    return [(cx + (i - 1) * STAMINA_TAB_DX * height, y) for i in range(3)]


def has_forbidden_restore_text(names):
    """说明文字里提到晶条/购买等字样时返回 True。"""
    return any(forbidden_restore_re.search(n) for n in names)


def popup_texts(boxes, title_box, height):
    """只取弹窗范围内（标题下方约半屏高、左右各 0.42 画面高）的文字。"""
    cx, cy = box_center(title_box)
    out = []
    for b in boxes:
        bx, by = box_center(b)
        if cy < by < cy + 0.5 * height and abs(bx - cx) < 0.42 * height:
            out.append(b.name)
    return out


def watchdog_message(stalled, executor_paused, task_paused, where, window_hidden=False):
    """看门狗报警文案：先区分是游戏窗口被最小化、人为暂停，还是真卡住。"""
    secs = int(stalled)
    if task_paused:
        return f"任务已暂停 {secs} 秒（任务卡片上的「暂停」按钮），点「开始」继续"
    if executor_paused and window_hidden:
        return f"游戏窗口被最小化或移出了屏幕，程序已暂停 {secs} 秒；把游戏窗口恢复出来就会自动继续（被别的窗口挡住没关系，不能最小化）"
    if executor_paused:
        return f"程序已暂停 {secs} 秒（F9 热键或顶部的暂停按钮），按 F9 或点「开始」继续"
    return f"{secs} 秒没有任何进展，卡在 {where}"


def describe_screen(names):
    """根据整屏 OCR 文字猜当前在哪个页面，给超时/报警信息用。"""
    text = " ".join(names)
    if stamina_popup_re.search(text):
        return "体力弹窗"
    if "任务失败" in text:
        return "任务失败页"
    if "继续前进" in text or "任务完成" in text:
        return "结算页"
    if "作战开始" in text:
        return "部署界面"
    if battle_ui_re.search(text):
        return "战斗中"
    if any(map_re.match(n) for n in names):
        return "选关页面"
    return "未知页面"


def stamina_value(boxes, height):
    """右上角「69/240」里当前体力的数值；读不到返回 None。"""
    for b in boxes:
        if b.y < 0.1 * height and (m := stamina_re.match(b.name.replace(" ", ""))):
            return int(m.group(0).split("/")[0])
    return None


def tab_count(boxes, tab_x, tab_y, height):
    """读页签图标下方的数量数字；识别不到返回 None。"""
    for b in boxes:
        bx, by = box_center(b)
        if abs(bx - tab_x) < 0.06 * height and tab_y < by < tab_y + 0.1 * height and number_re.match(b.name):
            return int(b.name)
    return None


def parse_time_option(option: str) -> list[float]:
    """
    将配置中的时间字符串解析为浮点数列表
    例如 "1.087-1.4-0.5" -> [1.087, 1.4, 0.5]
    """
    return [float(x) for x in option.split("-")]


must_deploy_re = re.compile(r"至少需要出击")
# 作战页顶部的导航页签：出现说明在章节选择 / 模拟作战等导航页，没有剧情可跳。
# 实录 2026-10-20：看完 SL-10-6 剧情退回章节选择页，skip_dialogs 点右上角「跳过」的位置正好是「模拟作战」页签
nav_tabs_re = re.compile(r"剧情战役|往期活动|补给作战|模拟作战|Supply\s*Missions")
chapter_select_re = re.compile(r"^章节进度$")


def battle_over_on_map(results):
    """等结算时等到的是选关页面的关卡名或章节选择页：战斗已经结束（结算页被点过去了），不用再点任何东西。"""
    return bool(results) and any(map_re.match(r.name) or chapter_select_re.match(r.name) for r in results)


def parse_deploy_count(text):
    """「3/4」→ (3, 4)，容错见 lineup_plan.parse_count_text。"""
    return parse_count_text(text)


ZILV_GRAY_GAP = 25  # 自律按钮比同一帧的挑战按钮暗这么多（灰度均值）就当它是灰色未解锁


def region_mean_gray(frame, box):
    """frame(BGR ndarray) 里 box 范围的灰度均值；frame 为空或 box 越界返回 None。"""
    if frame is None or box is None:
        return None
    h, w = frame.shape[:2]
    x0, y0 = max(0, int(box.x)), max(0, int(box.y))
    x1, y1 = min(w, int(box.x + box.width)), min(h, int(box.y + box.height))
    if x1 <= x0 or y1 <= y0:
        return None
    region = frame[y0:y1, x0:x1]
    if region.ndim == 3:
        region = region.mean(axis=2)
    return float(region.mean())


def zilv_locked(zilv_gray, challenge_gray, gap=ZILV_GRAY_GAP):
    """
    自律按钮是否灰色（未解锁）。用同一帧里「挑战」按钮做参照，整体亮度变化（遮罩/截图偏暗）不影响判断。
    实录 tests/fixtures/zilv_locked_1280x768.png：灰自律 ≈135，白挑战 ≈177。
    任一值缺失返回 None（不知道）。
    """
    if zilv_gray is None or challenge_gray is None:
        return None
    return challenge_gray - zilv_gray >= gap


class BaseGfTask(LineupMixin, RuntimeMixin, BaseTask):
    """任务基类：RuntimeMixin 提供模板匹配入口重写，BaseTask 提供框架能力。"""

    def __init_subclass__(cls, **kwargs):
        # 所有任务的 run 都自动先过一遍 ensure_game_started（界面上不显示这一步）
        super().__init_subclass__(**kwargs)
        run = cls.__dict__.get("run")
        if run is not None and not getattr(run, "_ensures_game", False):
            cls.run = _with_game_started(run)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.roles_dict = {
            "物理": [
                "夏安",
                "莱妮",
                "威玛西娜",
                "巴希达",
                "幼熙",
                "绯",
                "波波沙",
                "乌尔丽德",
                "莉塔拉",
                "黛烟",
                "维普蕾",
                "闪电",
            ],
            "燃烧": [
                "罗蕾莱",
                "樱花",
                "刘易斯",
                "秋桦",
                "佩莉",
                "维克托",
                "桑朵莱希",
                "科谢尼娅",
                "琼玖",
                "奇塔",
                "夏克里",
                "克罗丽科",
            ],
            "电导": ["莱娅", "安朵丝", "比悠卡", "绛雨", "莱娜", "莫辛纳甘"],
            "冷凝": ["海伦", "埃芙", "洛贝拉", "杜莎妮", "索米", "洛塔", "玛绮朵"],
            "浊刻": ["芙洛伦", "妮基塔", "春田", "朝晖", "塞布丽娜", "托洛洛", "寇尔芙"],
            "酸蚀": ["翡图萨", "哈卜茜", "琳德", "米什缇", "可露凯", "纳甘", "佩里缇亚", "纳美西丝"],
        }
        self.box = ScreenPosition(self)
        self.default_config_group = {}

        # 多账户：是否允许按账号覆盖本任务的配置（「账号配置」页据此列出任务）。
        # 用 getattr 读类属性，这样子类可以直接在类体里声明而不会被 __init__ 覆盖掉。
        self.support_multi_account = bool(getattr(self, "support_multi_account", False))
        self.account_config_blacklist = set(getattr(self, "account_config_blacklist", ()))
        self.account_config_whitelist = set(getattr(self, "account_config_whitelist", ()))
        self.account_config_defaults = dict(getattr(self, "account_config_defaults", {}))

    def debug_shot(self, tag, boxes=None):
        """
        保存调试截图到 screenshots/<任务名>/<日期>/，由设置页全局「调试」里的「调试截图」开关控制，对所有任务生效。
        :param tag: 文件名标签，说明当前阶段
        :param boxes: 需要画框标注的 Box 列表，可选
        """
        if not self.debug_shot_enabled():
            return None
        try:
            return save_debug_shot(self.frame, self.name, tag, boxes)
        except Exception as e:
            self.log_debug(f"调试截图失败: {e}")
            return None

    # ------------------------------------------------------------------ 看门狗
    _progress_ts = 0.0
    _watchdog_stop_event = None

    _last_frame = None
    _paused_by_window = False

    def _touch_progress(self):
        self._progress_ts = time.time()
        try:
            executor = self.executor
        except AttributeError:  # 还没绑定执行器（单测桩、初始化早期）
            return
        frame = getattr(executor, "_frame", None)
        if frame is not None:
            self._last_frame = frame

    def _game_window_hidden(self):
        """游戏窗口被最小化/移出屏幕（ok-script 这时会暂停执行器，而且窗口恢复后不会自己继续）。"""
        hw = getattr(getattr(self.executor, "device_manager", None), "hwnd_window", None)
        return hw is not None and not getattr(hw, "pos_valid", True)

    def _resume_if_window_back(self):
        """
        实录：游戏窗口被最小化时 ok-script 会把执行器暂停并弹「Paused because game window is minimized」，
        但窗口恢复后它不会自动继续，任务看起来像"自己结束了"。这里记住暂停是窗口引起的，窗口一回来就自动继续。
        """
        executor_paused = bool(getattr(self.executor, "paused", False))
        if executor_paused and self._game_window_hidden():
            self._paused_by_window = True
            return
        if (
            self._paused_by_window
            and executor_paused
            and not getattr(self, "_paused", False)
            and not self._game_window_hidden()
        ):
            logger.info("[看门狗] 游戏窗口恢复了，自动继续被最小化打断的任务")
            self._paused_by_window = False
            self.executor.start()
            self._touch_progress()
        elif not executor_paused:
            self._paused_by_window = False

    def log_info(self, message, notify=False, *args, **kwargs):
        self._touch_progress()
        return super().log_info(message, notify, *args, **kwargs)

    def info_set(self, key, value):
        self._touch_progress()
        return super().info_set(key, value)

    def start_watchdog(self, timeout=WATCHDOG_TIMEOUT):
        """
        起一个独立线程盯着任务：超过 timeout 秒没有任何进展就截图、记下执行线程卡在哪一行并弹通知；
        不是人为暂停、又停滞到 WATCHDOG_KILL_LEVEL 倍超时，就自动停止任务，不让它无限转下去。
        """
        self.stop_watchdog()
        self._touch_progress()
        self._watchdog_stop_event = threading.Event()
        threading.Thread(
            target=self._watchdog_loop,
            args=(timeout, self._watchdog_stop_event),
            name=f"watchdog-{self.__class__.__name__}",
            daemon=True,
        ).start()

    def stop_watchdog(self):
        if self._watchdog_stop_event is not None:
            self._watchdog_stop_event.set()
            self._watchdog_stop_event = None

    def _watchdog_loop(self, timeout, stop_event):
        reported = 0
        while not stop_event.wait(5):
            try:
                self._resume_if_window_back()
                stalled = time.time() - self._progress_ts
                if stalled < timeout:
                    reported = 0
                    continue
                level = int(stalled // timeout)
                if level <= reported:
                    continue
                reported = level
                self._watchdog_report(stalled, level)
            except Exception as e:
                logger.warning(f"看门狗出错: {e}")

    def _executor_where(self):
        """执行线程当前的 Python 调用栈（最内层在前），用来判断卡在哪。"""
        ident = getattr(getattr(self.executor, "thread", None), "ident", None)
        frame = sys._current_frames().get(ident) if ident else None
        if frame is None:
            return "未知位置"
        stack = traceback.extract_stack(frame)[-8:]
        return " <- ".join(f"{os.path.basename(f.filename)}:{f.lineno} {f.name}" for f in reversed(stack))

    def _watchdog_report(self, stalled, level):
        executor_paused = bool(getattr(self.executor, "paused", False))
        task_paused = bool(getattr(self, "_paused", False))
        where = self._executor_where()
        msg = watchdog_message(
            stalled, executor_paused, task_paused, where, self._game_window_hidden() or self._paused_by_window
        )
        path = None
        try:
            frame = getattr(self.executor, "_frame", None)
            path = save_debug_shot(frame if frame is not None else self._last_frame, self.name, f"watchdog_{level}")
        except Exception as e:
            logger.warning(f"看门狗截图失败: {e}")
        logger.warning(f"[看门狗] {msg}；截图 {path}")
        if level == 1 or not (executor_paused or task_paused):
            # 暂停状态只在第一次提醒一次，别每两分钟弹一回
            try:
                self.notification(msg, error=True, tray=True)
            except Exception as e:
                logger.warning(f"看门狗通知失败: {e}")
        if not executor_paused and not task_paused and level >= WATCHDOG_KILL_LEVEL:
            logger.error(f"[看门狗] 持续 {int(stalled)} 秒无进展，自动停止任务")
            self.info["Error"] = f"{int(stalled)} 秒没有进展，看门狗已停止任务，看日志里的 [看门狗] 和 watchdog 截图"
            self.disable()

    def debug_shot_enabled(self):
        try:
            return bool(self.get_global_config(DEBUG_OPTION_NAME).get(KEY_DEBUG_SHOT, True))
        except Exception:
            return True

    def isolate_by_hsv_ranges(self, frame, ranges, invert=True, kernel_size=2):
        """
        :param frame: 输入图像（BGR）
        :param ranges: HSV 区间列表
        :param invert: 是否反转结果
        :param kernel_size: 形态学核大小

        作用：按 HSV 范围提取颜色区域。
        """
        return isolate_by_hsv_ranges(frame, ranges, invert, kernel_size)

    def make_hsv_isolator(self, ranges, invert=True, kernel_size=2):
        """返回一个可直接调用的 HSV 过滤函数"""
        return lambda frame: isolate_by_hsv_ranges(
            frame,
            ranges,
            invert=invert,
            kernel_size=kernel_size,
        )

    def get_role_by_name(self, name):
        return next((k for k, v in self.roles_dict.items() if name in v), None)

    def ensure_main(self, recheck_time=1, time_out=30, esc=True, loading_grace=120):
        """
        回到主页。超时后如果画面还是加载页（NOW LOADING / 移动中 / 资源加载中），超时顺延，
        最多多等 loading_grace 秒（实录：离开活动层的「艾莫号 移动中…69%」加载页把 60 秒耗光，任务被判失败）。
        """
        self.info_set("current_task", "go_to_main")
        deadline = time.time() + time_out
        hard_deadline = deadline + loading_grace
        extended = False
        self._deadline_bump = 0
        while True:
            if self.is_main(recheck_time=recheck_time, esc=esc):
                return True
            if self._deadline_bump:
                # is_main 里刚重启过游戏，从现在起重新计时
                deadline = time.time() + max(time_out, self._deadline_bump)
                hard_deadline = deadline + loading_grace
                self._deadline_bump = 0
            now = time.time()
            if now >= deadline:
                self.next_frame()
                if now < hard_deadline and self._is_loading_frame(self.ocr()):
                    if not extended:
                        self.log_info("画面还在加载中（移动中/资源加载中），回主页的超时顺延", notify=False)
                        extended = True
                    deadline = now + 10
                else:
                    self.debug_shot("ensure_main_timeout")
                    raise Exception("请从游戏主页进入")
            self.sleep(recheck_time)

    def skip_dialogs(
        self, end_match, end_box=None, time_out=120, has_dialog=True, raise_if_not_found=True, loading_grace=120
    ):
        """
        跳过剧情/对话，直到出现 end_match。画面是加载页（资源加载中 xx% 等）时超时顺延，最多多等 loading_grace 秒
        （实录 2026-10-21 15.0 章：打完 VA-1-12 回地图的「资源加载中 30%」停了 30 多秒，推图被判超时停掉）。
        """
        self.info_set("current_task", "skip_dialogs")
        start = time.time()
        deadline = start + time_out
        hard_deadline = deadline + loading_grace
        attempts = 0
        next_debug_shot = 30
        boxes = []
        while time.time() < deadline:
            if time.time() - start > next_debug_shot:
                # 长时间没匹配到结束条件，留一张图方便排查卡在什么页面
                self.debug_shot("skip_dialogs_waiting")
                next_debug_shot += 30
            try:
                boxes = self.ocr()
            except AttributeError:
                self.log_info("WGC 抓帧返回空帧，等待 3s 后重试", notify=False)
                self.sleep(3)
                self.next_frame()
                continue
            if skip := self.find_boxes(boxes, match=["跳过"]):
                self.click(skip, after_sleep=2)
            elif no_alert := self.find_boxes(boxes, match="今日不再提示"):
                self.click(no_alert)
                self.sleep(0.2)
                self.click(self.find_boxes(boxes, match="确认"), after_sleep=2)
            elif stamina_popup := self.find_boxes(boxes, match=stamina_popup_re):
                # 体力不足弹窗挡在「继续前进」前面时，OCR 仍能读到后面的按钮，必须先处理弹窗
                self._handle_stamina_popup(stamina_popup[0])
                # 弹窗关掉后游戏停在触发它的那一页：选关面板要再点一次「挑战」才会进部署界面
                # （「继续前进」在 end_match 里，返回后由 auto_battle 再点）
                self.next_frame()
                if challenge := self.ocr(0.5, 0.85, 1, 1, match=challenge_button_re):
                    self.log_info("体力恢复后重新点「挑战」", notify=True)
                    self.click(challenge[0], after_sleep=2)
            elif story_exit := self.find_boxes(boxes, match=story_exit_re):
                self.click(story_exit, after_sleep=2)
            elif self.find_boxes(boxes, match=story_blank_re):
                self.click_relative(0.5, 0.6, after_sleep=2)
            elif result := self.find_boxes(boxes, match=end_match, boundary=end_box):
                # 优先返回"继续前进"
                for r in result:
                    if r.name == "继续前进":
                        self.sleep(1)
                        return [r]
                self.sleep(1)
                return result
            elif self.find_boxes(boxes, match=pop_ups):
                self.back()
                self.sleep(1)
            elif self._dismiss_notice(boxes):
                pass
            else:
                # 战斗中界面右上角是加速/跳过回合图标，不是剧情跳过，不能点
                if self._is_battle_frame(boxes) or self._is_loading_frame(boxes):
                    # 游戏在打/在加载，不算卡住，喂一下看门狗
                    self._touch_progress()
                if self._is_loading_frame(boxes):
                    deadline = min(max(deadline, time.time() + LOADING_EXTEND), hard_deadline)
                if has_dialog and (self.find_boxes(boxes, match=map_re) or self.find_boxes(boxes, match=nav_tabs_re)):
                    # 实录 2026-10-20：选关页面右上角是货币和「+」，真实输入下乱点会弹出「物品详情」；
                    # 章节选择页右上角是「模拟作战」页签，乱点会跑进模拟作战。导航页上什么都别点
                    pass
                elif has_dialog and not self._is_loading_frame(boxes) and not self._is_battle_frame(boxes):
                    # 剧情跳过标签在 (0.95, 0.04)，教学弹窗的关闭 X 在 (0.967, 0.042)，交替点两处
                    if attempts % 2 == 0:
                        self.click_relative(0.95, 0.04)
                    else:
                        self.click_relative(0.967, 0.042)
                    attempts += 1
                self.sleep(2)
            self.next_frame()
        where = describe_screen([b.name for b in boxes])
        self.log_info(
            f"等 {time_out} 秒没等到 {end_match}，当前在{where}: {[b.name for b in boxes][:12]}", notify=False
        )
        self.debug_shot(f"skip_dialogs_timeout_{where}")
        if raise_if_not_found:
            raise Exception(f"跳过剧情超时! 当前在{where}")

    # ------------------------------------------------------------------ 好友助战
    def _ocr_panel(self, box, **kw):
        x, y, to_x, to_y = box
        return self.ocr(x, y, to_x, to_y, **kw)

    _avatar_book = AvatarBook()

    def _scan_cards(self):
        """
        识别右侧面板的卡片：战力数字定位卡片，蓝圈椎数用模板比对（OCR 认不出那么小的数字），
        立绘和 assets/card_avatars 里的模板比对直接认出是谁（认不出的 name 为 None，点一下后会自动学会）。
        """
        if self._fix_panel_state():
            self.next_frame()
        boxes = self._ocr_panel(PANEL_BOX, match=re.compile(r"^\d{3,6}$"))
        cards = find_cards(
            boxes,
            self.width,
            self.height,
            badge_of=lambda b: read_badge(self.frame, b, self.width, self.height, recognize=self._recognize_badge),
        )
        identify_cards(self.frame, cards, self.width, self.height, self._avatar_book)
        return cards

    def _recognize_badge(self, img):
        """椎数蓝圈的放大图只做 OCR 识别（不做检测），返回 (文字, 置信度)；OCR 不可用返回 (None, 0)。"""
        try:
            res = self.executor.ocr_lib().ocr(img, det=False, rec=True, cls=False)
            return res[0][0] if res and res[0] else (None, 0.0)
        except Exception as e:
            self.log_info(f"椎数 OCR 失败: {e}", notify=False)
            return None, 0.0

    @staticmethod
    def _name_like(a, b):
        """OCR 认名字偶尔错一个字（克莱妲/克兼妲），立绘模板按名字预筛时用模糊比较，宁可多点一下也别漏掉目标。"""
        if not a or not b:
            return False
        if a in b or b in a:
            return True
        return SequenceMatcher(None, a, b).ratio() >= 0.5

    def _learn_card(self, card, name):
        """点过卡片、OCR 到名字后，把它的立绘存成模板，下次扫描就不用再点。"""
        if self._avatar_book.learn(name, card.get("avatar")):
            self.log_info(f"记住了 {name} 的卡片立绘（assets/card_avatars/{name}.png）", notify=False)

    def _click_card(self, card):
        """点中一张卡片，返回左下角名字，并顺手学习立绘。"""
        x, y = card["center"]
        self.click_relative(x / self.width, y / self.height, after_sleep=0.8)
        self.next_frame()
        name = self._selected_role_name()
        self._learn_card(card, name)
        return name

    def _ensure_panel(self):
        """右侧卡片面板可能被点地图关掉了（页签消失），点「作战开始」左边的按钮把它打开。"""
        if self._ocr_panel(TAB_BOX, match=self.fix_match_regex(["我的人形", "好友助战", "可部署人形"])):
            return True
        self.log_info("部署面板没打开，点左下按钮打开", notify=False)
        self.click_relative(0.37, 0.915, after_sleep=1)
        self.next_frame()
        ok = bool(self._ocr_panel(TAB_BOX, match=self.fix_match_regex(["我的人形", "好友助战", "可部署人形"])))
        self.debug_shot("panel_open" if ok else "panel_open_fail")
        return ok

    def _lineup_cfg(self):
        return self.get_global_config(LINEUP_OPTION_NAME)

    def _preset_name(self):
        return preset_name_for_kind(self._lineup_cfg(), self._lineup_kind)

    def _support_enabled(self):
        return support_enabled_for_kind(self._lineup_cfg(), self._lineup_kind)

    def _preset_boxes(self):
        return self._ocr_panel(
            PRESET_BOX, match=[re.compile(r"编队\s*\d"), re.compile(r"整备室配置"), re.compile(r".{1,12}")]
        )

    @staticmethod
    def _preset_text_like(text, name):
        t = (text or "").replace(" ", "")
        return bool(name) and (name in t or (t in name and len(t) >= 2))

    def _preset_state(self):
        """下拉框区域 OCR：(全部, 标题行, 标题下方, 下方里的编队/整备室配置条目)。条目 >= 2 说明列表展开着。"""
        boxes = self._preset_boxes()
        # 地图上敌方单位的名字标签（实录：扩编实练的「徒从-0331」）会飘进面板左上角，标题只认下拉框里的文字
        header = [b for b in boxes if b.y < self.height * PRESET_HEADER_Y and b.x >= self.width * PRESET_HEADER_MIN_X]
        below = [b for b in boxes if b.y > self.height * PRESET_HEADER_Y]
        entries = [b for b in below if re.search(r"编队\s*\d", b.name) or "整备室配置" in b.name]
        return boxes, header, below, entries

    def _click_preset_header(self, header):
        if header:
            self.click(header[0], after_sleep=1)
        else:
            self.click_relative(0.878, 0.097, after_sleep=1)
        self.next_frame()

    def _collapse_preset_list(self, header, below, entries):
        """
        把展开着的编队列表收起来。游戏里点当前已选中的那一项不会收起（实录：已是编队1再点编队1，列表还开着），
        所以：想选的项已经是当前项就点标题收起；否则点那一项。还开着就选别的项再切回来（每次换选择都会收起）。
        """
        name = self._preset_name()
        key = name or "整备室配置"
        target = next((b for b in below if self._preset_text_like(b.name, key)), None)
        same = any(self._preset_text_like(h.name, key) for h in header)
        if same or target is None:
            self.log_info("面板上展开着编队列表，当前项就是要的，点标题收起", notify=True)
            self._click_preset_header(header)
        else:
            self.log_info(f"面板上展开着编队列表，选「{target.name}」收起", notify=True)
            self.click(target, after_sleep=1)
            self.next_frame()
        _, header, below, entries = self._preset_state()
        if len(entries) < 2:
            return True
        other = next((b for b in below if not self._preset_text_like(b.name, key)), None)
        if other is None:
            self.log_info("编队列表还开着，也没别的项可点", notify=True)
            return False
        if getattr(self, "_collapsing_preset", False):
            self.log_info("编队列表还开着，已经在兜底里了，不再递归", notify=True)
            return False
        self.log_info(f"编队列表还开着，先选「{other.name}」再切回「{key}」", notify=True)
        self.click(other, after_sleep=1)
        self.next_frame()
        if name:
            self._collapsing_preset = True
            try:
                self.apply_preset(name)
            finally:
                self._collapsing_preset = False
        _, _, _, entries = self._preset_state()
        return len(entries) < 2

    def _fix_panel_state(self):
        """
        「我的人形」页签顶上的「使用整备室配置」下拉框被误点会展开「编队1…编队7」列表。
        列表展开着就把它收起来。返回是否做了修正。
        """
        boxes, header, below, entries = self._preset_state()
        if len(entries) < 2:
            return False
        self.debug_shot("preset_fix", boxes)
        self._collapse_preset_list(header, below, entries)
        return True

    def apply_preset(self, name):
        """在「我的人形」页签的「使用整备室配置」下拉框里选中名为 name 的编队。返回是否选中。"""
        self._click_tab("我的人形")
        # 标题 OCR 偶尔漏读一帧（实录：已是编队1却没读到，白白展开了列表），多读两帧再决定
        for attempt in range(3):
            boxes, header, below, entries = self._preset_state()
            if any(self._preset_text_like(b.name, name) for b in header):
                if len(entries) >= 2:
                    self.log_info(f"当前已是编队「{name}」，但列表展开着，收起", notify=False)
                    self._collapse_preset_list(header, below, entries)
                else:
                    self.log_info(f"当前已是编队「{name}」", notify=False)
                return True
            if header or entries:
                break
            self.sleep(0.4)
            self.next_frame()
        if len(entries) < 2:
            self._click_preset_header(header)
            boxes, header, below, entries = self._preset_state()
        picks = [b for b in below if self._preset_text_like(b.name, name)]
        self.debug_shot("preset_list", boxes)
        if not picks:
            self.log_info(f"编队列表里没找到「{name}」: {[b.name for b in boxes]}，不切编队", notify=True)
            self._fix_panel_state()
            return False
        self.click(picks[0], after_sleep=1.5)
        self.next_frame()
        boxes, header, below, entries = self._preset_state()
        if len(entries) >= 2:
            self.log_info("点了编队后列表没收起，点标题收起", notify=False)
            self._click_preset_header(header)
            boxes, header, below, entries = self._preset_state()
        ok = any(self._preset_text_like(b.name, name) for b in header)
        self.debug_shot("preset_applied", boxes)
        self.log_info(
            f"已切到编队「{name}」，阵容 {self._deploy_count()}"
            if ok
            else f"点了编队「{name}」但标题没变: {[b.name for b in header]}",
            notify=True,
        )
        return ok

    def _deploy_count(self):
        """顶部「部署人形 3/4」，返回 (3, 4)；读不到就换一帧再试一次，还读不到返回 None。"""
        for attempt in range(2):
            boxes = self._ocr_panel(COUNT_BOX)
            self.log_info(f"顶部计数区文字: {[b.name for b in boxes]}", notify=False)
            if m := deploy_count_from_boxes(boxes):
                return m
            self.sleep(0.3)
            self.next_frame()
        return None

    def _click_tab(self, name):
        """点「我的人形 / 好友助战」页签。OCR 偶尔漏读（实录：页签明明在却没认出来），多读几帧，再不行按固定位置点。"""
        for attempt in range(3):
            if name == "我的人形" and (single := self._ocr_panel(TAB_BOX, match=self.fix_match_regex(["可部署人形"]))):
                # 扩编实练等没有好友助战的关卡：面板只有「可部署人形」一页，布局同「我的人形」，不用切
                return single[0]
            tab = self._ocr_panel(TAB_BOX, match=self.fix_match_regex([name]))
            if tab:
                self.click(tab[0], after_sleep=1)
                self.next_frame()
                return tab[0]
            self.sleep(0.5)
            self.next_frame()
        xy = TAB_FALLBACK_XY.get(name)
        if xy is None:
            raise Exception(f"部署界面没找到「{name}」页签")
        self.log_info(f"页签「{name}」OCR 没认出来，按固定位置点", notify=True)
        self.debug_shot(f"tab_fallback_{name}")
        self.click_relative(xy[0], xy[1], after_sleep=1)
        self.next_frame()
        return Box(int(xy[0] * self.width) - 35, int(xy[1] * self.height) - 10, 70, 20, name=name)

    def _selected_role_name(self):
        """左下角当前选中人形的名字，去掉等级后缀，如 '莱娅Lv.60格' -> '莱娅'。"""
        boxes = self._ocr_panel(NAME_BOX)
        raw = "".join(b.name for b in boxes)
        name = re.split(r"L[vV]", raw)[0].strip()
        self.log_info(f"左下角人形名: {raw!r} -> {name!r}", notify=False)
        return name

    def _unit_tiles(self):
        """地图上已上场单位所在的格子：编号标签下方的格子优先，再用填充率低（被立绘挡住）的地格兜底。"""
        occupied, _ = self._occupied_and_empty()
        out = [(c, f"标签下的地格({int(c[0])},{int(c[1])})") for c in occupied]
        for t in reversed(find_deploy_tiles(self.frame, self.width, self.height)):
            if all((t["center"][0] - x) ** 2 + (t["center"][1] - y) ** 2 >= 45**2 for (x, y), _ in out):
                out.append((t["center"], f"地格({int(t['center'][0])},{int(t['center'][1])}, 填充 {t['fill']})"))
        return [(c, d) for c, d in out if not in_start_button(c, self.width, self.height)][:6]

    def _select_unit_on_map(self, want):
        """点地图上的单位格子，直到左下角名字是 want。点中单位后右侧面板会切回「我的人形」。"""
        for tile, desc in self._unit_tiles():
            self.click_relative(tile[0] / self.width, tile[1] / self.height, after_sleep=0.8)
            self.next_frame()
            if want in self._selected_role_name() and self._deploy_button()[0] == "withdraw":
                self.log_info(f"在地图上选中了 {want}（{desc}）", notify=False)
                return True
            self._clear_selection()
        return False

    def _deploy_button(self):
        """右下角按钮：("deploy", box) 部署人形 / ("withdraw", box) 撤回人形 / ("hint", box) 请点击地格 /
        ("swap", box) 编入队伍（顶替地图上选中的单位）/ ("blocked", box) 无法部署 / (None, None)。"""
        boxes = self._ocr_panel(BUTTON_BOX)
        self.log_info(f"右下角按钮: {[b.name for b in boxes]}", notify=False)
        for b in boxes:
            if re.fullmatch(r"\s*部署人形\s*", b.name):
                return "deploy", b
            if re.fullmatch(r"\s*编入队伍\s*", b.name):
                # 地图上还选中着一个单位时点卡片，按钮变成「编入队伍」= 用这张卡顶替选中的单位
                # （实录：刚部署完的助战还处于选中状态，补人时把助战顶掉了），要先取消选中
                return "swap", b
            if re.fullmatch(r"\s*撤回人形\s*", b.name):
                return "withdraw", b
        for b in boxes:
            if "地格" in b.name or "拖拽" in b.name:
                return "hint", b
            if "无法" in b.name:
                # 「无法在该点位部署」「该人形无法撤回」：地图上还挂着上一次点的格子/单位，要先取消选中
                return "blocked", b
        return None, None

    def _clear_selection(self):
        """点一下地图上离地格很远的空地，取消地图上挂着的格子/单位选中（否则后面点卡片会变成「无法在该点位部署」）。"""
        tiles = find_deploy_tiles(self.frame, self.width, self.height)
        x, y = far_point(tiles, self.width, self.height)
        self.click_relative(x, y, after_sleep=0.8)
        self.next_frame()
        kind, _ = self._deploy_button()
        self.log_info(f"取消地图选中（点 {x:.2f},{y:.2f}），按钮状态 {kind}", notify=False)
        return kind not in ("withdraw", "blocked")

    def _occupied_and_empty(self):
        """(有人的地格列表, 空地格列表)：有人的按编号标签定位，空的用菱形模板找并排除标签附近的。"""
        tags = find_unit_tags(self.frame, self.width, self.height)
        occupied = unit_tiles_from_tags(tags, self.height, self.width)
        tiles = find_deploy_tiles(self.frame, self.width, self.height)
        near = lambda t: any((t["center"][0] - x) ** 2 + (t["center"][1] - y) ** 2 < 45**2 for x, y in occupied)
        empty = [t for t in tiles if not near(t)]
        self.log_info(
            f"单位标签 {[(x, y, sc) for x, y, sc in tags]}，空地格 {[(t['center'], t['fill']) for t in empty]}",
            notify=False,
        )
        return occupied, empty

    def _candidate_tiles(self):
        """
        选中卡片后可以试着点的地格：阵容没满就点空地格（填充率高的在前）；满了（顶替）就点有人的格子。
        """
        count = self._deploy_count()
        occupied, empty = self._occupied_and_empty()
        self.debug_shot("tiles")
        full = count is not None and count[0] >= count[1]
        if full:
            out = [(c, f"有人的地格({int(c[0])},{int(c[1])})") for c in occupied]
        else:
            # 刚撤人空出来的格子最可靠（前后两帧对比找的），排最前
            out = [((x, y), f"刚空出的地格({int(x)},{int(y)})") for x, y in (self._freed_tiles or [])]
            out += [
                (t["center"], f"空地格({int(t['center'][0])},{int(t['center'][1])}, 填充 {t['fill']})") for t in empty
            ]
            extra = fallback_empty_tiles(self.frame, self.width, self.height, [c for c, _ in out], occupied)
            out += [(c, f"兜底地格({int(c[0])},{int(c[1])})") for c in extra]
        out = [(c, d) for c, d in out if not in_start_button(c, self.width, self.height)]
        self.log_info(f"阵容 {count}，候选地格 {len(out)} 个", notify=False)
        return out[:6]

    def _placed(self, card_name, before):
        """核对是否上场：按钮是「撤回人形」且左下角名字就是这张卡，或者计数涨了。"""
        kind, _ = self._deploy_button()
        if kind == "withdraw" and card_name and card_name in self._selected_role_name():
            return True
        after = self._deploy_count()
        return before is not None and after is not None and after[0] > before[0]

    def _place_selected(self, label, card_name, before=None, reselect=None):
        """
        当前已选中一张卡片（我的人形或好友助战），把它放到场上：
        - 按钮已是「撤回人形」且左下角名字就是它：已在场上；
        - 「请点击地格」：逐个试点地格。点到空格会出现「部署人形」再点一下；
          阵容满时点有人的格子会直接顶替（按钮变「撤回人形」且名字变成它）；
          点到别的单位只是选中了那个单位，面板会切回「我的人形」，所以试下一个格子前要用 reselect 重新选卡。
        :param card_name: 这张卡的名字，用来核对是否真的上场
        :param before: 部署前的 (n, m) 计数
        :param reselect: 重新选中这张卡片的函数（含切回对应页签）
        """
        kind, button = self._deploy_button()
        if kind == "withdraw" and card_name in self._selected_role_name():
            self.log_info(f"{label} 已在场上", notify=True)
            return True
        if kind in ("withdraw", "blocked", "swap") and reselect:
            # 地图上还挂着别的格子/单位，先取消再重选这张卡
            self._clear_selection()
            reselect()
            self.next_frame()
            kind, button = self._deploy_button()
        if kind == "swap":
            self.log_info(f"{label} 按钮是「编入队伍」（会顶替地图上选中的单位），不点，跳过", notify=False)
            self._clear_selection()
            return False
        if kind == "hint":
            candidates = self._candidate_tiles()
            if not candidates:
                self.log_info(f"{label} 需要先点地格，但没找到可点的地格", notify=False)
                return False
            for i, (tile, desc) in enumerate(candidates):
                if i > 0:
                    self._clear_selection()
                    if reselect:
                        reselect()
                        self.next_frame()
                self.log_info(f"{label} 试点{desc}", notify=False)
                self.click_relative(tile[0] / self.width, tile[1] / self.height, after_sleep=1)
                self.next_frame()
                kind, button = self._deploy_button()
                if kind == "deploy":
                    break
                if kind == "withdraw" and card_name in self._selected_role_name():
                    self.log_info(f"已顶替上场 {label}，阵容 {self._deploy_count()}", notify=True)
                    return True
            else:
                # 所有地格都试完了还没出现「部署人形」，把挂着的选中清掉再返回
                self._clear_selection()
        if kind != "deploy":
            self.log_info(f"{label} 没出现部署按钮，跳过", notify=False)
            return False
        for attempt in range(2):
            # 偶尔第一下「部署人形」点了没反应（按钮还是部署人形），等一下再点一次
            self.click(button, after_sleep=1.5)
            self.next_frame()
            if confirm := self.ocr(match=self.fix_match_regex(["确认"]), box=self.box.bottom):
                self.click(confirm, after_sleep=1.5)
                self.next_frame()
            kind, button = self._deploy_button()
            if kind != "deploy":
                break
            self.log_info(f"{label} 点了部署人形没反应，再点一次", notify=False)
        if self._placed(card_name, before):
            self.log_info(f"已部署 {label}，阵容 {self._deploy_count()}", notify=True)
            return True
        self.log_info(f"{label} 点了部署但没确认上场", notify=False)
        return False

    LINEUP_TASK = False  # 会进部署界面并需要整理阵容的任务置 True（推图）
    # 阵容是按关卡类型（推图/竞技场/体力本/班组/活动）整理的：每种类型在一次任务里只整理一次，之后沿用；
    # _lineup_kind 为 None 表示这段战斗不整理阵容（没进部署界面的任务用）
    _lineup_kind = None
    _lineup_verified_kinds = None

    def set_lineup_kind(self, kind):
        """进战斗前声明这是哪种关卡，决定用全局「阵容与助战」里的哪个编队；None = 不整理阵容"""
        self._lineup_kind = kind

    def reset_lineup(self, kind=None):
        """任务 run 开头调用：清掉"已整理过"的记录，并设定当前关卡类型"""
        self._lineup_verified_kinds = set()
        self._lineup_kind = kind

    def _lineup_verified(self):
        return self._lineup_verified_kinds is not None and self._lineup_kind in self._lineup_verified_kinds

    def _mark_lineup_verified(self):
        if self._lineup_verified_kinds is None:
            self._lineup_verified_kinds = set()
        self._lineup_verified_kinds.add(self._lineup_kind)

    # ------------------------------------------------------------------ 支援单位（第 9 章起，实录 2026-10-20）
    def _support_count(self):
        """顶部「支援 2/3」→ (2, 3)；这一关没有支援单位返回 None；有「支援」行但数字被挡住，多读两帧仍读不到返回 (None, None)。"""
        count = None
        for attempt in range(3):
            boxes = self._ocr_panel(SUPPORT_COUNT_BOX)
            count = parse_support_count([b.name for b in boxes])
            self.log_info(f"支援计数区文字: {[b.name for b in boxes]} -> {count}", notify=False)
            if count != (None, None):
                break
            self.sleep(0.3)
            self.next_frame()
        return count

    def _support_button(self):
        """右下角：("deploy", box) 部署支援单位 / ("withdraw", box) 撤回支援单位 / ("hint", box) 请点击地格 / (None, None)。"""
        boxes = self._ocr_panel(BUTTON_BOX)
        for b in boxes:
            if "部署支援" in b.name:
                return "deploy", b
            if "撤回支援" in b.name:
                return "withdraw", b
        for b in boxes:
            if "地格" in b.name or "拖拽" in b.name:
                return "hint", b
        return None, None

    def _click_support_tab(self, name):
        """底部中间「部署人形 / 部署支援」页签；OCR 漏读就按固定位置点。"""
        tab = self._ocr_panel(SUPPORT_TAB_BOX, match=self.fix_match_regex([name]))
        if tab:
            self.click(tab[0], after_sleep=1)
        else:
            xy = SUPPORT_TAB_XY[name]
            self.log_info(f"页签「{name}」OCR 没认出来，按固定位置点", notify=False)
            self.click_relative(xy[0], xy[1], after_sleep=1)
        self.next_frame()

    def _ensure_unit_tab(self):
        """部署界面停在「部署支援」页签时（右上是「可部署支援单位」），切回「部署人形」，整理阵容的面板逻辑才认得。"""
        if self._ocr_panel(TAB_BOX, match=self.fix_match_regex(["可部署支援单位"])):
            self.log_info("部署界面停在「部署支援」页签，切回「部署人形」", notify=False)
            self._click_support_tab("部署人形")
            return True
        return False

    def _support_cards(self):
        """右侧「可部署支援单位」面板的卡片 [{center, check, deployed}]，按位置排序。"""
        boxes = self._ocr_panel(PANEL_BOX, match=support_lv_re)
        cards = support_card_points(boxes, self.width, self.height)
        for c in cards:
            c["deployed"] = is_orange_check(self.frame, *c["check"])
        self.log_info(f"支援卡片 {len(cards)} 张，已部署 {sum(c['deployed'] for c in cards)} 张", notify=False)
        return cards

    def _support_card_placed(self, card):
        """部署后重新扫一遍卡片，同一位置的卡片是否打上了橙色勾。"""
        for c in self._support_cards():
            if (
                abs(c["center"][0] - card["center"][0]) < 0.02 * self.width
                and abs(c["center"][1] - card["center"][1]) < 0.03 * self.height
            ):
                return c["deployed"]
        return False

    def _click_support_card(self, card):
        self.click_relative(card["center"][0] / self.width, card["center"][1] / self.height, after_sleep=0.8)
        self.next_frame()

    def _follow_support_tutorial(self, max_steps=8):
        """
        第一次进第 9 章时可露凯的「通信中」引导挡在部署界面上，别的什么都点不了：
        按提示点红框支援点 / 点对话框推进 / 点「部署支援单位」，直到对话框消失。返回是否处理过引导。
        """
        handled = False
        for step in range(max_steps):
            boxes = self._ocr_panel(TUTORIAL_BOX)
            names = [b.name for b in boxes]
            action = tutorial_step(names)
            if action is None:
                return handled
            handled = True
            self.log_info(f"支援单位引导：{names} → {action}", notify=step == 0)
            self.debug_shot(f"support_tutorial_{step}")
            if action == "tile":
                xy = find_tutorial_tile(self.frame, self.width, self.height)
                if xy is None:
                    self.log_info("没找到引导红框圈住的支援点，点对话推进", notify=True)
                    self.click(boxes[-1], after_sleep=1.5)
                else:
                    self.click_relative(xy[0] / self.width, xy[1] / self.height, after_sleep=1.5)
            elif action == "button":
                kind, btn = self._support_button()
                if kind == "deploy":
                    self.click(btn, after_sleep=1.5)
                else:
                    self.click_relative(0.885, 0.94, after_sleep=1.5)
            else:
                self.click(boxes[-1], after_sleep=1.5)
            self.next_frame()
        self.log_info(f"支援单位引导 {max_steps} 步后还没结束，继续往下走", notify=True)
        return handled

    def deploy_supports(self):
        """
        第 9 章起的支援单位：顶部有「支援 n/m」且 n<m 时切到「部署支援」页签，选一张没部署的卡片、
        逐个点蓝色支援点，出现「部署支援单位」就点；点到「撤回支援单位」说明那格已有单位，换下一格。
        部署满或没有可部署的就切回「部署人形」页签。返回是否部署过。
        """
        self._follow_support_tutorial()
        count = self._support_count()
        if count is None:
            return False
        n, m = count
        if n is not None and n >= m:
            self.log_info(f"支援单位已满 {n}/{m}", notify=False)
            return False
        if n is None:
            self.log_info("有「支援」行但计数被挡住读不到，按没上满处理，部署到没有可用卡片/支援点为止", notify=True)
        self.info_set("current_task", "部署支援单位")
        self.log_info(f"支援单位 {n}/{m}，开始部署", notify=True)
        self._click_support_tab("部署支援")
        tried = []
        min_gap = (0.03 * self.height) ** 2
        deployed = False
        for _ in range((m or 3) * 3):
            if n is not None and n >= m:
                break
            cards = self._support_cards()
            free = [c for c in cards if not c["deployed"]]
            if not free:
                self.log_info("没有可部署的支援卡片了", notify=True)
                break
            card = free[0]
            self._click_support_card(card)
            tiles = [
                c
                for c in support_point_candidates(self.frame, self.width, self.height)
                if all((c[0] - x) ** 2 + (c[1] - y) ** 2 >= min_gap for x, y in tried)
            ]
            self.debug_shot("support_tiles")
            if not tiles:
                self.log_info("地图上没找到还没试过的支援点", notify=True)
                break
            placed = False
            for tile in tiles:
                tried.append(tile)
                self.click_relative(tile[0] / self.width, tile[1] / self.height, after_sleep=1)
                self.next_frame()
                kind, btn = self._support_button()
                if kind not in ("deploy", "withdraw"):
                    # 先点格子再点卡片的顺序也试一下
                    self._click_support_card(card)
                    kind, btn = self._support_button()
                self.log_info(f"支援点({int(tile[0])},{int(tile[1])}) 按钮状态 {kind}", notify=False)
                if kind == "withdraw":
                    self._clear_selection()
                    self._click_support_card(card)
                    continue
                if kind != "deploy":
                    continue
                self.click(btn, after_sleep=1.5)
                self.next_frame()
                if confirm := self.ocr(match=self.fix_match_regex(["确认"]), box=self.box.bottom):
                    self.click(confirm, after_sleep=1.5)
                    self.next_frame()
                new = self._support_count()
                if new and new[0] is not None and (n is None or new[0] > n):
                    n, m = new
                    deployed = placed = True
                    self.log_info(f"已部署支援单位，{n}/{m}", notify=True)
                    self._clear_selection()
                    break
                if new == (None, None) and self._support_card_placed(card):
                    # 计数仍被挡住：这张卡片打上勾了也算成功
                    deployed = placed = True
                    self.log_info("已部署支援单位（计数读不到，按卡片勾选确认）", notify=True)
                    self._clear_selection()
                    break
                self.log_info("点了「部署支援单位」但计数没涨，换下一个支援点", notify=True)
                self._clear_selection()
                self._click_support_card(card)
            if not placed:
                self.log_info(f"这张支援卡片在所有支援点都没能部署，停止（{n}/{m}）", notify=True)
                break
        self.debug_shot("supports_done")
        self._click_support_tab("部署人形")
        return deployed

    def _handle_stamina_popup(self, title):
        """
        体力不足弹窗：全局设置「体力」里开了「自动使用体力药」就只用调度室储存/情报拼图道具恢复，
        没开、或两种都用不了，就取消弹窗并抛异常停止任务，绝不消耗坍塌晶条。
        """
        self.debug_shot("stamina_popup", [title])
        if not self.auto_potion_enabled():
            self._cancel_stamina_popup()
            raise Exception("体力不足，已停止；要自动用体力药请打开设置页「体力」里的「自动使用体力药」")
        if self.restore_stamina(title):
            return
        raise Exception("体力不足，调度室储存和情报拼图道具都用不了，已停止（不会使用坍塌晶条）")

    def auto_potion_enabled(self):
        """全局设置「体力」→「自动使用体力药」；读不到按关闭处理。"""
        try:
            return bool(self.get_global_config(STAMINA_OPTION_NAME).get(KEY_AUTO_POTION, False))
        except Exception:
            return False

    def _cancel_stamina_popup(self):
        self.next_frame()
        if cancel := self.ocr(match=self.fix_match_regex(["取消"])):
            self.click(cancel, after_sleep=1)
        else:
            self.back()
            self.sleep(1)

    def restore_stamina(self, title):
        """
        在「情报拼图补充」弹窗上依次试前两个页签（调度室储存、情报拼图道具），每次只用 1 份。
        :return: True 弹窗已消失（恢复成功）；False 两个页签都没用上，弹窗已取消
        """
        points = stamina_tab_points(title, self.height)
        before = stamina_value(self.ocr(), self.height)
        for idx in STAMINA_SAFE_TABS:
            x, y = points[idx]
            self.click_relative(x / self.width, y / self.height, after_sleep=1)
            self.next_frame()
            boxes = self.ocr()
            if not self.find_boxes(boxes, match=stamina_popup_re):
                self.log_info("体力弹窗已消失", notify=False)
                return True
            texts = popup_texts(boxes, title, self.height)
            self.debug_shot(f"stamina_tab{idx + 1}", boxes)
            if has_forbidden_restore_text(texts):
                self.log_info(f"体力弹窗页签{idx + 1} 会消耗抽卡资源，跳过: {texts}", notify=False)
                continue
            count = tab_count(boxes, x, y, self.height)
            if count == 0:
                self.log_info(f"体力弹窗页签{idx + 1} 数量为 0，跳过", notify=False)
                continue
            confirm = [c for c in self.find_boxes(boxes, match=self.fix_match_regex(["确认"])) if c.y > y]
            if not confirm:
                self.log_info(f"体力弹窗页签{idx + 1} 没找到确认按钮，跳过", notify=False)
                continue
            self.click(confirm[0], after_sleep=2)
            # 确认后弹窗要过一会儿才关，用接入密钥兑换成功后弹窗甚至一直开着（实录：9/240 -> 69/240 还在），
            # 所以看右上角体力数字有没有涨：涨了就算成功，自己把弹窗关掉
            for _ in range(4):
                self.next_frame()
                boxes = self.ocr()
                if not self.find_boxes(boxes, match=stamina_popup_re):
                    self.log_info(f"已用体力弹窗页签{idx + 1} 恢复体力（数量 {count}）", notify=True)
                    self.debug_shot("stamina_restored", boxes)
                    return True
                after = stamina_value(boxes, self.height)
                if before is not None and after is not None and after > before:
                    self.log_info(
                        f"已用体力弹窗页签{idx + 1} 恢复体力 {before}→{after}，弹窗还开着，关掉继续", notify=True
                    )
                    self.debug_shot("stamina_restored", boxes)
                    self._cancel_stamina_popup()
                    return True
                self.sleep(1)
            self.log_info(f"体力弹窗页签{idx + 1} 确认后弹窗仍在、体力没变（{before}），换下一个页签", notify=False)
            self.debug_shot(f"stamina_tab{idx + 1}_after_confirm", boxes)
        self._cancel_stamina_popup()
        return False

    def _click_continue(self, box):
        """点「继续前进」，连续点太多次都没进入战斗就停，避免体力不足时无限循环。"""
        self._continue_streak = getattr(self, "_continue_streak", 0) + 1
        if self._continue_streak > MAX_CONTINUE_STREAK:
            self.debug_shot("continue_no_progress", box)
            raise Exception(f"连续点击继续前进 {MAX_CONTINUE_STREAK} 次都没进入战斗，已停止")
        self.click_box(box, after_sleep=2)

    def _is_failure_page(self):
        """读到「任务失败」后核对：底部有「重新挑战 / 战斗重演」才是真的失败结算页。"""
        return bool(self.wait_ocr(match=failure_page_re, box=self.box.bottom, time_out=3, raise_if_not_found=False))

    def _is_battle_frame(self, boxes):
        """
        判断当前帧是否为战斗中界面（存在「行动结束」或回合计数）。
        :param boxes: OCR 识别结果
        :return: True 如果处于战斗中，否则 False
        """
        return bool(self.find_boxes(boxes, match=battle_ui_re))

    def _is_loading_frame(self, boxes):
        """
        判断当前帧是否为加载界面。
        :param boxes: OCR 识别结果
        :return: True 如果是加载界面，否则 False
        """
        if not boxes:
            return True
        names = [box.name for box in boxes if box.name]
        if any("资源加载中" in name for name in names):
            return True
        # 离开活动层时的「艾莫号」过场：NOW LOADING / 移动中…69%，文字很多但就是加载页
        if any(re.search(r"移动中|NOW\s*LOADING|LOADING\.{0,3}$", name, re.I) for name in names):
            return True
        # 只有一个进度百分比、几乎没有别的文字时才算加载页；
        # 教学弹窗里的「60% 25% 60% 20%」这类伤害数值不能当成加载页，否则会一直不点关闭
        has_progress = any(re.fullmatch(r"\s*\d{1,3}%\s*", name) for name in names)
        return has_progress and len(names) <= 3

    def auto_battle(
        self,
        end_match=None,
        end_box=None,
        has_dialog=False,
        need_click_auto=False,
        has_dialog_behind_start=False,
        keep_lineup=False,
    ):
        """
        确认战斗界面后执行自动作战；开局无法识别时抛出明确错误。

        :param keep_lineup: 这一轮是点「继续前进」进来的，阵容（含助战）沿用上一段，不再整理直接开战
        """
        self.info_set("current_task", "auto battle")
        result = self.skip_dialogs(
            end_match=["作战开始", "行动结束", "继续前进"],
            end_box=self.box.bottom,
            time_out=120,
            has_dialog=has_dialog,
            raise_if_not_found=False,
        )
        self.debug_shot("battle_entry", result)
        if not result:
            raise RuntimeError("2 分钟内没进入部署界面（没等到作战开始/行动结束/继续前进），已停止，看 battle_entry 截图")
        if result[0].name != "继续前进":
            self._continue_streak = 0
        if result and result[0].name == "继续前进":
            self.log_info("开局检测到继续前进，点击后开启新一轮自动战斗", notify=True)
            self._click_continue(result)
            self.auto_battle(
                end_match=end_match,
                end_box=end_box,
                has_dialog=has_dialog,
                need_click_auto=need_click_auto,
                has_dialog_behind_start=has_dialog_behind_start,
                keep_lineup=True,
            )
            return
        if result[0].name == "作战开始":
            self.sleep(2)
            # 实录 2026-10-20：第一次进第 9 章时「支援单位」引导挡在部署界面上，不先按引导走完什么都点不了
            self._follow_support_tutorial()
            lineup_on = self.LINEUP_TASK or self._lineup_kind is not None
            if lineup_on:
                self._ensure_unit_tab()
            if lineup_on and (keep_lineup or self._lineup_verified()):
                # 任务启动后只在第一次进部署界面时整理阵容；之后不管是「继续前进」还是从选关面板「挑战」进来，
                # 游戏都沿用上一场的阵容（含助战），只看一眼人数没缺就直接开战
                count = self._deploy_count()
                if count and count[0] < count[1]:
                    self.log_info(f"阵容只有 {count[0]}/{count[1]}，重新整理一次", notify=True)
                    self.prepare_lineup()
                else:
                    self.log_info("阵容已整理过，沿用上一场直接开战", notify=False)
            elif lineup_on:
                self.log_info(
                    f"第一次进「{self._lineup_kind or '推图'}」部署界面，整理阵容（编队：{self._preset_name() or '不切'}）",
                    notify=True,
                )
                self.prepare_lineup()
                self._mark_lineup_verified()
            if lineup_on:
                # 第 9 章起每关有自己的支援点，不管阵容整不整理都要看一眼支援有没有上满
                self.deploy_supports()
                if self._deploy_button()[0] in ("withdraw", "blocked"):
                    self._clear_selection()
                result = self.wait_ocr(match="作战开始", box=self.box.bottom, time_out=10, raise_if_not_found=True)
            self.click_box(result, after_sleep=1)
            must_full = False
            for _ in range(2):
                # 地图上挂着选中时点「作战开始」只会把面板弹出来，战斗不会开始；清掉选中再点一次
                self.sleep(2)
                self.next_frame()
                still = self.ocr(match="作战开始", box=self.box.bottom)
                if not still:
                    break
                if self.ocr(match=re.compile("还有可部署")):
                    # 实录 2026-10-20：「还有可部署的单位」确认框是半透明的，后面的「作战开始」还能 OCR 到；
                    # 这不是没点上，交给下面的 skip_dialogs 点确认
                    break
                if must := self.ocr(match=must_deploy_re):
                    # 实录 2026-10-20 BH-9-4：点作战开始只闪一下「本关至少需要出击4人!」，人没满开不了战
                    self.log_info(f"游戏提示「{must[0].name}」，再补一次人", notify=True)
                    self.debug_shot("must_deploy")
                    must_full = True
                    self._ensure_panel()
                    self.fill_lineup()
                self.log_info("点了作战开始但还在部署界面，清掉选中后再点", notify=True)
                self.debug_shot("battle_start_retry")
                self._clear_selection()
                self.click_box(still, after_sleep=1)
            if must_full:
                self.sleep(2)
                self.next_frame()
                if self.ocr(match="作战开始", box=self.box.bottom) and not self.ocr(match=re.compile("还有可部署")):
                    count = self._deploy_count()
                    raise Exception(f"本关要求出击人数补不满（当前 {count}），请手动部署后再启动推图")
            start_result = self.skip_dialogs(
                end_match=[
                    re.compile("行动完成"),
                    re.compile("行动结束"),
                    re.compile("还有可部署"),
                    re.compile("任务完成"),
                    re.compile("继续前进"),
                ],
                has_dialog=True,
                time_out=45,
                raise_if_not_found=False,
            )
            self.debug_shot("after_battle_start", start_result)
            if start_result and "继续前进" in start_result[0].name:
                self.log_info("开局后检测到继续前进，点击后开启新一轮自动战斗", notify=True)
                self._click_continue(start_result)
                self.auto_battle(
                    end_match=end_match,
                    end_box=end_box,
                    has_dialog=has_dialog,
                    need_click_auto=need_click_auto,
                    has_dialog_behind_start=has_dialog_behind_start,
                    keep_lineup=True,
                )
                return
            ok_bool = bool(start_result) and (
                not ("还有可部署" in start_result[0].name or "行动结束" in start_result[0].name)
            )
            if not ok_bool:
                if start_result and ("还有可部署" in start_result[0].name):
                    self.log_info("阵容没上满!", notify=True)

                    self.wait_click_ocr(match=["确认"], box=self.box.bottom, time_out=5, raise_if_not_found=True)
                    self.wait_ocr(match=["行动结束"], box=self.box.bottom_right, raise_if_not_found=False, time_out=15)
                    # start_result = self.wait_ocr(match=['行动结束'], box=self.box.bottom_right,
                    #                              raise_if_not_found=False, time_out=15)
                if not start_result and has_dialog_behind_start:
                    start_result = self.skip_dialogs(
                        end_match=["作战开始", "行动结束", "继续前进"],
                        end_box=self.box.bottom,
                        time_out=120,
                        has_dialog=has_dialog,
                        raise_if_not_found=False,
                    )
                    if start_result and start_result[0].name == "继续前进":
                        self.log_info("开局二次检测到继续前进，点击后开启新一轮自动战斗", notify=True)
                        self._click_continue(start_result)
                        self.auto_battle(
                            end_match=end_match,
                            end_box=end_box,
                            has_dialog=has_dialog,
                            need_click_auto=need_click_auto,
                            has_dialog_behind_start=has_dialog_behind_start,
                            keep_lineup=True,
                        )
                        return
                    if self.wait_ocr(match="注意", box=self.box.top):
                        self.wait_click_ocr(match="取消", after_sleep=2)
                if start_result and need_click_auto:
                    self.sleep(0.5)
                    # 最多尝试 5 次，避免自动按钮被反复切换
                    for _ in range(5):
                        if not self.ocr(match="行动结束", box=self.box.bottom_right):
                            break
                        self.log_info("检测到行动结束，点击右上角自动战斗按钮", notify=False)
                        if self.is_adb():
                            self.click_relative(0.85, 0.05, after_sleep=1)
                        else:
                            self.click_relative(0.88, 0.04, after_sleep=1)
                        self.debug_shot("after_click_auto")

        clicked_continue = False
        fake_failures = 0
        while results := self.skip_dialogs(
            # 实录 2026-10-20：真实输入下角落点击会把结算页点过去，等到的直接是选关页面，也算打完了
            end_match=[
                "任务完成",
                "任务失败",
                "战斗失败",
                "对战胜利",
                "对战失败",
                "确认",
                "确认结算",
                "继续前进",
                map_re,
                chapter_select_re,
            ],
            time_out=900,
            has_dialog=has_dialog,
        ):
            if battle_over_on_map(results):
                self.log_info("结算页已经过去，回到了选关页面 / 章节选择页", notify=False)
                break
            if results[0].name == "任务失败" and fake_failures < 20 and not self._is_failure_page():
                fake_failures += 1
                self.log_info("读到「任务失败」但没有失败结算页的按钮，当成战斗特效误读，继续等", notify=False)
                self.debug_shot("fake_failure", results)
                continue
            # 优先遍历所有结果找"继续前进"
            clicked = False
            if any(r.name != "继续前进" for r in results):
                self._continue_streak = 0
            for result in results:
                if result.name == "继续前进":
                    self._click_continue(result)
                    clicked = True
                    clicked_continue = True
                    break
            if not clicked:
                for result in results:
                    if result.name in ("确认", "确认结算"):
                        self.click_box(result, after_sleep=2)
                        clicked = True
                        break
            self.sleep(2)
            self.click_box(results, after_sleep=2)
            if results[0].name not in pop_ups:
                break
        self.debug_shot("battle_result", results)
        if not results:
            raise Exception("自动战斗异常")
        if results[0].name == "任务失败":
            raise BattleLost("任务失败, 没打过!")
        if clicked_continue:
            self.log_info("检测到继续前进，点击后开启新一轮自动战斗", notify=True)
            self.auto_battle(
                end_match=end_match,
                end_box=end_box,
                has_dialog=has_dialog,
                need_click_auto=need_click_auto,
                has_dialog_behind_start=has_dialog_behind_start,
                keep_lineup=True,
            )
            return
        if cont := self.wait_ocr(match="继续前进", box=self.box.bottom_right, raise_if_not_found=False, time_out=3):
            self.log_info("结算后检测到继续前进，点击后开启新一轮自动战斗", notify=True)
            self._click_continue(cont)
            self.auto_battle(
                end_match=end_match,
                end_box=end_box,
                has_dialog=has_dialog,
                need_click_auto=need_click_auto,
                has_dialog_behind_start=has_dialog_behind_start,
                keep_lineup=True,
            )
            return
        while self.wait_click_ocr(match="确认", box=self.box.bottom_right, raise_if_not_found=False, time_out=3):
            pass
        if end_match:
            if isinstance(end_match, list):
                end_match = end_match + pop_ups
            else:
                end_match = [end_match] + pop_ups
            end_match.append("确认")
            end_match.append("确认结算")
            end_match.append("继续前进")
            while True:
                match = self.skip_dialogs(
                    end_match=end_match, end_box=end_box, time_out=30, has_dialog=has_dialog, raise_if_not_found=True
                )
                if match[0].name in pop_ups:
                    self.back(after_sleep=2)
                    continue
                if match[0].name == "继续前进":
                    self.log_info("最后阶段检测到继续前进，点击后开启新一轮自动战斗", notify=True)
                    self.click_box(match, after_sleep=2)
                    self.auto_battle(
                        end_match=end_match,
                        end_box=end_box,
                        has_dialog=has_dialog,
                        need_click_auto=need_click_auto,
                        has_dialog_behind_start=has_dialog_behind_start,
                        keep_lineup=True,
                    )
                    return
                if match[0].name in ("确认", "确认结算"):
                    self.click_box(match, after_sleep=8)
                break
        self.sleep(2)

    def is_main(self, recheck_time=0.0, esc=True):
        boxes = self.ocr(match=main_marks, box="right", log=True)
        feature_boxes = []
        for feature in [fL.dog_icon, fL.message_icon]:
            if result := self.find_one(feature, vertical_variance=0.002, horizontal_variance=0.002):
                feature_boxes.append(result)
        total = len(boxes) + len(feature_boxes)
        self.log_info(f"is main ocr={len(boxes)} features={len(feature_boxes)} total={total}")
        if total >= 2:
            self._cancel_streak = 0
            return True
        if self._handle_restart_required():
            return False
        # 剧情对话：右上角「自动 / 跳过 / 全部跳过」，ESC 没用，交给 skip_dialogs 点「跳过」
        # （实录 2026-10-21：停掉推图时正好在放下一章的开场剧情，接着跑一键日常，回主页 90 秒超时；OCR 会把「自动跳过」读成一个框）
        if self.ocr(box=self.box.top_right, match=story_skip_re):
            self.log_info("画面是剧情对话，先跳过剧情再回主页", notify=False)
            self.skip_dialogs(end_match=main_marks, time_out=20, raise_if_not_found=False)
            return False
        # if not self.do_handle_alert()[0]:
        if self.ocr(match=re.compile("^是否离开活动层"), box=self.box.center, log=True):
            # 实录：读到了「是否离开活动层」却 10 秒都找不到确认按钮，连续 5 轮把回主页的时间耗光；缩短等待，找不到就走下面的 ESC
            if self.wait_click_ocr(match="确认", after_sleep=2, box=self.box.bottom_right, time_out=3):
                return False
        if box := self.ocr(box=self.box.bottom, match=["点击开始", "点击空白处关闭", "取消"], log=True):
            if box[0].name == "取消":
                # 实录：活动层里 ESC 弹出的离开确认框标题没被 OCR 读到，脚本反复点「取消」→ESC→再弹，60 秒后超时。
                # 弹窗文字里有离开/退出字样、或已经连点 3 次取消还没回主页，就改点「确认」
                self._cancel_streak = getattr(self, "_cancel_streak", 0) + 1
                texts = [b.name for b in self.ocr()]
                leave_like = any(re.search(r"离开|退出|返回", t) for t in texts)
                if self._cancel_streak == 3:
                    self.log_info(f"连续 3 次点取消都没回到主页，弹窗文字: {texts[:12]}", notify=False)
                    self.screenshot("cancel_loop")
                if leave_like or self._cancel_streak >= 3:
                    if confirm := self.ocr(box=self.box.bottom, match=["确认"]):
                        self.log_info(f"弹窗像是离开确认（{texts[:6]}），点确认", notify=False)
                        self.click(confirm, after_sleep=2)
                        return False
            self.click(box, after_sleep=2)
            return False
        # 「本期扩编实练已结束」通知框、竞技场「对战胜利/失败」结算页：只有「确认」能关，ESC 没用
        if self._confirm_battle_result():
            return False
        # 停在战斗部署界面时 ESC 只会弹出/关掉关卡信息菜单，回不去；菜单里有「退出作战」就点它（后面的确认框走上面的离开确认）
        if quit_box := self.ocr(box=self.box.bottom_left, match=re.compile("^退出作战$")):
            if self.ocr(box=self.box.bottom_right, match=re.compile("^继续作战$")):
                self.log_info("在战斗菜单里，点「退出作战」", notify=False)
                self.click(quit_box, after_sleep=2)
                return False
        if esc:
            if result := self.find_feature(
                feature=[fL.back_home, fL.back_home_light], horizontal_variance=0.02, vertical_variance=0.002
            ):
                self.click(result, after_sleep=2)
                return False
            self.back(after_sleep=2)
        self.next_frame()
        return False

    def click(
        self,
        x: float | Box | list[Box] = 0.0,
        y: float | int = 0.0,
        move_back=False,
        name=None,
        interval=-1,
        move=True,
        down_time=0.01,
        after_sleep=0,
        key="left",
        alt=False,
    ):
        """
        点击。

        ``alt=True`` 时按住 alt 再点击（等价于 ``click_with_alt``），用于只有 alt 组合键才能命中的界面。
        x 支持 Box、Box 列表、屏幕比例（0~1）与绝对坐标，分派逻辑沿用父类。
        """
        self._touch_progress()
        if alt:
            return self.click_with_alt(
                x,
                y,
                move_back=move_back,
                name=name,
                interval=interval,
                move=move,
                down_time=down_time,
                after_sleep=after_sleep,
                key=key,
            )
        frame = self.frame
        super().click(
            x,
            y,
            move_back=move_back,
            name=name,
            move=move,
            down_time=0.04,
            after_sleep=after_sleep,
            interval=interval,
            key=key,
        )
        if self.debug:
            self.screenshot("click", frame=frame)

    def click_with_alt(
        self,
        x: float | Box | list[Box] = 0.0,
        y: float | int = 0.0,
        move_back=False,
        name=None,
        interval=-1,
        move=True,
        down_time=0.01,
        after_sleep=0,
        key="left",
        alt_hold_delay=0.5,
        debug_name="click_with_alt",
    ):
        """
        按住 alt 键点击。

        用于只有 alt 组合键才能生效的目标（例如自由层内的点击）。
        先 ``send_key_down('alt')``，等待 ``alt_hold_delay`` 让游戏识别到修饰键，再点击，最后 ``send_key_up('alt')``。

        Args:
            alt_hold_delay: 按下 alt 后到点击之间的等待秒数；传 0 可保持不加额外等待的时序。
            debug_name: debug 模式下的截图名。
        """
        frame = self.frame
        self.send_key_down("alt")
        try:
            if alt_hold_delay > 0:
                self.sleep(alt_hold_delay)
            self.click(
                x,
                y,
                move_back=move_back,
                name=name,
                interval=interval,
                move=move,
                down_time=down_time,
                after_sleep=after_sleep,
                key=key,
            )
        finally:
            # 必须保证松开 alt：点击抛异常时若卡住 alt，后续所有按键都会被污染
            self.send_key_up("alt")
        if self.debug:
            self.screenshot(debug_name, frame=frame)

    def back(self, after_sleep=0):
        frame = self.frame
        self.send_key("esc", down_time=0.04, after_sleep=after_sleep)
        if self.debug:
            self.screenshot("back", frame=frame)

    def free_layer_click(
        self, x=0, y=0, move_back=False, name=None, interval=-1, move=True, down_time=0.01, after_sleep=0, key="left"
    ):
        # alt_hold_delay=0：保持改造前的时序（按下 alt 后立即点击，不加额外等待）
        self.click_with_alt(
            x,
            y,
            move_back=move_back,
            name=name,
            interval=interval,
            move=move,
            down_time=down_time,
            after_sleep=after_sleep,
            key=key,
            alt_hold_delay=0,
            debug_name="free_layer_click",
        )

    def click_with_key(self, hold_key, result, delay1=1, delay2=0.5, after_sleep=0):
        # 任务线程内执行，异常可传播且修饰键总会释放。
        """Click while holding a modifier and guarantee its release on failure."""
        try:
            self.send_key_down(hold_key)
            self.sleep(delay2)
            self.click(result)
            self.sleep(max(0, delay1 - delay2))
        finally:
            self.send_key_up(hold_key)
        self.sleep(after_sleep)

    def wait_click_ocr(
        self,
        x=0,
        y=0,
        to_x=1,
        to_y=1,
        width=0,
        height=0,
        box=None,
        name=None,
        match=None,
        threshold=0,
        frame=None,
        target_height=0,
        time_out=0,
        raise_if_not_found=False,
        recheck_time=0,
        after_sleep=0,
        post_action=None,
        log=False,
        screenshot=False,
        settle_time=-1,
        lib="default",
        alt=False,
    ):
        """
        等待 OCR 命中并点击，``alt=True`` 时改用 alt 组合键点击。

        参数与父类一致；``alt=False`` 直接走父类实现，不做任何改动。
        """
        if not alt:
            return super().wait_click_ocr(
                x=x,
                y=y,
                to_x=to_x,
                to_y=to_y,
                width=width,
                height=height,
                box=box,
                name=name,
                match=match,
                threshold=threshold,
                frame=frame,
                target_height=target_height,
                time_out=time_out,
                raise_if_not_found=raise_if_not_found,
                recheck_time=recheck_time,
                after_sleep=after_sleep,
                post_action=post_action,
                log=log,
                screenshot=screenshot,
                settle_time=settle_time,
                lib=lib,
            )

        result = self.wait_ocr(
            x,
            y,
            width=width,
            height=height,
            to_x=to_x,
            to_y=to_y,
            box=box,
            name=name,
            match=match,
            threshold=threshold,
            frame=frame,
            target_height=target_height,
            time_out=time_out,
            raise_if_not_found=raise_if_not_found,
            post_action=post_action,
            log=log,
            screenshot=screenshot,
            settle_time=settle_time,
            lib=lib,
        )
        if recheck_time > 0:
            self.sleep(1)
            result = self.ocr(
                x,
                y,
                width=width,
                height=height,
                to_x=to_x,
                to_y=to_y,
                box=box,
                name=name,
                match=match,
                threshold=threshold,
                frame=frame,
                target_height=target_height,
                log=log,
                screenshot=screenshot,
                lib=lib,
            )
        if result is not None:
            self.click_with_alt(result, after_sleep=after_sleep)
            return result
        logger.warning(f"wait ocr no box {x} {y} {width} {height} {to_x} {to_y} {match}")

    def wait_click_feature(
        self,
        feature,
        horizontal_variance=0,
        vertical_variance=0,
        threshold=0,
        relative_x=0.5,
        relative_y=0.5,
        time_out=0,
        pre_action=None,
        post_action=None,
        box=None,
        raise_if_not_found=True,
        use_gray_scale=False,
        canny_lower=0,
        canny_higher=0,
        click_after_delay=0,
        settle_time=-1,
        after_sleep=0,
        target_height=0,
        alt=False,
    ):
        """
        等待特征命中并点击，``alt=True`` 时改用 alt 组合键点击。

        参数与父类一致；``alt=False`` 直接走父类实现，不做任何改动。
        """
        if not alt:
            return super().wait_click_feature(
                feature,
                horizontal_variance,
                vertical_variance,
                threshold,
                relative_x=relative_x,
                relative_y=relative_y,
                time_out=time_out,
                pre_action=pre_action,
                post_action=post_action,
                box=box,
                raise_if_not_found=raise_if_not_found,
                use_gray_scale=use_gray_scale,
                canny_lower=canny_lower,
                canny_higher=canny_higher,
                click_after_delay=click_after_delay,
                settle_time=settle_time,
                after_sleep=after_sleep,
                target_height=target_height,
            )

        found = self.wait_until(
            lambda: self.find_one(
                feature,
                horizontal_variance,
                vertical_variance,
                threshold,
                box=box,
                use_gray_scale=use_gray_scale,
                canny_lower=canny_lower,
                canny_higher=canny_higher,
                target_height=target_height,
            ),
            time_out=time_out,
            pre_action=pre_action,
            post_action=post_action,
            raise_if_not_found=raise_if_not_found,
            settle_time=settle_time,
        )
        if found is not None:
            if click_after_delay > 0:
                self.sleep(click_after_delay)
            x, y = found.relative_with_variance(relative_x, relative_y)
            self.click_with_alt(x, y, name=found.name, after_sleep=after_sleep)
            return True
        return False

    def find_top_right_count(self):
        result = self.ocr(0.89, 0.01, 0.99, 0.1, match=re.compile(r"^\d+/\d+$"), box="top_right")
        if not result:
            raise Exception("找不到当前体力或票")
        return int(result[0].name.split("/")[0])

    def find_cost(self, boxes=None, default=30):
        boundary = self.box_of_screen(0.48, 0.56, 0.57, 0.7)
        if not boxes:
            boxes = self.ocr(box=boundary)

        if costs := self.find_boxes(boxes, match=number_re, boundary=boundary):
            cost = int(costs[0].name)
        else:
            cost = default
        return cost

    def out_free_layer(self):
        self.info_set("current_task", "out_free_layer")
        while not self.wait_click_ocr(match=["确认"], time_out=2):
            self.back()
            self.sleep(2)

    def is_free_layer(self, time_out=20, every_time=1):
        # wait_ocr(time_out=0) 使用框架默认超时，不能用于单次探测。
        """按限定超时识别活动层 HUD，避免嵌套默认等待。"""

        def detected():
            """仅用当前帧检查活动层快捷键标识是否齐全。"""
            result = self.ocr(match=["Esc", "P", "M", "F1", "F2", "F3", "F4"], box=self.box.top)
            return bool(result and len(result) >= 5)

        return bool(self.wait_until(detected, time_out=max(time_out, 0.01), settle_time=0))

    def break_if_not_enough(self):
        if self.wait_ocr(match=re.compile("坍塌晶条"), time_out=2, log=True):
            self.wait_click_ocr(match=["取消"], after_sleep=2, time_out=2, raise_if_not_found=True)
            return True
        return False

    def back_if_not_ocr_match(self, match, box=None, max_back_count=1, raise_if_not_found=False):
        for count in range(max_back_count + 1):
            temp_raise_if_not_found = False
            if count == max_back_count:
                temp_raise_if_not_found = True
            if self.wait_ocr(match=match, box=box, raise_if_not_found=temp_raise_if_not_found):
                return
            else:
                self.back(after_sleep=2)
        return

    def fast_combat(self, *, set_cost, battle_max=10, plus_x=0.616, plus_y=0.52, click_all=False, activity=False):
        if activity:
            click_all = True
        if click_all:
            plus_x = 0.65
            plus_y = 0.52
            self.wait_click_ocr(match=["自律"], box=self.box.bottom_right, after_sleep=2, raise_if_not_found=True)
            if self.break_if_not_enough():
                self.wait_ocr(match=["自律"], box=self.box.bottom_right, raise_if_not_found=True)
                return 0
            self.click(plus_x, plus_y)
            self.wait_click_ocr(match=["确认"], after_sleep=1, raise_if_not_found=False)
            if not self.wait_click_ocr(match=["取消"], time_out=2, raise_if_not_found=False):
                self.wait_pop_up(count=1)
            self.back_if_not_ocr_match(match=["自律"], box=self.box.bottom_right, raise_if_not_found=True)
            return 0

        if self._zilv_locked:
            # 这一轮任务里已经确认过自律是灰的，不再每次都点一下白等
            return self._manual_stamina_battle(set_cost)
        self.wait_click_ocr(match=["自律"], box=self.box.bottom_right, after_sleep=2, raise_if_not_found=True)
        if self.break_if_not_enough():
            self.wait_ocr(match=["自律"], box=self.box.bottom_right, raise_if_not_found=True)
            return 0
        boxes = self.ocr(log=True, threshold=0.8, frame_processor=self.make_hsv_isolator(hR.WHITE))
        if next_step := self.find_boxes(boxes, "下一步", self.box.bottom_right):
            self.click(next_step, after_sleep=1)
            boxes = self.ocr(log=True, threshold=0.8, frame_processor=self.make_hsv_isolator(hR.WHITE))
            # default_cost = 30
        # 实录：右上角金币「447760」尾巴会落进这个框被当成体力（读成 60/760），只认「147/240」这种带斜杠的
        current = self._read_stamina(default=1)
        self.sleep(1)
        if (
            len(find_boxes_by_name(boxes, ["确认", "取消", "上一步"])) != 2
            and len(find_boxes_by_name(boxes, ["确认", "取消", "上", "一步"])) != 3
        ):
            self.debug_shot("fast_no_zilv", boxes)
            locked = self._zilv_button_locked()
            if locked:
                self.log_info("自律按钮是灰色的（还没解锁自律），改为直接点「挑战」手动打", notify=True)
            elif locked is None:
                self.log_info("点了自律没弹窗，也没找到自律/挑战按钮对比颜色，改为直接点「挑战」手动打", notify=True)
            else:
                self.log_info("点了自律没弹窗（按钮不是灰的，可能调度权限不足），改为直接点「挑战」手动打", notify=True)
            self._zilv_locked = True
            return self._manual_stamina_battle(set_cost, current)
        cost = set_cost
        # if set_cost:
        #     cost = set_cost
        # else:
        #     cost = self.find_cost(boxes, default=default_cost)

        self.info_set("current_stamina", current)
        self.info_set("battle_cost", cost)
        self.info_set("battle_max", battle_max)
        can_fast_count = min(int(current / cost), battle_max)
        self.info_set("can_fast_count", can_fast_count)
        self.info_set("click_battle_plus", 0)
        self.log_info(f"battle cost: {cost} current_stamina: {current} can_fast_count: {can_fast_count}")

        for _ in range(can_fast_count - 1):
            self.click(plus_x, plus_y)
            self.info_incr("click_battle_plus")
            self.sleep(0.2)
        self.sleep(1)
        remaining = current - can_fast_count * cost
        self.info_set("remaining_stamina", remaining)
        if can_fast_count <= 0:
            self.click(find_boxes_by_name(boxes, "取消"))
            return remaining

        self.click(find_boxes_by_name(boxes, "确认"), after_sleep=2)

        # 「前往」只在背包满了弹「去分解」时才有；没有就别把 None 传给 click（会刷一条 click_box box is None 的 ERROR）
        if (go := find_boxes_by_name(boxes, "前往")) and self.click(go, after_sleep=2):
            if self.enter_fast_disassemble():
                self.fast_disassemble_loop(stamina_re)

            self.click(find_boxes_by_name(boxes, "确认"), after_sleep=2)

        self.wait_pop_up(count=1)
        self.wait_ocr(match=["自律"], box=self.box.bottom_right, raise_if_not_found=True)

        return remaining

    _zilv_locked = False  # 本次任务里自律按钮灰色/点了没反应；DailyTask.run 开头置回 False

    def _zilv_button_locked(self):
        """
        看当前帧右下角：「自律」按钮比「挑战」按钮暗很多就是灰色未解锁。
        返回 True/False，找不到两个按钮返回 None。
        """
        self.next_frame()
        boxes = self.ocr(box=self.box.bottom_right)
        zilv = self.find_boxes(boxes, match="自律")
        challenge = self.find_boxes(boxes, match=challenge_button_re)
        if not zilv or not challenge:
            return None
        zg = region_mean_gray(self.frame, zilv[0])
        cg = region_mean_gray(self.frame, challenge[0])
        self.log_info(f"自律按钮灰度 {zg and round(zg)}，挑战按钮灰度 {cg and round(cg)}", notify=False)
        if cg is not None and cg < 90:
            # 整个画面被压暗了（弹窗/过渡），这帧比不出来
            return None
        return zilv_locked(zg, cg)

    def _read_stamina(self, default=None):
        """右上角「147/240」里的当前体力；金币数等纯数字一律不认，读不到返回 default。"""
        for _ in range(2):
            value = stamina_value(self.ocr(box=self.box_of_screen(0.80, 0, 0.99, 0.10)), self.height)
            if value is not None:
                return value
            self.sleep(0.5)
            self.next_frame()
        self.log_info("右上角没读到体力数字", notify=False)
        return default

    def _manual_stamina_battle(self, set_cost, current=None):
        """
        自律不可用时点「挑战」手动打一场，打完回到选关面板，返回剩余体力。
        """
        if current is None:
            current = self._read_stamina(default=set_cost)
        if current < set_cost:
            self.log_info(f"体力 {current} 不够一场（{set_cost}），不再手动挑战", notify=False)
            return current
        self.log_info(f"手动挑战：体力 {current}，本场消耗 {set_cost}", notify=True)
        pop = None
        for attempt in range(3):
            # 实录：点自律后画面会暗一下（灰度 55），这时点「挑战」没反应；点完没离开面板就再点
            if not self.wait_click_ocr(
                match=challenge_button_re,
                box=self.box.bottom_right,
                time_out=5,
                after_sleep=2,
                raise_if_not_found=False,
            ):
                self.debug_shot("manual_challenge_missing")
                raise Exception("自律不可用，但选关面板上也没找到「挑战」按钮")
            pop = self.wait_ocr(match=stamina_popup_re, time_out=2, raise_if_not_found=False)
            if pop:
                break
            self.next_frame()
            if not self.ocr(match=challenge_button_re, box=self.box.bottom_right):
                break
            self.log_info(f"点了「挑战」还在选关面板，再点一次（第 {attempt + 1} 次）", notify=False)
            self.sleep(1)
        if pop:
            # 体力读错了也不怕：真不够会弹「情报拼图补充」。全局「体力」开了自动用药就恢复后再点挑战，没开就当刷完
            if self.auto_potion_enabled() and self.restore_stamina(pop[0]):
                self.log_info("体力不足，已用体力药恢复，重新点「挑战」", notify=True)
                self.next_frame()
                if not self.wait_click_ocr(
                    match=challenge_button_re,
                    box=self.box.bottom_right,
                    time_out=5,
                    after_sleep=2,
                    raise_if_not_found=False,
                ):
                    raise Exception("恢复体力后没找到「挑战」按钮")
            else:
                self.log_info("点挑战弹出体力不足，今天的体力刷完了", notify=True)
                self._cancel_stamina_popup()
                self.wait_ocr(
                    match=challenge_button_re, box=self.box.bottom_right, time_out=5, raise_if_not_found=False
                )
                return 0
        self.auto_battle(end_match=["自律", "挑战"], end_box=self.box.bottom_right)
        self.sleep(1)
        self.next_frame()
        remaining = self._read_stamina(default=current - set_cost)
        self.info_set("remaining_stamina", remaining)
        self.info_incr("手动挑战次数")
        return remaining

    def click_box_by_match_position(self, box: Box | list[Box], match: str | re.Pattern, after_sleep=None):
        if isinstance(box, list):
            box = box[0]
        text = box.name

        # 找匹配位置
        if isinstance(match, str):
            start = text.find(match)
            if start == -1:
                return self.click_box(box)
            end = start + len(match)

        else:  # regex
            m = match.search(text)
            if not m:
                return self.click_box(box)
            start = m.start()
            end = m.end()

        mid = (start + end) / 2
        ratio = mid / len(text)

        x = box.x
        y = box.y
        w = box.width
        h = min(box.height, int(30 / 1080 * self.height))  # 限制高度，避免匹配到下方的按钮

        click_y = y + h // 2

        if ratio < 0.33:
            click_x = x + h
        elif ratio > 0.66:
            click_x = x + w - h
        else:
            click_x = x + w // 2

        self.click(click_x, click_y, after_sleep=after_sleep)

    def fast_disassemble_loop(self, model_re):
        while self.wait_click_ocr(match=["快捷选择"], after_sleep=2):
            ocr_select_num = self.wait_ocr(match=re.compile(model_re), box=self.box.bottom_right)

            if not ocr_select_num:
                self.back(after_sleep=2)
                break

            self.wait_click_ocr(match=["拆解"], box=self.box.bottom_right, after_sleep=2)
            self.wait_pop_up(count=1)

    def enter_fast_disassemble(self):
        # 拆解入口是硬条件
        if not self.wait_click_ocr(match=["拆解"], box=self.box.top_right, after_sleep=2):
            return False

        # 以下是“尽力而为”的筛选条件
        self.wait_click_ocr(match=["工业级及以下未培养"], after_sleep=2)
        self.wait_click_ocr(match=["精密级及以下未培养"], after_sleep=2)

        return True

    def loop_click_ocr(self, match_list, box=None, pop_up_count=1, sleep_after_click=0.5):
        """
        循环点击 OCR 匹配元素，直到找不到为止。
        处理弹窗 pop_up_count。
        """
        if box is None:
            box = self.box.bottom_right
        while self.wait_click_ocr(match=match_list, box=box, raise_if_not_found=False, after_sleep=sleep_after_click):
            if pop_up_count:
                self.wait_pop_up(count=pop_up_count)

    def wait_pop_up(self, time_out=15, other=None, box=None, count=100):
        if box is None:
            box = self.box.bottom
        start = time.time()
        check = pop_ups.copy()
        if other:
            if isinstance(other, list):
                check += other
            else:
                check.append(other)
        found_count = 0
        while (
            self.wait_ocr(
                match=pop_ups,
                box=box,
                settle_time=2,
                time_out=int(time_out - (time.time() - start)),
                raise_if_not_found=False,
            )
            and found_count < count
        ):
            found_count += 1
            self.back(after_sleep=3)

    def press_keys_sequence(self, keys, times, sleep_between=0.5, sleep_after_last=False):
        """
        按顺序按下按键，每次按键后等待 sleep_between 秒，可选择最后一个按键后不等待。
        当按键持续时间为 0 时，不传 down_time 参数给 send_key。
        """
        for i, (key, t) in enumerate(zip(keys, times)):
            if t:  # t != 0
                self.send_key(key, down_time=t)
            else:  # t == 0
                self.send_key(key)
            if i < len(keys) - 1 or sleep_after_last:
                self.sleep(sleep_between)

    def run_steps_with_retry_and_rollback(self, steps):
        """
        执行带重试与回退机制的步骤序列。

        参数:
            steps: List[List[Callable, bool, bool]]
                每个元素为 [func, retry_on_fail, rollback_on_fail]
                - func: 无参可调用对象，成功返回 True，失败返回 False
                - retry_on_fail: 是否允许重试（最多尝试 2 次）
                - rollback_on_fail: 失败且未达重试上限时，是否回退到上一步

        返回:
            bool: 全部成功返回 True，中途失败返回 False
        """
        if not steps:
            return True

        retries = [0] * len(steps)
        i = 0

        while 0 <= i < len(steps):
            func, retry_on_fail, rollback_on_fail = steps[i]

            # 执行当前步骤
            try:
                success = func()
            except Exception:
                success = False

            if success:
                retries[i] = 0
                i += 1
                continue

            # === 处理失败 ===
            if retry_on_fail:
                retries[i] += 1
                if retries[i] >= 2:
                    return False
            else:
                return False

            # 决定是否回退
            if rollback_on_fail and i > 0:
                i -= 1
            # 否则：留在当前步，下一轮重试（因 i 未变）

        return True

    # ------------------------------------------------------------------ 游戏要求重启
    def _game_exe_names(self):
        cfg = getattr(getattr(self, "_app", None), "config", None) or {}
        exes = (cfg.get("windows") or {}).get("exe") or ["GF2_Exilium.exe"]
        if isinstance(exes, str):
            exes = [exes]
        return {e.lower() for e in exes}

    def _game_processes(self):
        import psutil

        names = self._game_exe_names()
        return [p for p in psutil.process_iter(["name"]) if (p.info.get("name") or "").lower() in names]

    def _game_gone(self):
        try:
            gone = not self._game_processes()
        except Exception as e:
            self.log_info(f"查游戏进程失败: {e}", notify=False)
            return False
        if not gone:
            self._game_seen = True
        return gone

    def next_frame(self):
        """
        隔一会儿查一次游戏进程：之前在、现在没了就抛 GameCrashed，交给任务外层重新拉起游戏（不再对着空窗口干等/空点）。
        从没见过游戏进程（截图回放的单测）不算崩溃。
        """
        now = time.time()
        watch = not isinstance(self, TriggerTask) and not getattr(self, "skip_game_check", False)
        if watch and now - getattr(self, "_alive_checked", 0) >= GAME_ALIVE_CHECK_INTERVAL:
            self._alive_checked = now
            if self._game_gone() and getattr(self, "_game_seen", False):
                raise GameCrashed("游戏进程没了")
        return super().next_frame()

    def _wait_game_exit(self, timeout):
        end = time.time() + timeout
        while time.time() < end:
            if not self._game_processes():
                return True
            self.sleep(1)
        return not self._game_processes()

    def _relaunch_game(self):
        """让框架重新拉起游戏：先刷新设备状态（窗口没了 → 未连接），start_device 才会去执行 exe 并等窗口就绪。"""
        from ok import og

        og.device_manager.do_refresh(True)
        self.log_info("重新启动游戏", notify=False)
        self.start_device()
        self.next_frame()

    # ------------------------------------------------------------------ 战斗结算相关的通知框
    def _dismiss_notice(self, boxes):
        """
        实录 2026-10-20：竞技场打赢后先弹「您已晋升至新锐·三，首次晋升可获得补给…」的段位通知，
        盖在「对战胜利」结算页上面；它没有按钮文字，skip_dialogs 认不出就干等 30 秒超时。ESC 能关掉它。
        """
        if not self.find_boxes(boxes, match=rank_up_notice_re):
            return False
        self.log_info("弹出段位晋升通知，按 ESC 关掉", notify=False)
        self.debug_shot("rank_up_notice", boxes)
        self.back(after_sleep=1.5)
        self.next_frame()
        return True

    def _confirm_battle_result(self):
        """
        实录 2026-10-20：竞技场「对战胜利」结算页（积分、作战奖励、伤害统计、确认）只有「确认」能关，
        回主页一直按 ESC 按了 85 秒超时，整个一键日常中断。认出结算页就点「确认」。
        """
        if not self.ocr(match=battle_result_re, log=True):
            return False
        if confirm := self.ocr(box=self.box.bottom, match=re.compile(r"^确认$")):
            self.log_info("在战斗结算页，点「确认」回去", notify=False)
            self.click(confirm, after_sleep=2)
            return True
        return False

    # ------------------------------------------------------------------ 任务开始前：确保游戏已进入主页
    def _game_process_age(self):
        """最年轻的游戏进程已经跑了多少秒；没有进程返回 None，读不到创建时间当成很久。"""
        procs = self._game_processes()
        if not procs:
            return None
        ages = []
        for p in procs:
            try:
                ages.append(time.time() - p.create_time())
            except Exception:
                continue
        return min(ages) if ages else float("inf")

    def _on_title_screen(self):
        self.next_frame()
        return bool(self.ocr(box=self.box.bottom, match=title_start_re, log=True))

    def ensure_game_started(self, time_out=GAME_LAUNCH_MAIN_TIMEOUT):
        """
        每个任务开始前自动做的隐藏步骤：
        游戏没开 → 拉起游戏，等标题页点「点击开始」、关掉公告，直到主页；
        游戏刚被拉起（进程很新）或停在标题页 → 同样点进主页；
        游戏早就开着 → 什么都不做，直接开始任务（推图这类从关卡页开始的任务不会被拖回主页）。
        触发任务（模板监控）每轮都会 run，不走这一步。
        """
        if isinstance(self, TriggerTask) or getattr(self, "skip_game_check", False):
            return False
        age = self._game_process_age()
        launched = False
        if age is None:
            self.log_info("游戏没有打开，先启动游戏再开始任务", notify=True)
            self._relaunch_game()
            launched = True
        elif age < GAME_FRESH_SECONDS:
            self.log_info(f"游戏刚启动 {int(age)} 秒，先进入主页再开始任务", notify=False)
        elif not self._on_title_screen():
            return False
        else:
            self.log_info("游戏停在标题页，点「点击开始」进入主页", notify=False)
        self.ensure_main(recheck_time=2, time_out=time_out)
        return launched

    def _handle_restart_required(self):
        """
        实录 2026-10-20：游戏热更新当天第一次启动，标题页前弹「资源更新完毕，需要重新启动游戏」，只有一个「确认」，
        点了游戏自己退出；不处理的话脚本会在这个框前面按 ESC 直到回主页超时。
        这里点确认 → 等游戏退出（超时就结束进程）→ 框架重新拉起 → 把回主页的超时顺延，交回 is_main 去点「点击开始」。
        """
        if not self.ocr(box=self.box.center, match=restart_required_re, log=True):
            return False
        self.log_info("游戏提示资源更新完毕、需要重新启动，点确认后重新拉起游戏", notify=True)
        self.debug_shot("restart_required")
        if confirm := self.ocr(box=self.box.bottom, match=re.compile(r"^确认$")):
            self.click(confirm, after_sleep=3)
        if not self._wait_game_exit(GAME_EXIT_TIMEOUT):
            self.log_info(f"点确认后 {GAME_EXIT_TIMEOUT} 秒游戏还没退出，直接结束游戏进程", notify=False)
            for proc in self._game_processes():
                try:
                    proc.kill()
                except Exception as e:
                    self.log_info(f"结束游戏进程失败: {e}", notify=False)
            self._wait_game_exit(10)
        self._relaunch_game()
        self._deadline_bump = GAME_RESTART_TITLE_TIMEOUT
        return True

    def kill_all_related_processes(self):
        """尝试杀死游戏进程和本软件自身进程（除当前进程外）"""
        import os

        import psutil
        import win32api
        import win32con
        import win32process

        # 1. 杀死游戏进程
        try:
            hwnd = getattr(self, "hwnd", None)
            if hwnd is not None:
                hwnd_val = getattr(hwnd, "hwnd", None)
                if hwnd_val:
                    tid, pid = win32process.GetWindowThreadProcessId(hwnd_val)
                    handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
                    win32api.TerminateProcess(handle, 0)
                    win32api.CloseHandle(handle)
                    self.log_info(f"已终止游戏进程 pid={pid}", notify=True)
                else:
                    self.log_info("未获取到 hwnd，无法终止游戏进程", notify=True)
            else:
                self.log_info("未获取到 hwnd 属性，无法终止游戏进程", notify=True)
        except Exception as e:
            self.log_info(f"终止游戏进程失败: {e}", notify=True)
        # 2. 杀死本软件所有同名进程（除当前进程）
        try:
            current_pid = os.getpid()
            exe_name = psutil.Process(current_pid).name()
            for proc in psutil.process_iter(["pid", "name"]):
                if proc.info["name"] == exe_name and proc.info["pid"] != current_pid:
                    try:
                        proc.kill()
                        self.log_info(f"已终止本软件进程 pid={proc.info['pid']}", notify=True)
                    except Exception as e2:
                        self.log_info(f"终止本软件进程失败: {e2}", notify=True)
        except Exception as e:
            self.log_info(f"查找/终止本软件进程失败: {e}", notify=True)
