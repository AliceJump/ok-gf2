import functools
import os
import re
import sys
import threading
import time
import traceback

from ok import BaseTask, Box, Logger, TriggerTask, find_boxes_by_name

from src.core.base_mixin.runtime_mixin import RuntimeMixin
from src.core.debug_config import DEBUG_OPTION_NAME, KEY_DEBUG_SHOT
from src.core.debug_shot import save_debug_shot
from src.data.FeatureList import FeatureList as fL
from src.image.frame_processs import isolate_by_hsv_ranges
from src.image.hsv_config import HSVRange as hR
from src.interaction.ScreenPosition import ScreenPosition

logger = Logger.get_logger(__name__)
pop_ups = ["点击空白处关闭", "点击屏幕任意位置继续", "点击任意位置继续", "新周期开启", "周期已重置"]
number_re = re.compile(r"^\d+$")
stamina_re = re.compile(r"^\d+/\d+")
map_re = re.compile(r"^.{0,2}\s*-?\s*\d{1,2}\s*-\s*\d{1,2}\s*\*?$")
# 战斗中界面的标志：右下角「行动结束」或左上角「01/12 回合」计数
battle_ui_re = re.compile(r"行动结束|\d{1,2}\s*/\s*\d{1,2}\s*回合")
stamina_popup_re = re.compile(r"情报拼图补充|情报.{0,3}补充|体力不足|体力补充")
WATCHDOG_TIMEOUT = 120  # 秒：这么久没有任何进展（没点击、没日志、没换阶段）看门狗就截图报警
WATCHDOG_KILL_LEVEL = 2  # 停滞达到 WATCHDOG_TIMEOUT 的这个倍数、而且不是人为暂停，就自动停止任务
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


def _with_game_started(run):
    """给任务的 run 套一层：先 ensure_game_started（游戏没开就拉起、标题页点进主页），再跑任务本身。"""

    @functools.wraps(run)
    def wrapped(self, *args, **kwargs):
        self.ensure_game_started()
        return run(self, *args, **kwargs)

    wrapped._ensures_game = True
    return wrapped


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


def parse_time_option(option: str) -> list[float]:
    """
    将配置中的时间字符串解析为浮点数列表
    例如 "1.087-1.4-0.5" -> [1.087, 1.4, 0.5]
    """
    return [float(x) for x in option.split("-")]


