"""战斗与班组：体力本、竞技场、班组尘烟。（国服模拟作战里没有兵棋推演，旧的 bingqi 已删）"""

import re

import cv2
import win32api
import win32gui

from src.core.BaseGfTask import stamina_re
from src.core.lineup_config import preset_name_for_kind, support_enabled_for_kind
from src.tasks.daily.daily_public_mixin import loop_covers

OUTPOST_KIND = "尘烟前哨战"
power_re = re.compile(r"^\d{3,6}$")
# 尘烟前线卡片在两期之间显示「12天22小时后开启」
chenyan_not_open_re = re.compile(r"后\s*开\s*启|未\s*开\s*启|未\s*开\s*放")
# 班组助战弹窗里战力前面有个图标，实录 OCR 成「心25850」
support_power_re = re.compile(r"^\D?\d{4,6}$")


def power_of(box):
    return int(re.sub(r"\D", "", box.name))


# 前哨战编队界面右下「阵容」：我方格子在左，最右一格是班组助战（关掉助战开关时也是我方格子）
OUTPOST_OWN_SLOTS = (0.61, 0.69, 0.87, 0.83)
OUTPOST_SUPPORT_SLOT = (0.87, 0.69, 0.97, 0.83)


def sort_characters_by_priority(chars, priority):
    """
    Sorts a list of character objects based on their 'char_name' attribute,
    according to a priority list.

    Characters whose 'char_name' attribute appears in the priority list are
    placed at the front, sorted by their order within the priority list.
    Characters not in the priority list retain their original order.

    Args:
        chars: A list of character objects, where each object has a 'char_name' attribute (string).
        priority: A list of character names (strings) representing the priority order.

    Returns:
        A new list of character objects, sorted according to the priority.  The
        original `chars` list is not modified.
    """

    priority_map = {name: index for index, name in enumerate(priority)}
    sorted_chars = []

    for i, the_char in enumerate(chars):  # Use enumerating to get the original index
        char_name = the_char.name.lower()
        if char_name in priority_map:
            sorted_chars.append((priority_map[char_name], i, the_char))  # (priority_index, original_index, char_object)
        else:
            sorted_chars.append((len(priority), i, the_char))  # (lowest_priority, original_index, char_object)

    sorted_chars.sort()  # Sort the list of tuples

    return [char_object for _, _, char_object in sorted_chars]  # Extract the character objects


