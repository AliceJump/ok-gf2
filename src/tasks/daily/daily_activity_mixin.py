"""限时活动相关：活动自律（物资关卡）、活动层（喝水/吃饭/领奖）、活动列表识别。"""

import re

import win32api
import win32gui

from src.core.BaseGfTask import map_re, parse_time_option, pop_ups
from src.tasks.daily.daily_common_mixin import (
    chapter_suffix_re,
    down_chapter_re,
    middle_chapter_re,
    up_chapter_re,
)

activity_time_re = re.compile(r"^(\d+)\s*(?:天|days?)\s*(\d+)\s*(?:小时|hours?)", re.I)
# 今天已经吃过/喝过时，点「下一步/制作」会弹「提示：当前已有 章鱼小丸子 生效中，是否确认更换?」
# （实录截图 tests/fixtures/food_already_active_1280x768.png；菜名是橙色，OCR 可能把这句拆成几段）
food_active_re = re.compile(r"生效中|是否确认更换|已有.{0,12}生效")

# 活动层走路：各键连续按、中间不停。实录 2026-10-21：角色往旁边跑之后镜头会转到它身后，按键之间停 0.5 秒时
# 镜头转多少每次不一样，后面的 w/d 方向就跟着变，同一组时长有时走到水吧、有时走到沙发边。连续按之后
# 从出生点走的位置稳定，按此重新量过：喝水 d 0.4 偏左、0.8 偏右（停在 NPC 旁），0.6 正好；吃饭 s 0.55～0.78 都能出「美味烹调」。
DRINK_ROUTE = "1.087-1.0-0.6"
EAT_ROUTE = "0.65"
# 旧默认值是按「中间停顿」量的，换成连续按键后已经不对；存着旧默认值的配置按新默认走
LEGACY_ROUTES = {"喝水": ("1.087-1.0-0.8", DRINK_ROUTE), "吃饭": ("1.0", EAT_ROUTE)}