class BaseGfTask(RuntimeMixin, BaseTask):
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

    def skip_dialogs(self, end_match, end_box=None, time_out=120, has_dialog=True, raise_if_not_found=True):
        self.info_set("current_task", "skip_dialogs")
        start = time.time()
        while time.time() - start < time_out:
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
            else:
                if has_dialog and not self._is_loading_frame(boxes):
                    self.click_relative(0.95, 0.04)
                self.sleep(2)
            self.next_frame()
        if raise_if_not_found:
            raise Exception("跳过剧情超时!")

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
        self, end_match=None, end_box=None, has_dialog=False, need_click_auto=False, has_dialog_behind_start=False
    ):
        self.info_set("current_task", "auto battle")
        result = self.skip_dialogs(
            end_match=["作战开始", "行动结束", "继续前进"],
            end_box=self.box.bottom,
            time_out=120,
            has_dialog=has_dialog,
            raise_if_not_found=False,
        )
        if result and result[0].name == "继续前进":
            self.log_info("开局检测到继续前进，点击后开启新一轮自动战斗", notify=True)
            self.click_box(result, after_sleep=2)
            self.auto_battle(
                end_match=end_match,
                end_box=end_box,
                has_dialog=has_dialog,
                need_click_auto=need_click_auto,
                has_dialog_behind_start=has_dialog_behind_start,
            )
            return
        if result[0].name == "作战开始":
            self.sleep(2)
            self.click_box(result, after_sleep=1)
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
            if start_result and "继续前进" in start_result[0].name:
                self.log_info("开局后检测到继续前进，点击后开启新一轮自动战斗", notify=True)
                self.click_box(start_result, after_sleep=2)
                self.auto_battle(
                    end_match=end_match,
                    end_box=end_box,
                    has_dialog=has_dialog,
                    need_click_auto=need_click_auto,
                    has_dialog_behind_start=has_dialog_behind_start,
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
                        self.click_box(start_result, after_sleep=2)
                        self.auto_battle(
                            end_match=end_match,
                            end_box=end_box,
                            has_dialog=has_dialog,
                            need_click_auto=need_click_auto,
                            has_dialog_behind_start=has_dialog_behind_start,
                        )
                        return
                    if self.wait_ocr(match="注意", box=self.box.top):
                        self.wait_click_ocr(match="取消", after_sleep=2)
                if start_result and need_click_auto:
                    self.sleep(0.5)
                    while self.ocr(match="行动结束", box=self.box.bottom_right):
                        if self.is_adb():
                            self.click_relative(0.85, 0.05, after_sleep=1)
                        else:
                            self.click_relative(0.88, 0.04, after_sleep=1)

        clicked_continue = False
        while results := self.skip_dialogs(
            end_match=["任务完成", "任务失败", "战斗失败", "对战胜利", "对战失败", "确认", "确认结算", "继续前进"],
            time_out=900,
            has_dialog=has_dialog,
        ):
            # 优先遍历所有结果找"继续前进"
            clicked = False
            for result in results:
                if result.name == "继续前进":
                    self.click_box(result, after_sleep=2)
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
        if not results:
            raise Exception("自动战斗异常")
        if results[0].name == "任务失败":
            raise Exception("任务失败, 没打过!")
        if clicked_continue:
            self.log_info("检测到继续前进，点击后开启新一轮自动战斗", notify=True)
            self.auto_battle(
                end_match=end_match,
                end_box=end_box,
                has_dialog=has_dialog,
                need_click_auto=need_click_auto,
                has_dialog_behind_start=has_dialog_behind_start,
            )
            return
        if self.wait_click_ocr(match="继续前进", box=self.box.bottom_right, raise_if_not_found=False, time_out=3):
            self.log_info("结算后检测到继续前进，点击后开启新一轮自动战斗", notify=True)
            self.auto_battle(
                end_match=end_match,
                end_box=end_box,
                has_dialog=has_dialog,
                need_click_auto=need_click_auto,
                has_dialog_behind_start=has_dialog_behind_start,
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

        self.wait_click_ocr(match=["自律"], box=self.box.bottom_right, after_sleep=2, raise_if_not_found=True)
        if self.break_if_not_enough():
            self.wait_ocr(match=["自律"], box=self.box.bottom_right, raise_if_not_found=True)
            return 0
        boxes = self.ocr(log=True, threshold=0.8, frame_processor=self.make_hsv_isolator(hR.WHITE))
        if next_step := self.find_boxes(boxes, "下一步", self.box.bottom_right):
            self.click(next_step, after_sleep=1)
            boxes = self.ocr(log=True, threshold=0.8, frame_processor=self.make_hsv_isolator(hR.WHITE))
            # default_cost = 30
        current = self.ocr(match=[stamina_re, number_re], box=self.box_of_screen(0.84, 0, 0.99, 0.10))
        if current:
            current = int(current[0].name.split("/")[0])
        else:
            current = 1
        self.sleep(1)
        if (
            len(find_boxes_by_name(boxes, ["确认", "取消", "上一步"])) != 2
            and len(find_boxes_by_name(boxes, ["确认", "取消", "上", "一步"])) != 3
        ):
            if self.debug:
                self.screenshot("fast_no_zilv")
            self.log_info("自律没有弹窗, 可能是调度权限不足")
            return current
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

        if self.click(find_boxes_by_name(boxes, "前往"), after_sleep=2):
            if self.enter_fast_disassemble():
                self.fast_disassemble_loop(stamina_re)

            self.click(find_boxes_by_name(boxes, "确认"), after_sleep=2)

        self.wait_pop_up(count=1)
        self.wait_ocr(match=["自律"], box=self.box.bottom_right, raise_if_not_found=True)

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