class DailyBattleMixin:
    def _open_campaign_tab(self, tab, expect, fallback_xy):
        """
        战役推进页顶部切页签（补给作战/模拟作战）。实录 2560x1440：页面还在过渡时按固定坐标点一下会落空，
        停在「剧情战役」；现在按文字点，点完确认目标内容出现，没出现再点，最多 3 次。
        """
        for attempt in range(3):
            if not self.wait_click_ocr(
                match=tab, box=self.box.top, time_out=3, after_sleep=1, raise_if_not_found=False, log=True
            ):
                self.click_relative(fallback_xy[0], fallback_xy[1], after_sleep=1)
            if self.wait_ocr(match=expect, time_out=3, raise_if_not_found=False):
                return True
            self.log_info(f"点了「{tab}」页签但还没看到目标内容，再点一次（第 {attempt + 1} 次）", notify=False)
            self.next_frame()
        self.screenshot(f"campaign_tab_{tab}")
        raise Exception(f"战役推进里切不到「{tab}」页签，看 campaign_tab 截图")

    def battle(self):
        if loop_covers(self, "体力"):
            self.log_info("自主循环已经消耗体力，跳过体力本 / 刷钱本")
            return
        self.info_set("current_task", "battle")
        self.set_lineup_kind("体力本")
        self.wait_click_ocr(
            match=re.compile("战役推进"), box=self.box.top_right, after_sleep=0.5, raise_if_not_found=True
        )
        self.wait_ocr(match=re.compile("补给作战"), box=self.box.top_right, raise_if_not_found=True)
        self._open_campaign_tab("补给作战", re.compile("军备解析|深度搜索|决策构象|标准同调"), (0.78, 0.05))
        if self.is_adb():
            self.swipe_relative(0.8, 0.6, 0.5, 0.6, duration=1)
        self.sleep(1)
        remaining = 10000
        if self.config.get("刷钱本"):
            self.wait_click_ocr(match=["标准同调"], box=self.box.right, after_sleep=0.5, raise_if_not_found=True)
            remaining = self.fast_combat(battle_max=4, set_cost=20)
            self.back(after_sleep=1)
        target = self.config.get("体力本")
        cost_dict = {"深度搜索": 10, "军备解析": 10, "决策构象": 20, "定向精研": 30}
        min_stamina = cost_dict.get(target, 30)
        if remaining >= min_stamina:
            ding_xiang = self.stamina_options.index(target) >= 3
            if ding_xiang:
                target = "定向精研"
            self.wait_click_ocr(match=target, settle_time=1, after_sleep=0.5, raise_if_not_found=True, log=True)
            # if ding_xiang:
            #     self.wait_click_ocr(match=re.compile(self.config.get('体力本')),
            #                         box=self.box_of_screen(0.01, 0.21, 0.73, 0.31),
            #                         settle_time=0.5,
            #                         after_sleep=0.5, log=True,
            #                         raise_if_not_found=True)
            while remaining >= min_stamina:
                if ding_xiang:
                    remaining = self.fast_combat(plus_x=0.69, plus_y=0.59, set_cost=cost_dict[target])
                else:
                    remaining = self.fast_combat(set_cost=cost_dict.get(target))
        self.ensure_main()

    def arena(self):
        if loop_covers(self, "实兵演习"):
            self.log_info("自主循环已经打过实兵演习，跳过竞技场")
            return
        self.info_set("current_task", "arena")
        self.set_lineup_kind("竞技场")
        self.wait_click_ocr(
            match=re.compile("战役推进"), box=self.box.top_right, after_sleep=1, raise_if_not_found=True
        )
        self.wait_ocr(match=re.compile("补给作战"), box=self.box.top_right, raise_if_not_found=True)
        self._open_campaign_tab("模拟作战", "实兵演习", (0.89, 0.05))
        self.wait_click_ocr(match=["实兵演习"], box=self.box.bottom, after_sleep=0.5, raise_if_not_found=True)
        self.wait_pop_up(time_out=15, count=1)
        remaining_count = self.arena_remaining()
        if remaining_count > 1:
            self.wait_click_ocr_with_pop_up("进攻", box=self.box.bottom_right)
            self.sleep(2)
            self.challenge_arena_opponent()
            self.back()
            self.sleep(1)
        # if count > 0:
        #     self.click_relative(0.34 if self.is_adb() else 0.26, 0.89, after_sleep=0.5)
        #     if not self.wait_ocr(match=['演习补给'], box=self.box.top, time_out=4):
        #         self.wait_pop_up(time_out=4)
        if self.wait_click_ocr(match=["周期奖励"], box=self.box.left, after_sleep=1, raise_if_not_found=True):
            self.wait_click_ocr(match=[re.compile("键领取")], after_sleep=1, raise_if_not_found=False)
        self.ensure_main()

    def arena_remaining(self):
        return int(self.ocr(0.89, 0.01, 0.99, 0.1, match=stamina_re)[0].name.split("/")[0])

    def challenge_arena_opponent(self):
        challenged = 0
        waited_pop_up = False
        while True:
            remaining_count = self.arena_remaining()
            self.log_info(f"challenge_arena_opponent remaining_count {remaining_count}")
            if remaining_count <= 1:
                self.log_info(f"challenge arena complete {remaining_count}")
                break
            boxes = self.ocr(0, 0.51, 0.94, 0.59, match=re.compile(r"^[1-9]\d*$"))
            if len(boxes) < 3:
                if not waited_pop_up:
                    waited_pop_up = True
                    self.wait_pop_up(time_out=15) and self.wait_pop_up(time_out=15) and self.wait_pop_up(time_out=15)
                    continue
                else:
                    raise Exception("找不到五个演习对手")
            self.log_info(f"arena opponents {boxes}")
            for box in boxes:
                if remaining_count - challenged <= 1:
                    self.log_info(f"challenged enough return {remaining_count} {challenged}")
                    return challenged
                if int(box.name) < 5000:
                    search_success = box.copy()
                    search_success.width = self.width_of_screen(0.17)
                    search_success.height = self.height_of_screen(0.15)
                    search_success.y -= search_success.height
                    if not self.ocr(match=re.compile("挑战"), box=search_success, log=True):
                        self.log_info(f"challenge opponent {box.name}")
                        self.click(box)
                        self.wait_click_ocr(
                            match=["进攻"], box=self.box.bottom_right, after_sleep=0.5, raise_if_not_found=True
                        )
                        self.auto_battle(end_match="刷新")
                        self.sleep(3)
                        challenged += 1
                        continue
            if self.ocr(match=["刷新消耗"], box=self.box.bottom_right):
                self.log_info("no refresh count remains")
                return challenged
            self.wait_click_ocr(match="刷新", box=self.box.bottom_right, after_sleep=2, raise_if_not_found=True)
        return challenged

    def guild(self):
        """执行班组要务和尘烟，尘烟出错时返回主页并报告失败。"""
        self.info_set("current_task", "guild")
        self.set_lineup_kind("班组")
        if result := self.wait_ocr(match=["班组"], box=self.box._group, raise_if_not_found=True):
            self.click_box_by_match_position(result, "班组", after_sleep=2)
            if loop_covers(self, "每日要务"):
                self.log_info("自主循环已经打过每日要务，跳过")
            else:
                self.wait_click_ocr(match=["要务"], box=self.box.bottom_right, after_sleep=0.5, settle_time=2)
                result = self.wait_ocr(
                    match=["开始作战", "每日要务已完成"], box=self.box.bottom_right, raise_if_not_found=True, log=True
                )
                if result[0].name == "开始作战":
                    self.click(result)
                    self.auto_battle()
                    self.wait_ocr(
                        match=["开始作战", "每日要务已完成", "要务"], box=self.box.bottom_right, raise_if_not_found=True
                    )
                else:
                    self.log_info("每日要务已完成")
                self.back()
                self.sleep(1)
            if loop_covers(self, "尘烟前线"):
                self.log_info("自主循环已经打过尘烟前线，跳过")
            elif self.chenyan() is False:
                self.ensure_main()
                return False

            if loop_covers(self, "班组奖励"):
                self.log_info("自主循环已经领过班组奖励，跳过补给领取")
            else:
                self.wait_click_ocr(match=["补给"], box=self.box.bottom_right, after_sleep=0.5)
                if result := self.wait_ocr(
                    match=["领取全部"], box=self.box.bottom_right, time_out=4, raise_if_not_found=False
                ):
                    self.click_box(result)
                    self.wait_pop_up(count=1)
                self.back()
                self.sleep(1)
        self.ensure_main()

    def chenyan(self):
        """
        按当前剩余票数执行尘烟，每次作战后重新读取次数。
        返回 True 表示打完或确认可以跳过，False 表示没完成（已留截图），None 表示没进去但还停在班组页。
        """
        if not self.config.get("尘烟"):
            return True

        def failed(reason):
            """记录失败原因并保留现场，向调用者返回明确失败。"""
            self.log_warning(f"尘烟未完成：{reason}")
            self.info_set("尘烟前线", f"待核查：{reason}")
            self.screenshot("Chenyan_EntryOrTicketsFailed")
            return False

        end = self.wait_ocr(match=re.compile("前线"), box=self.box.bottom_right, time_out=5, log=True)
        if not end:
            return failed("未找到尘烟前线入口")
        # 实录 2026-10-22：两期之间卡片底下是「12天22小时后开启」，点了进不去；原来照样按返回，
        # 直接退出了班组页，后面的「补给」找不到，班组补给天天漏领
        if not_open := self.ocr(match=chenyan_not_open_re, box=self.box.bottom_right):
            self.log_info(f"尘烟前线还没开放（{not_open[0].name}），跳过", notify=False)
            self.info_set("尘烟", f"未开放：{not_open[0].name}")
            return True
        self.click(end, after_sleep=1)
        # 页面切换和后台截图可能延迟；先确认尘烟页，避免把其他页面的数字当成次数。
        if not self.wait_ocr(match=["攻坚战", "前哨战"], box=self.box.top_right, time_out=10, log=True):
            if self.ocr(match=["补给", "要务"], box=self.box.bottom_right):
                # 点了卡片没进去、还停在班组页：不能按返回，否则后面的「补给」就找不到了
                self.log_info("尘烟前线没进去，还在班组页，跳过", notify=False)
                self.info_set("尘烟前线", "待核查：点了入口还在班组页")
                return None
            return failed("点击入口后未确认进入尘烟页面")
        result = self.wait_ocr(match=stamina_re, box=self.box.top_right, time_out=10, log=True)
        if not result:
            return failed("未读取到剩余挑战次数，不能按次数耗尽跳过")
        assault_locked = False
        bought = False
        # 每天 2 次（开了「尘烟买第3次」再花晶条买 1 次）；多留一轮余量，防止次数读不准时死循环
        for _ in range(5):
            tickets = int(result[0].name.split("/")[0])
            self.log_info(f"chenyan tickets {tickets}")
            self.info_set("chenyan tickets", tickets)
            if tickets == 0:
                if self.config.get("尘烟买第3次") and not bought and self._chenyan_buy_ticket():
                    bought = True
                else:
                    self.log_info("尘烟前线已确认剩余 0 次，跳过作战")
                    self.info_set("尘烟前线", "已确认剩余 0 次")
                    break
            elif not assault_locked:
                self.wait_click_ocr(match="攻坚战", box=self.box.top_right, after_sleep=0.5, raise_if_not_found=True)
                self.next_frame()
                if locked := self.ocr(match=re.compile("解锁"), box=self.box.bottom_right):
                    # 实录：指挥官 41 级时右下角按钮是「指挥官60级后解锁」，攻坚战打不了，改打前哨战
                    self.log_info(f"尘烟攻坚战还没解锁（{locked[0].name}），改打前哨战", notify=True)
                    self.info_set("尘烟", f"攻坚战未解锁：{locked[0].name}")
                    assault_locked = True
                    continue
                self.wait_click_ocr(match="开始作战", box=self.box.bottom_right, after_sleep=2, raise_if_not_found=True)
                if not self.choose_chenyan(tickets):
                    return False
                self.sleep(2)
            else:
                if not self.chenyan_outpost():
                    break
                self.sleep(2)
            result = self.wait_ocr(match=stamina_re, box=self.box.top_right, time_out=10, log=True)
            if not result:
                return failed("作战后未读取到剩余挑战次数")
        self.back(after_sleep=2)
        return True

    def _chenyan_buy_ticket(self):
        """
        右上角次数旁的「+」：弹「参战机会补充」，消耗 50 坍塌晶条换 1 次，「本日剩余1」。
        剩余 0 或晶条不够就取消。返回是否买到。
        """
        self.click_relative(0.9715, 0.0444, after_sleep=1.5)
        if not self.wait_ocr(match=re.compile("参战机会补充"), box=self.box.top, time_out=3):
            self.log_info("尘烟：点了「+」没弹出参战机会补充")
            return False
        self.next_frame()
        texts = [b.name for b in self.ocr(box=self.box.center)]
        left = next((m.group(1) for t in texts if (m := re.search(r"本日剩余\s*(\d+)", t))), None)
        self.log_info(f"尘烟参战机会补充: 本日剩余 {left} {texts[:6]}")
        if left is None or left == "0" or any("不足" in t for t in texts):
            self.wait_click_ocr(match=re.compile("^取消$"), box=self.box.bottom, time_out=3, after_sleep=1)
            return False
        if not self.wait_click_ocr(match=re.compile("^确认$"), box=self.box.bottom, time_out=3, after_sleep=2):
            return False
        # 晶条不够时游戏会再弹提示，点掉就算没买到
        if self.ocr(match=re.compile("不足"), box=self.box.center):
            self.log_info("尘烟：坍塌晶条不足，没买到")
            self.wait_click_ocr(match=re.compile("^(取消|确认)$"), box=self.box.bottom, time_out=3, after_sleep=1)
            return False
        self.log_info("尘烟：花 50 坍塌晶条买了第 3 次", notify=True)
        self.info_set("尘烟买第3次", "已买")
        return True

    def chenyan_outpost(self):
        """
        前哨战打一场：切到前哨战 → 开始作战 → 编队界面选整备室编队、按战力上人、按设置借班组助战 → 确定开打。
        编队和借不借助战按全局「阵容与助战」的「尘烟前哨战」场景取值。
        """
        self.info_set("current_task", "chenyan_outpost")
        self.wait_click_ocr(match="前哨战", box=self.box.top_right, after_sleep=1, raise_if_not_found=True)
        start = self.wait_ocr(match="开始作战", box=self.box.bottom_right, time_out=3)
        if not start:
            self.log_info("前哨战右下角没有「开始作战」，跳过")
            self.info_set("尘烟前哨战", "没有开始作战")
            return False
        self.click(start, after_sleep=2)
        if not self.wait_ocr(match="选择人形", box=self.box_of_screen(0.02, 0.26, 0.3, 0.33), time_out=10):
            self.debug_shot("chenyan_outpost_no_lineup")
            raise Exception("前哨战点了开始作战，没进编队界面")
        cfg = self._lineup_cfg()
        support = support_enabled_for_kind(cfg, OUTPOST_KIND)
        self._outpost_select_preset(preset_name_for_kind(cfg, OUTPOST_KIND))
        support = self._outpost_set_support_toggle(support)
        # 开助战时我方 4 格 + 助战 1 格；关助战时我方 5 格
        self._outpost_fill_top_power(4 if support else 5)
        if support:
            self._outpost_pick_support()
        self.next_frame()
        self.debug_shot("chenyan_outpost_ready")
        self.wait_click_ocr(match="确定", box=self.box.bottom_right, after_sleep=2, raise_if_not_found=True)
        # 没坐满（比如今天能上的人不够、助战没借上）会弹「仍有可上阵的位置，是否依然开始作战」
        if self.wait_ocr(match=re.compile("仍有可上阵"), time_out=2):
            self.log_info("阵容没坐满，确认直接开战")
            self.wait_click_ocr(match=re.compile("^确认$"), box=self.box.bottom, after_sleep=2, raise_if_not_found=True)
        # 前哨战的阵容在编队界面已经定好，战斗里不再走部署界面的整理阵容
        kind = self._lineup_kind
        self.set_lineup_kind(None)
        try:
            self.auto_battle("开始作战", self.box.bottom_right)
        finally:
            self.set_lineup_kind(kind)
        self.info_incr("尘烟前哨战")
        return True

    @staticmethod
    def _outpost_name_match(text, name):
        """编队名比对：容忍 OCR 多读/少读一个字，但多出来或少掉的是数字就不算（「编队1」不能命中「编队10」）。"""
        t, n = (text or "").replace(" ", ""), name.replace(" ", "")
        if t == n:
            return True
        if n in t and len(t) - len(n) <= 1:
            return not t.replace(n, "", 1).isdigit()
        if t and t in n and len(n) - len(t) <= 1:
            return not n.replace(t, "", 1).isdigit()
        return False

    def _outpost_select_preset(self, name):
        """「选择人形」下拉框切到整备室编队 name；留空不切。点当前已选中的项不会收起列表，要点标题收起。"""
        if not name:
            return
        header_box = self.box_of_screen(0.03, 0.32, 0.52, 0.375)
        if any(self._outpost_name_match(b.name, name) for b in self.ocr(box=header_box)):
            self.log_info(f"前哨战编队已是「{name}」")
            return
        self.click_relative(0.508, 0.349, after_sleep=1)
        list_box = self.box_of_screen(0.03, 0.38, 0.52, 0.68)
        chosen = False
        for _ in range(4):
            hit = [b for b in self.ocr(box=list_box) if self._outpost_name_match(b.name, name)]
            if hit:
                self.click_box(hit[0], after_sleep=1)
                chosen = True
                break
            self.scroll_relative(0.27, 0.55, -3)
            self.sleep(0.8)
        self.next_frame()
        if len([b for b in self.ocr(box=list_box) if re.search(r"编队|整备室", b.name)]) >= 2:
            self.click_relative(0.508, 0.349, after_sleep=1)
        if chosen:
            self.log_info(f"前哨战切到编队「{name}」", notify=True)
        else:
            self.log_info(f"前哨战编队列表里没找到「{name}」，沿用当前编队", notify=True)

    def _outpost_slot_count(self, support_slot=False):
        """阵容格子里有人时格子底下显示战力数字。support_slot=False 时最右格不算（开助战时它是助战格）。"""
        area = (
            (OUTPOST_OWN_SLOTS[0], OUTPOST_OWN_SLOTS[1], OUTPOST_SUPPORT_SLOT[2], OUTPOST_SUPPORT_SLOT[3])
            if support_slot
            else OUTPOST_OWN_SLOTS
        )
        return len(self.ocr(box=self.box_of_screen(*area), match=power_re))

    def _outpost_fill_top_power(self, slots):
        """先撤掉阵容里已有的人，再按卡片底下的战力从高到低点，点了没上场（如今天已出战）就换下一个。"""
        # 关助战时 5 格都是我方；开助战时最右格是助战，清空只清我方格
        slot_box = self.box_of_screen(
            *(
                OUTPOST_OWN_SLOTS
                if slots == 4
                else (OUTPOST_OWN_SLOTS[0], OUTPOST_OWN_SLOTS[1], OUTPOST_SUPPORT_SLOT[2], OUTPOST_SUPPORT_SLOT[3])
            )
        )
        for _ in range(6):
            filled = self.ocr(box=slot_box, match=power_re)
            if not filled:
                break
            self.click_box(filled[0], after_sleep=0.5)
        cards = self.ocr(box=self.box_of_screen(0.02, 0.37, 0.53, 0.9), match=power_re)
        cards.sort(key=power_of, reverse=True)
        picked = []
        for card in cards:
            if len(picked) >= slots:
                break
            before = self._outpost_slot_count(support_slot=slots == 5)
            self.click_box(card, after_sleep=0.6)
            if self._outpost_slot_count(support_slot=slots == 5) > before:
                picked.append(card.name)
            else:
                self.log_info(f"战力 {card.name} 的人形点了没上场，换下一个")
        self.log_info(f"前哨战上场 {len(picked)}/{slots}：战力 {', '.join(picked)}", notify=True)

    def _outpost_support_on(self):
        """「本次作战使用班组人形助战」开关：开是橙色勾（饱和度高），关是灰底叉。"""
        self.next_frame()
        h, w = self.frame.shape[:2]
        region = self.frame[int(0.625 * h) : int(0.66 * h), int(0.912 * w) : int(0.938 * w)]
        sat = float(cv2.cvtColor(region, cv2.COLOR_BGR2HSV)[..., 1].mean())
        return sat > 100

    def _outpost_set_support_toggle(self, want):
        on = self._outpost_support_on()
        if on != want:
            self.click_relative(0.9255, 0.642, after_sleep=1)
            on = self._outpost_support_on()
        self.log_info(f"前哨战班组助战：{'开' if on else '关'}（设置：{'借' if want else '不借'}）")
        return on

    def _outpost_pick_support(self):
        """
        助战格空着就点「助战」打开班组助战弹窗，借战力最高的人形：点卡片选中后按钮变「入队」，点了弹窗关掉就算借上。
        助战格已经有人（游戏会记住上一场）就沿用。借不到就关掉弹窗不借。
        """
        if borrowed := self.ocr(box=self.box_of_screen(*OUTPOST_SUPPORT_SLOT), match=power_re):
            self.log_info(f"助战格已有人形（战力 {borrowed[0].name}），沿用")
            return True
        if not self.wait_click_ocr(
            match=re.compile("^助战$"), box=self.box_of_screen(0.85, 0.79, 0.97, 0.87), time_out=3, after_sleep=1.5
        ):
            self.log_info("没找到「助战」按钮，不借助战")
            return False
        popup_title = self.box_of_screen(0.4, 0.14, 0.6, 0.22)
        if not self.wait_ocr(match="班组助战", box=popup_title, time_out=5):
            self.log_info("班组助战弹窗没打开，不借助战")
            return False
        cards = self.ocr(box=self.box_of_screen(0.18, 0.28, 0.83, 0.74), match=support_power_re, log=True)
        cards.sort(key=power_of, reverse=True)
        for card in cards[:3]:
            # 点头像会打开人形详情，点战力数字（卡片正文）才是选中
            self.click_box(card, after_sleep=1)
            self.wait_click_ocr(
                match=re.compile("^(入队|确认)$"),
                box=self.box_of_screen(0.62, 0.74, 0.83, 0.84),
                time_out=2,
                after_sleep=1.5,
            )
            self.next_frame()
            if not self.ocr(match="班组助战", box=popup_title):
                self.log_info(f"前哨战借班组助战：战力 {power_of(card)}", notify=True)
                return True
            self.log_info(f"战力 {power_of(card)} 的助战没借上，换下一个")
        self.debug_shot("chenyan_outpost_support_fail")
        self.click_relative(0.813, 0.178, after_sleep=1)
        self.log_info("班组助战没借上，关掉弹窗不借", notify=True)
        return False

    def _select_chenyan_attribute(self, attr):
        """切换助战属性，OCR 漏读时在确认列表后使用比例坐标。"""
        if self.wait_click_ocr(match=attr, box=self.box_of_screen(0.28, 0.24, 0.81, 0.29), time_out=2, after_sleep=1):
            return True
        # 选中页签和属性图标会被 OCR 漏读；只在确认助战列表后使用固定比例位置。
        if not self.wait_ocr(match="班组助战", box=self.box_of_screen(0.35, 0.12, 0.65, 0.24), time_out=2):
            return False
        positions = {"物理": 0.313, "燃烧": 0.405, "电导": 0.500, "冷凝": 0.592, "酸蚀": 0.684, "浊刻": 0.776}
        self.click_relative(positions[attr], 0.264, after_sleep=1)
        return True

    def _scroll_chenyan_list(self, count):
        """可取消地滚动一页；Unity 列表需要前台的真实滚轮。"""
        self.sleep(0.01)
        executor = getattr(self, "executor", None)
        if executor is not None and executor.paused:
            return False
        if self.is_adb():
            self.swipe_relative(0.65, 0.72 if count > 0 else 0.40, 0.65, 0.40 if count > 0 else 0.72, duration=0.3)
        else:
            interaction = getattr(executor, "interaction", None)
            scroll = getattr(interaction, "do_scroll", None)
            if not callable(scroll):
                scroll = getattr(interaction, "scroll", None)
            if not callable(scroll):
                raise RuntimeError("当前输入后端不支持助战列表真实滚轮")
            hwnd = self.hwnd.hwnd
            if not win32gui.IsWindow(hwnd):
                raise RuntimeError("助战列表滚动失败：游戏窗口无效")
            previous_window = win32gui.GetForegroundWindow()
            previous_cursor = win32api.GetCursorPos()
            try:
                if previous_window != hwnd:
                    try:
                        win32gui.SetForegroundWindow(hwnd)
                    except Exception as error:
                        raise RuntimeError("助战列表滚动失败：游戏未进入前台") from error
                    self.sleep(0.05)
                if win32gui.GetForegroundWindow() != hwnd:
                    raise RuntimeError("助战列表滚动失败：游戏未进入前台")
                x, y = int(self.width * 0.65), int(self.height * 0.60)
                win32api.SetCursorPos(win32gui.ClientToScreen(hwnd, (x, y)))
                self.sleep(0.1)
                if executor.paused:
                    return False
                if win32gui.GetForegroundWindow() != hwnd:
                    raise RuntimeError("助战列表滚动失败：游戏失去前台焦点")
                scroll(x, y, -3 if count > 0 else 3)
                self.sleep(0.15)
            finally:
                try:
                    win32api.SetCursorPos(previous_cursor)
                except Exception:
                    self.log_warning("助战滚动后恢复鼠标位置失败")
                if previous_window != hwnd and win32gui.IsWindow(previous_window) and win32gui.GetForegroundWindow() == hwnd:
                    try:
                        win32gui.SetForegroundWindow(previous_window)
                    except Exception:
                        self.log_warning("助战滚动后恢复原窗口失败")
        self.sleep(0.05)
        return True

    def _chenyan_list_snapshot(self):
        """按比例裁取卡片区域，缩小副本用于判断页面是否实际变化。"""
        frame = self.frame
        if frame is None or frame.size == 0:
            return None
        height, width = frame.shape[:2]
        cards = frame[int(height * 0.31):int(height * 0.79), int(width * 0.18):int(width * 0.82), :3]
        if cards.size == 0:
            return None
        return cv2.resize(cards, (256, 144), interpolation=cv2.INTER_AREA)

    def _find_chenyan_assist(self, name):
        """逐页查找指定助战，仅在文字和卡片画面都未变化时提前停止。"""
        previous = None
        previous_image = None
        for page in range(100):
            self.sleep(0.01)
            executor = getattr(self, "executor", None)
            if executor is not None and executor.paused:
                return None
            chars = self.ocr(0.18, 0.31, 0.82, 0.79)
            found = next((char for char in chars if char.name.casefold() == name.casefold()), None)
            if found is not None:
                return found
            visible = chars
            self.log_info(f"助战翻页搜索 {name} 第{page + 1}页: {[box.name for box in visible]}")
            signature = tuple((box.name, round(box.x / 10), round(box.y / 10)) for box in visible)
            image = self._chenyan_list_snapshot()
            # 同名角色可以来自不同玩家；必须同时确认卡片画面基本不变。
            # 缩图降低分辨率与采集噪声影响，忽略不超过 0.5% 的轻微变化。
            same_image = (
                previous_image is not None and image is not None
                and (cv2.absdiff(previous_image, image).max(axis=2) > 12).mean() <= 0.005
            )
            if previous is not None and signature == previous and same_image:
                self.log_info(f"助战列表未移动，结束搜索: {name}")
                break
            previous = signature
            previous_image = image
            if page < 99 and self._scroll_chenyan_list(1) is False:
                return None
        return None

    def _find_priority_chenyan_assist(self, name):
        """已知角色按属性查找，未录入属性的首选角色遍历属性页。"""
        attr = self.get_role_by_name(name)
        for candidate_attr in ([attr] if attr else self.roles_dict):
            if not self._select_chenyan_attribute(candidate_attr):
                continue
            char = self._find_chenyan_assist(name)
            if char is not None:
                return char
        return None

    def _chenyan_candidates(self):
        """提取卡片名称，排除等级、按钮和短装饰文字。"""
        chars = self.ocr(0.18, 0.31, 0.82, 0.79)
        valid = re.compile(
            r"^(?!.*(?:[LlVv][Vv]?\.?\s*\d|等级|战力|入队|确认|确定|心\s*\d))(?=.*[A-Za-z\u4e00-\u9fff]).{2,20}$"
        )
        return [
            char
            for char in chars
            if valid.fullmatch(char.name) and (re.search(r"[\u4e00-\u9fff]", char.name) or len(char.name) >= 3)
        ]

    def _is_chenyan_list(self):
        """排除弹窗后按标题确认列表，允许属性和当前卡片同时漏读。"""
        if self.ocr(
            match=["确认", "取消", re.compile("队伍中有相同角色"), "火控预演方案", "Firepower Preview", "Combat Effectiveness"],
            box=self.box_of_screen(0.2, 0.25, 0.8, 0.78),
        ):
            return False
        return bool(
            self.wait_ocr(match="班组助战", box=self.box_of_screen(0.35, 0.12, 0.65, 0.24), time_out=1)
        )

    def _restore_chenyan_list(self):
        """取消冲突或关闭详情，False 可重试，None 表示恢复失败。"""
        self.wait_click_ocr(match="取消", box=self.box_of_screen(0.28, 0.65, 0.50, 0.75), time_out=0.5, after_sleep=0.3)
        if self._is_chenyan_list():
            return False
        for _ in range(2):
            self.back(after_sleep=1)
            if self._is_chenyan_list():
                return False  # 列表已恢复，可以尝试下一位。
        self.log_error("未能返回助战列表，停止本次尘烟作战")
        return None  # 恢复失败，禁止继续使用旧列表坐标。

    def _try_chenyan_assist(self, char, duplicates):
        """尝试入队，True 成功，False 可重试，None 终止流程。"""
        self.click(char, after_sleep=1)
        join = self.wait_ocr(match=["入队", "替换"], box=self.box.bottom_right, time_out=3)
        if not join:
            self.screenshot("chenyan_join_missing")
            # 国际服详情页文字可能是英文；无论详情文字是否可识别，都返回列表。
            return self._restore_chenyan_list()
        self.click_box(join, after_sleep=1)
        result = self.wait_ocr(match=["确认", "确定"], box=self.box.bottom_right, time_out=3)
        if not result:
            self.screenshot("chenyan_confirm_missing")
            return self._restore_chenyan_list()
        if any(box.name == "确认" for box in result):
            duplicates.add(char.name)
            self.log_info(f"duplicate char {sorted(duplicates)}")
            return self._restore_chenyan_list()
        self.log_info(f"助战已入队: {char.name}")
        return True

    def _order_chenyan_candidates(self, chars):
        """容忍 OCR 行位置偏移，按从上到下、每行从左到右排序。"""
        rows = []
        for char in sorted(chars, key=lambda box: box.y + box.height / 2):
            center = char.y + char.height / 2
            if rows and abs(center - rows[-1][0]) <= max(char.height, rows[-1][1]) / 2:
                rows[-1][2].append(char)
            else:
                rows.append((center, char.height, [char]))
        return [char for _, _, row in rows for char in sorted(row, key=lambda box: box.x)]

    def choose_chenyan(self, tickets):
        """配置自有人形和可用助战，只有编队确认成功才启动作战。"""
        existing = self.ocr(box=self.box_of_screen(0.61, 0.69, 0.88, 0.83), match=re.compile(r"^\d+$"))
        for exist in existing:
            self.click_box(exist, after_sleep=0.1)
        self.click_relative(0.28, 0.35, after_sleep=0.2)
        self.click_relative(0.21, 0.64, after_sleep=0.2)
        self.click_relative(0.28, 0.35, after_sleep=0.2)
        if tickets == 2:
            self.click_relative(0.16, 0.47, after_sleep=0.2)  # 编队1
        else:
            self.click_relative(0.16, 0.56, after_sleep=0.2)  # 编队2
        x_start = 0.06
        step = (0.24 - 0.03) / 3
        for i in range(4):
            self.click_relative(x_start + step * i, 0.45, after_sleep=0.2)

        self.wait_click_ocr(
            match="助战", box=self.box.bottom_right, settle_time=1, after_sleep=1, raise_if_not_found=True
        )
        priority = [
            "OTs-14",
            "威玛西娜",
            "可露凯",
            "夏安",
            "罗蕾莱",
            "春田",
            "莱妮",
            "妮基塔",
            "玛绮朵",
            "洛贝拉",
            "托洛洛",
            "琼玖",
        ]
        selected = False
        my_chars = set()
        # 排除顶部属性/装饰区；允许国际服名称和未录入角色表的新角色。

        for name in priority:
            char = self._find_priority_chenyan_assist(name)
            if char is None:
                continue

            joined = self._try_chenyan_assist(char, my_chars)
            if joined is None:
                return False
            if joined:
                selected = True
                break
        if not selected:
            self.log_info("no priority char joined, fallback start")

            attr_order = ["物理", "酸蚀", "浊刻", "燃烧", "冷凝", "电导"]

            for attr in attr_order:
                if not self._select_chenyan_attribute(attr):
                    continue

                chars = self._order_chenyan_candidates(self._chenyan_candidates())

                for char in chars:
                    if char.name in my_chars:
                        continue

                    joined = self._try_chenyan_assist(char, my_chars)
                    if joined is None:
                        return False
                    if joined:
                        self.log_info(f"fallback joined char: {char.name}")
                        selected = True
                        break

                if selected:
                    break

        if not selected:
            self.log_error("未找到可入队的助战角色，停止本次尘烟作战")
            return False
        if not self.wait_click_ocr(match="确定", box=self.box.bottom_right, time_out=5):
            self.log_error("助战入队后未找到编队确定按钮，停止本次尘烟作战")
            return False
        self.auto_battle("开始作战", self.box.bottom_right)
        return True