class DailyActivityMixin:
    def activities(self):
        """检查补给活动入口并返回领取结果。"""
        self.info_set("current_task", "activity_stamina")
        return self._collect_supply_activities()

    def _collect_supply_activities(self):
        """逐项领取补给，区分活动缺席与页面未确认并恢复主页。"""
        uncertain = False
        try:
            # 实录（tests/fixtures/activity_page_1280x768.png）：点「活动」后主页 UI 先淡出，约 5~9 秒活动页才出来，
            # 等得太短会误报；真没打开再点一次「活动」，两次都确认不了才待核查
            opened = False
            for attempt in range(2):
                self.wait_click_ocr(
                    match=["活动"], box=self.box._activities, after_sleep=1, time_out=3, raise_if_not_found=False
                )
                opened = self._ensure_supply_menu()
                if opened:
                    break
                if attempt == 0:
                    self.log_info("点了「活动」还没确认活动列表打开，回主页再点一次", notify=False)
                    self.ensure_main()
            if not opened:
                self.info_set("情报补给", "待核查：未确认活动列表打开")
                self.info_set("战前补给", "待核查：未确认活动列表打开")
                return "待核查"
            for reward_activity in ("情报补给", "战前补给"):
                self.info_set(reward_activity, "检查中")
                if not self._open_supply_activity(reward_activity):
                    self.info_set(reward_activity, "未找到入口，跳过")
                    self.log_info(f"{reward_activity}：活动列表中未找到入口，跳过")
                    continue
                if self._claim_supply_activity(reward_activity) == "待核查":
                    uncertain = True
            return "待核查" if uncertain else True
        finally:
            self.ensure_main()

    def _ensure_supply_menu(self, time_out=12):
        """结合侧边列表与主页标识确认活动菜单打开（活动页淡入要 5~9 秒）。"""
        menu_box = self.box_of_screen(0.035, 0.10, 0.23, 0.84)

        def opened():
            """仅在侧栏可识别且不再是主页时确认菜单。"""
            menu = self.ocr(
                box=menu_box,
                match=re.compile(r"^\s*(?:情\s*报\s*补\s*给|战\s*前\s*补\s*给|新\s*手|活\s*动)\s*$"),
            )
            home = self.ocr(box=self.box.right, match=["整备室", "活动层", "招募"])
            names = {re.sub(r"\s+", "", box.name) for box in menu}
            return not home and bool(names & {"情报补给", "战前补给"} or {"新手", "活动"} <= names)

        if self.wait_until(opened, time_out=time_out, settle_time=0):
            self.log_info("已确认活动列表打开")
            return True
        self.log_warning("未确认活动列表打开，跳过补给检查")
        self.screenshot("supply_menu_not_open")
        return False

    def _open_supply_activity(self, reward_activity):
        menu_box = self.box_of_screen(0.035, 0.10, 0.23, 0.84)
        match = re.compile(r"^\s*" + r"\s*".join(map(re.escape, reward_activity)) + r"\s*$")
        # 活动列表会记住滚动位置；从顶部开始，覆盖藏在列表下方的补给入口。
        self._scroll_supply_menu(30)
        for page in range(8):
            if self.wait_click_ocr(
                match=match, box=menu_box, time_out=1, raise_if_not_found=False, after_sleep=0.6, log=True
            ):
                return True
            if page < 7:
                self._scroll_supply_menu(-3)
        return False

    def _scroll_supply_menu(self, count):
        """在游戏前台用真实滚轮滚动补给侧栏。"""
        self.sleep(0.01)
        interaction = getattr(self.executor, "interaction", None)
        if not callable(getattr(interaction, "do_scroll", None)):
            raise RuntimeError("当前输入后端不支持补给列表真实滚轮")
        hwnd = self.hwnd.hwnd
        if not win32gui.IsWindow(hwnd):
            raise RuntimeError("补给列表滚动失败：游戏窗口无效")
        previous_window = win32gui.GetForegroundWindow()
        previous_cursor = win32api.GetCursorPos()
        try:
            if previous_window != hwnd:
                try:
                    win32gui.SetForegroundWindow(hwnd)
                except win32gui.error as error:
                    raise RuntimeError("补给列表滚动失败：游戏未进入前台") from error
                self.sleep(0.05)
            if win32gui.GetForegroundWindow() != hwnd:
                raise RuntimeError("补给列表滚动失败：游戏未进入前台")
            x, y = int(self.width * 0.12), int(self.height * 0.60)
            win32api.SetCursorPos(win32gui.ClientToScreen(hwnd, (x, y)))
            self.sleep(0.1)
            if win32gui.GetForegroundWindow() != hwnd:
                raise RuntimeError("补给列表滚动失败：游戏失去前台焦点")
            interaction.do_scroll(x, y, count)
            self.sleep(0.6)
        finally:
            try:
                win32api.SetCursorPos(previous_cursor)
            except Exception:
                self.log_warning("补给滚动后恢复鼠标位置失败")
            if (
                previous_window != hwnd
                and win32gui.IsWindow(previous_window)
                and win32gui.GetForegroundWindow() == hwnd
            ):
                try:
                    win32gui.SetForegroundWindow(previous_window)
                except Exception:
                    self.log_warning("补给滚动后恢复原窗口失败")

    def _claim_supply_activity(self, reward_activity):
        """验证补给页与领取结果，无法确认时保留待核查。"""
        page_match = re.compile(r"^\s*" + r"\s*".join(map(re.escape, reward_activity)) + r"\s*$")
        claim_match = re.compile(r"^\s*(?:一\s*键\s*)?领\s*取(?:\s*奖\s*励)?\s*$")
        empty_match = re.compile(
            r"已\s*领\s*取|暂无可领取|未到领取时间|未到开放时间|"
            r"(?:\d+\s*天\s*)?\d+\s*:\s*\d{2}\s*:\s*\d{2}\s*后\s*可\s*领取"
        )
        claimed = 0
        for _ in range(10):
            if not self.wait_ocr(match=page_match, box=self.box.right, time_out=3, raise_if_not_found=False):
                self.info_set(reward_activity, "待核查：未确认补给页面")
                return "待核查"
            # 必须完整匹配，不能把「已领取」当成「领取」反复点击。
            if not self.wait_click_ocr(
                match=claim_match, box=self.box.right, time_out=2, raise_if_not_found=False, after_sleep=0.3
            ):
                if claimed:
                    self.info_set(reward_activity, self.tr("已确认领取 {count} 次").format(count=claimed))
                    self.log_info(f"{reward_activity}：已确认领取 {claimed} 次")
                    return True
                if self.wait_ocr(match=empty_match, box=self.box.right, time_out=1, raise_if_not_found=False):
                    self.info_set(reward_activity, "已领取或未到领取时间")
                    return True
                self.info_set(reward_activity, "待核查：未识别到领取按钮或领取状态")
                return "待核查"
            if not self.wait_ocr(match=pop_ups, box=self.box.bottom, time_out=5, raise_if_not_found=False):
                self.info_set(reward_activity, "待核查：点击后未确认奖励弹窗")
                return "待核查"
            self.wait_pop_up(time_out=6, count=1)
            claimed += 1
        self.info_set(reward_activity, "待核查：领取按钮持续出现")
        return "待核查"

    def _enter_free_time_layer(self):
        # 点击命中不代表切页成功；只有活动层 HUD 才能开始移动和交互。
        """有限重试进入活动层，避免主页漏读导致长时间等待。"""
        for attempt in range(3):
            self.log_info(f"尝试进入活动层：第 {attempt + 1}/3 次")
            self.wait_click_ocr(
                match="活动层",
                box=self.box.right,
                time_out=2,
                raise_if_not_found=False,
                after_sleep=0.5,
            )
            if self.is_free_layer(time_out=8):
                return True
            # 已离开主页时可能正在加载，不在未知页面再次点击。
            home = self.ocr(box=self.box.right, match=["整备室", "公共区", "活动层", "招募"])
            if len(home) < 2:
                if self.is_free_layer(time_out=12):
                    return True
                # 额外等待后重新确认主页，避免单次 OCR 漏读提前结束重试。
                home = self.ocr(box=self.box.right, match=["整备室", "公共区", "活动层", "招募"])
                if len(home) < 2:
                    break
        self.log_warning("活动层入口未成功打开，恢复主页后继续后续步骤")
        self.screenshot("activity_layer_entry_failed")
        return False

    def free_time_layer(self):
        """执行活动层日常，区分失败和跳过结果并返回主页。"""
        self.info_set("current_task", "free_time_layer")
        completed = True
        uncertain = False
        for i in range(2):
            if not self._enter_free_time_layer():
                self.ensure_main(time_out=60)
                completed = False
                continue
            if self.is_free_layer(time_out=1):
                if i == 0:
                    drink_result = self.do_food_flow(
                        enter_func=self.go_drink,
                        entry_match=re.compile("茶歇一刻"),
                        main_btn="制作",
                        second_btn="确认",
                        skip_end_match=["饮品加成"],
                        need_extra_confirm=False,
                        done_match=re.compile("今日已饮用"),
                    )
                    if drink_result == "done":
                        self.log_info("今天已经喝过了，跳过喝水", notify=False)
                    elif drink_result is not True:
                        if drink_result == "entry":
                            self.log_warning(
                                f"未找到茶歇一刻入口，角色可能被挡住，请检查「喝水」按键时长，参考 {DRINK_ROUTE}"
                            )
                        elif drink_result == "button":
                            self.log_warning("喝水流程未完成：未找到制作按钮，请检查移动是否到位或界面是否已加载完成")
                        else:
                            self.log_warning("喝水流程未完成：未找到确认按钮，请检查界面是否已加载完成")
                        completed = False

                else:
                    eat_result = self.do_food_flow(
                        enter_func=self.go_eat,
                        entry_match=re.compile("美味烹调"),
                        main_btn="下一步",
                        second_btn="确认邀请",
                        skip_end_match=["前往战役"],
                        need_extra_confirm=True,
                        need_again_test=True,
                    )
                    if eat_result == "done":
                        self.log_info("今天已经吃过了，跳过吃饭", notify=False)
                    elif eat_result is not True:
                        self.log_warning("吃饭流程未完成，请检查移动是否到位或界面是否已加载完成")
                        completed = False
            else:
                self.log_error("没检测到活动层页面")
                completed = False
            self.ensure_main(time_out=60)
        # 奖励领取属于活动层本身；即使关闭浇花，也要进入一次 F2 面板处理逸趣导算奖励。
        if not self._enter_free_time_layer():
            self.ensure_main(time_out=60)
            return False
        if self.is_free_layer(time_out=1):
            if self.config.get("活动层浇花", True):
                water_result = self.water_flowers()
                if water_result is False:
                    completed = False
                elif water_result == "待核查":
                    uncertain = True
            elif self._ensure_activity_panel():
                self._claim_activity_panel_rewards()
            else:
                completed = False
        else:
            self.log_error("没检测到活动层页面，跳过领奖和浇花")
            completed = False
        self.ensure_main(time_out=60)
        return "待核查" if uncertain and completed else completed

    def _ensure_activity_panel(self):
        panel_match = re.compile(
            r"逸\s*趣(?:\s*导\s*算|\s*事\s*件)?|宜\s*居\s*值|栽\s*培|生\s*长\s*阶\s*段|浇\s*灌|一\s*键\s*领\s*取"
        )
        panel_box = self.box_of_screen(0.13, 0.16, 0.87, 0.82)

        def is_open(timeout):
            return bool(
                self.wait_ocr(match=panel_match, box=panel_box, time_out=timeout, raise_if_not_found=False, log=True)
            )

        # 已打开时不要再次按 F2，以免把面板关闭。领奖态也属于已打开状态。
        if is_open(1):
            self.log_info("活动层面板已打开")
            return True
        for attempt in range(2):
            self.log_info(f"尝试打开活动层面板：发送 F2（第 {attempt + 1}/2 次）")
            self.send_key("f2", down_time=0.15, after_sleep=1)
            if is_open(4):
                self.log_info("已确认 F2 面板打开")
                return True
        self.log_info("F2 后未检测到面板，尝试点击顶部 F2 入口")
        if self.wait_click_ocr(
            match=re.compile(r"^F\s*2$"),
            box=self.box_of_screen(0.65, 0, 0.74, 0.12),
            time_out=2,
            raise_if_not_found=False,
            after_sleep=1,
            log=True,
        ):
            if is_open(4):
                self.log_info("点击入口后已确认活动层面板打开")
                return True
        self.log_error("活动层 F2 面板未打开：按键重试及入口点击未成功，跳过领奖和浇花")
        return False

    def _claim_activity_panel_rewards(self):
        """领取逸趣导算进度奖励，并关闭每次领取后的通用奖励弹层。"""
        claim_match = re.compile(r"^\s*(?:一\s*)?键\s*领\s*取\s*$")
        claim_box = self.box_of_screen(0.10, 0.08, 0.95, 0.90)
        claimed = False
        for _ in range(5):
            if not self.wait_click_ocr(
                match=claim_match,
                box=claim_box,
                time_out=1,
                raise_if_not_found=False,
                after_sleep=0.5,
                log=True,
            ):
                break
            claimed = True
            self._close_reward_popup()
        if claimed:
            self.log_info("活动层逸趣导算进度奖励已领取")
        return claimed

    def _close_reward_popup(self, time_out=15):
        """关闭领奖后的「获得道具」弹层：点底部「点击空白处关闭」，不按 ESC（会把 F2 面板一起关掉）。

        实录 2026-10-21：领奖让活动层升到 Lv.10，「获得道具」要等约 12 秒升级动画才出来，
        原来 wait_pop_up(time_out=6) 没等到就返回，弹层一直盖着栽培页签，浇灌被跳过。
        """
        hint = re.compile(r"(?:空\s*白\s*)?处\s*关\s*闭$")
        title = re.compile(r"^获\s*得\s*道\s*具$")
        wait = time_out
        for _ in range(4):
            found = self.wait_ocr(match=[hint, title], time_out=wait, raise_if_not_found=False)
            if not found:
                return True
            hints = [b for b in found if hint.search(b.name)]
            if hints:
                self.click(hints[0], after_sleep=1.5)
            else:
                self.click(0.5, 0.9, after_sleep=1.5)
            wait = 3
        self.log_warning("「获得道具」弹层点了多次仍未关闭")
        return False

    def _dismiss_activity_progress_dialog(self):
        """关闭遮住栽培页签的进度窗口，并确认它已消失。"""
        match = re.compile(r"逸\s*趣\s*导\s*算\s*进\s*度|奖\s*励\s*清\s*单")
        box = self.box_of_screen(0.13, 0.16, 0.87, 0.82)
        if not self.wait_ocr(match=match, box=box, time_out=1, raise_if_not_found=False):
            return True
        self.back(after_sleep=1)
        if self.wait_ocr(match=match, box=box, time_out=2, raise_if_not_found=False):
            self.log_warning("逸趣导算进度窗口未关闭，跳过被遮挡的栽培入口")
            return False
        return True

    def water_flowers(self):
        """验证浇灌次数，无法识别栽培入口时标记待核查。"""
        self.info_set("current_task", "water_flowers")
        if not self._ensure_activity_panel():
            self.info_set("浇灌", "已跳过：未识别到栽培入口")
            self.log_info("未识别到栽培入口，跳过浇灌并继续后续任务")
            return "待核查"
        # F2 可能先停在逸趣导算奖励页；先处理奖励，再导航到栽培。
        self._claim_activity_panel_rewards()
        if self._dismiss_activity_progress_dialog() is False:
            self.info_set("浇灌", "待核查：进度窗口未关闭")
            return "待核查"
        watering_match = re.compile(r"浇\s*灌")
        # F2 可能直接选中栽培页；优先识别内容，避免依赖选中页签的黑字。
        on_watering_page = self.wait_ocr(match=watering_match, box=self.box.right, time_out=2, raise_if_not_found=False)
        on_overview = False
        if not on_watering_page:
            on_overview = self.wait_ocr(
                match=re.compile(r"栽\s*培\s*天\s*数|生\s*长\s*阶\s*段"),
                box=self.box_of_screen(0.36, 0.43, 0.85, 0.59),
                time_out=2,
                raise_if_not_found=False,
                log=True,
            )
        if on_overview:
            self.log_info("F2 已打开栽培概览，直接前往浇灌")
        if not on_watering_page and not on_overview:
            # 未进入栽培页时才切换页签，允许文字前带图标。
            if not self.wait_click_ocr(
                match=re.compile(r"栽\s*培"),
                box=self.box_of_screen(0.30, 0.15, 0.42, 0.25),
                time_out=10,
                raise_if_not_found=False,
                after_sleep=2,
                log=True,
            ):
                self.info_set("浇灌", "已跳过：未识别到栽培入口")
                self.log_info("未识别到栽培入口，跳过浇灌并继续后续任务")
                return "待核查"
        if not self.wait_ocr(match=watering_match, box=self.box.right, time_out=3, raise_if_not_found=False):
            # 部分界面先显示栽培概览，需点击“前往”才进入花盆页面。
            if not self.wait_click_ocr(
                match=re.compile("前往"),
                box=self.box.bottom_right,
                time_out=5,
                raise_if_not_found=False,
                after_sleep=3,
                log=True,
            ):
                self.info_set("浇灌", "已跳过：未识别到浇灌入口")
                self.log_info("未识别到浇灌入口，跳过浇灌并继续后续任务")
                return "待核查"
        watering_buttons = self.wait_ocr(
            match=watering_match, box=self.box.right, time_out=10, raise_if_not_found=False
        )
        if not watering_buttons:
            self.info_set("浇灌", "已跳过：未进入浇灌页面")
            self.log_info("未进入浇灌页面，跳过浇灌并继续后续任务")
            return "待核查"
        # 用按钮文字定位下方次数。旧固定区域只框住“浇灌”，漏掉了次数。
        # 限制在浇灌这一列，避免把右侧施肥的 1/1 当成浇水完成。
        watering_button = watering_buttons[0]
        center_x = (watering_button.x + watering_button.width / 2) / self.width
        bottom_y = (watering_button.y + watering_button.height) / self.height
        count_box = self.box_of_screen(
            max(0, center_x - 0.05), bottom_y, min(1, center_x + 0.05), min(1, bottom_y + 0.12)
        )
        done_match = re.compile(r"^\s*1\s*[/／]\s*1\s*$")
        if self.wait_ocr(match=done_match, box=count_box, time_out=1, raise_if_not_found=False):
            self.log_info("今日已浇灌，跳过重复浇花")
            self.back(after_sleep=2)
            return True
        if not self.wait_click_ocr(
            match=watering_match, box=self.box.right, time_out=5, raise_if_not_found=False, after_sleep=2, log=True
        ):
            self.log_error("未找到浇灌按钮，跳过浇花")
            return False
        self.wait_pop_up(count=1, time_out=5)
        completed = bool(
            self.wait_ocr(match=done_match, box=count_box, time_out=10, raise_if_not_found=False, log=True)
        )
        if not completed:
            self.log_error("点击浇灌后未检测到次数 1/1，浇花未确认完成")
        # 关闭栽培页面后，由活动层共用的 ensure_main 处理退出确认。
        self.back(after_sleep=2)
        return completed

    def _skip_active_food_buff(self, next_match=None):
        """仅处理已生效饮食的覆盖提示，取消重复制作并验证弹窗关闭。"""
        # 只点「取消」，千万不能点确认（会把材料再花一遍）；后半段同 food_active_re，覆盖 OCR 把这句拆成几段的情况
        duplicate = re.compile(
            r"同名(?:菜品|饮品)已生效|覆盖已生效(?:菜品|饮品)|当前已有.+?生效中.*确认更换|生效中|是否确认更换|已有.{0,12}生效"
        )

        def page_state():
            """页面状态判定：无重复弹窗且出现预期界面"""
            if self.ocr(match=duplicate, box=self.box.center):
                return False
            if next_match is not None:
                return bool(self.ocr(match=next_match, box=self.box.center))
            return (
                not self.ocr(match="饮品加成")
                and len(self.ocr(match=["Esc", "P", "M", "F1", "F2", "F3", "F4"], box=self.box.top)) >= 5
            )

        if not self.wait_until(
            lambda: self.ocr(match=duplicate, box=self.box.center),
            time_out=3,
            raise_if_not_found=False,
        ):
            return None
        if not self.wait_click_ocr(
            match="取消",
            box=self.box.center,
            time_out=2,
            raise_if_not_found=False,
            after_sleep=0.5,
        ):
            self.screenshot("food_duplicate_cancel_failed")
            return False
        if not self.wait_until(page_state, time_out=3, settle_time=0):
            self.screenshot("food_duplicate_dialog_blocked")
            return False
        self.log_info("已确认同名饮食增益生效，取消重复制作，继续日常")
        return True

    def _confirm_drink_result(self):
        """确认饮品结果页已关闭并回到活动层，丢失点击最多重试三次。"""

        def returned_to_layer():
            # time_out=0 在 ok-script 中使用默认超时，不能用于外层轮询。
            # HUD 同样直接读取当前帧，避免 is_free_layer 内部再次等待。
            """单帧确认结果页消失且活动层 HUD 出现，避免嵌套默认超时。"""
            return (
                not self.ocr(match="饮品加成")
                and len(self.ocr(match=["Esc", "P", "M", "F1", "F2", "F3", "F4"], box=self.box.top)) >= 5
            )

        for attempt in range(3):
            if not self.wait_click_ocr(
                match=re.compile(r"^\s*确\s*认\s*$"),
                box=self.box.bottom,
                time_out=3,
                raise_if_not_found=False,
                after_sleep=1,
            ):
                if returned_to_layer():
                    return True
            elif self.wait_until(returned_to_layer, time_out=4, settle_time=0.3):
                return True
            self.log_warning(f"饮品加成确认后未返回活动层，重试 {attempt + 1}/3")
        self.screenshot("drink_result_blocked")
        return False

    def do_food_flow(
        self,
        *,
        enter_func,
        entry_match,
        main_btn,
        second_btn,
        skip_end_match,
        need_extra_confirm=False,
        need_again_test=False,
        done_match=None,
    ):
        """
        返回 True 表示流程完成；'done' 表示今天已经做过（已跳过）；失败时返回 'entry'、'button' 或 'confirm' 表示失败阶段。
        done_match：进到界面后右下角出现这个字样（如喝水的「今日已饮用」）就说明今天做过了，直接退出。
        """
        enter_func(after_sleep=1)
        times = 1
        if need_again_test:
            times = 2
        for attempt in range(times):
            result = self.wait_ocr(match=entry_match, time_out=3)
            if not result:
                # 实录：走完站在了交互点旁边（图标已经显示）但提示文字没出来，往前/往后蹭一小步再看
                for key, hold in (("w", 0.25), ("s", 0.4)):
                    self.log_info(f"没看到「{entry_match.pattern}」提示，按 {key} {hold}s 微调位置再找", notify=False)
                    self.press_keys_sequence([key], [hold], sleep_between=0)
                    self.sleep(0.8)
                    if result := self.wait_ocr(match=entry_match, time_out=2):
                        break
            if result:
                drink_done = False
                if main_btn == "制作":
                    for entry in result:
                        name = getattr(entry, "name", "")
                        title = re.search(r"茶\s*歇\s*一\s*刻", name)
                        if not title:
                            continue
                        count = re.search(r"(\d+)\s*[/／]\s*(\d+)\s*$", name[title.end() :])
                        if count:
                            drink_done = count.groups() == ("1", "1")
                        else:
                            # 计数可能被 OCR 分成独立框，只读取入口旁及下方的局部区域。
                            h = entry.height
                            count_box = self.box_of_screen(
                                max(0, (entry.x - h) / self.width),
                                max(0, (entry.y - h / 2) / self.height),
                                min(1, (entry.x + entry.width + 4 * h) / self.width),
                                min(1, (entry.y + 3 * h) / self.height),
                            )
                            drink_done = bool(
                                self.ocr(
                                    match=re.compile(r"^\s*1\s*[/／]\s*1\s*$"),
                                    box=count_box,
                                    log=True,
                                )
                            )
                        if drink_done:
                            break
                if drink_done:
                    self.log_info("茶歇一刻 1/1：今日喝水已完成，跳过重复制作")
                    return True
                self.click_with_key("alt", result)
            else:
                self.screenshot(f"food_entry_missing_{entry_match.pattern}")
                return "entry"
            if done_match is not None and self.wait_ocr(
                match=done_match, box=self.box.bottom_right, time_out=3, raise_if_not_found=False, log=True
            ):
                # 实录截图 tests/fixtures/drink_already_done_1280x768.jpg：右下角按钮变成「今日已饮用」
                self.log_info(f"右下角显示「{done_match.pattern}」，今天已经做过，退出", notify=True)
                self.screenshot("food_already_done")
                self.back(after_sleep=2)
                return "done"
            if self.wait_click_ocr(match=main_btn, box=self.box.bottom_right, time_out=10):
                duplicate_result = self._skip_active_food_buff(next_match=second_btn if main_btn == "下一步" else None)
                if duplicate_result is True:
                    return True
                if duplicate_result is False:
                    return "confirm"
                if main_btn == "制作":
                    confirm_match = re.compile(r"^\s*确\s*认\s*$")
                    if not self.wait_until(lambda: bool(self.ocr(match=confirm_match)), time_out=3, settle_time=0):
                        if not self.ocr(match="制作", box=self.box.bottom_right):
                            self.screenshot("food_make_unknown_page")
                            return "confirm"
                        if not self.wait_click_ocr(match="制作", box=self.box.bottom_right, time_out=2):
                            # 页面可能在重试前后推进；点击未命中时再确认一次结果页。
                            if not self.wait_until(
                                lambda: bool(self.ocr(match=confirm_match)), time_out=3, settle_time=0
                            ):
                                self.screenshot("food_make_retry_failed")
                                return "confirm"
                        duplicate_result = self._skip_active_food_buff()
                        if duplicate_result is True:
                            return True
                        if duplicate_result is False:
                            return "confirm"
                        if not self.wait_until(lambda: bool(self.ocr(match=confirm_match)), time_out=3, settle_time=0):
                            self.screenshot("food_make_not_advanced")
                            return "confirm"
                if not self.wait_click_ocr(match=second_btn, time_out=3, after_sleep=2):
                    # 实录：今天已经吃过饭时点「下一步」后不会出现「确认邀请」，留下画面文字和截图，好判断是不是"已完成"
                    self.log_info(f"没找到「{second_btn}」，当前画面文字见下一行 OCR 日志", notify=False)
                    self.ocr(log=True)
                    self.screenshot("food_second_button_missing")
                    return "confirm"
                if need_extra_confirm:
                    self.wait_click_ocr(match="确认", time_out=3, after_sleep=1)
                self.skip_dialogs(end_match=skip_end_match, time_out=60)
                if skip_end_match == ["饮品加成"]:
                    if self._confirm_drink_result() is False:
                        self.log_error("饮品加成确认失败：结果页未关闭")
                        return "confirm"
                    return True
                self.wait_click_ocr(match="确认", time_out=3, box=self.box.bottom, after_sleep=1)
                self.wait_pop_up(count=1)
                return True
            else:
                if need_again_test and attempt == 0:
                    continue
                else:
                    self.ocr(log=True, screenshot=True)
                    self.screenshot("food_main_button_missing")
                    self.back(after_sleep=2)
                    return "button"
        return "button"

    def _route(self, key):
        value = str(self.config.get(key) or "").strip()
        legacy, current = LEGACY_ROUTES[key]
        if not value or value == legacy:
            if value:
                self.log_info(f"「{key}」还是旧默认值 {legacy}（按停顿走量的），改用连续按键的 {current}", notify=False)
            return current
        return value

    def go_drink(self, after_sleep=None):
        down_times = parse_time_option(self._route("喝水"))
        self.press_keys_sequence(["a", "w", "d"], down_times, sleep_between=0)
        if after_sleep and after_sleep > 0:
            self.sleep(after_sleep)

    def go_eat(self, after_sleep=None):
        down_time = float(self._route("吃饭"))
        self.press_keys_sequence(["s"], [down_time], sleep_between=0)
        if after_sleep and after_sleep > 0:
            self.sleep(after_sleep)

    def activity(self):
        activity_wuzi_names = [name.strip() for name in str(self.config.get("当前物资关卡名称")).split("-")]
        self.info_set("current_task", "activity")
        self.set_lineup_kind("活动")
        if to_activity_page := self.wait_click_ocr(
            match=["限时开启"], box=self.box.top_right, after_sleep=2, raise_if_not_found=False, time_out=4
        ):
            if activities := self.wait_ocr(match=["开启中"], box=self.box.bottom_left, time_out=4):
                activity_count = 0
                for activity in activities:
                    self.ensure_main()
                    self.click(to_activity_page, after_sleep=2)
                    self.click(activity)
                    if activity_count >= len(activity_wuzi_names):
                        activity_count -= 1
                    name_re = activity_wuzi_names[activity_count]
                    activity_count += 1
                    chapter_re = re.compile(rf"{re.escape(name_re)}[·・：]{chapter_suffix_re}")
                    to_clicks = self.wait_ocr_until_count(
                        match=[chapter_re], box=None, min_count=2, timeout=5, settle_time=2, log=True
                    )
                    if to_clicks:
                        up = None
                        middle = None
                        down = None
                        for click in to_clicks:
                            if up_chapter_re.search(click.name):
                                up = click
                            elif middle_chapter_re.search(click.name):
                                middle = click
                            elif down_chapter_re.search(click.name):
                                down = click

                        chapter_boxes = [box for box in (up, middle, down) if box]
                        wuzi_boxes = self.wait_ocr(
                            match=re.compile("物资"), box=None, time_out=4, settle_time=2, log=True
                        )
                        click_boxes = (
                            self._filter_boxes_near_candidates(chapter_boxes, wuzi_boxes) if wuzi_boxes else []
                        )

                        if not click_boxes:
                            click_boxes = chapter_boxes

                        click_boxes = sorted(click_boxes, key=self._chapter_click_order)

                        for chapter in click_boxes:
                            self.click(chapter, after_sleep=0.2)
                    elif to_clicks := self.wait_ocr(
                        match=["活动战役", re.compile("物资")],
                        box=self.box.bottom,
                        raise_if_not_found=False,
                        time_out=4,
                        settle_time=2,
                        log=True,
                    ):
                        self.click(to_clicks, after_sleep=2)
                    if to_clicks:
                        self.sleep(2)
                        if wu_zi := self.ocr(match=re.compile("物资"), box=self.box.bottom_right):
                            self.click(wu_zi, after_sleep=0.5)
                        battles = self.wait_ocr(match=map_re, time_out=4)
                        if battles:
                            self.click(battles[-1])
                            self.fast_combat(set_cost=1, battle_max=6, activity=True)
            else:
                self.log_info("找不到开启的活动")
        self.ensure_main()

    def find_activities(self):
        return self.wait_ocr(match=[activity_time_re], box=self.box.bottom_left, raise_if_not_found=False, time_out=4)

    def find_latest_activity(self):
        boxs = self.find_activities()

        def parse_time(name):
            match = activity_time_re.match(name)
            if match:
                days = int(match.group(1))
                hours = int(match.group(2))
                return days * 24 + hours
            return 0

        if not boxs:
            return None
        longest = max(boxs, key=lambda b: parse_time(b.name))
        return longest
