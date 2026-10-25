import re

import cv2
from ok import Logger

from src.core.BaseGfTask import BaseGfTask, stamina_re
from src.image.hsv_config import HSVRange as hR

logger = Logger.get_logger(__name__)
# 首领挑战左上角「当前层级4/9」、右下角「消耗0/1」（持有/每场需要）
boss_level_re = re.compile(r"当前层级\s*(\d+)\s*/\s*(\d+)")
boss_cost_re = re.compile(r"消耗\s*(\d+)\s*/\s*(\d+)")
BOSS_MAX_LEVEL = 9
pattern_kt = re.compile(r"^(?!(?=.*开拓之王)(?=.*区域开拓))(?:开拓之王|区域开拓(?:I|II|III|IV|V|VI|VII))$")


class WeeklyTask(BaseGfTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "周常"
        self.description = ""
        self.support_schedule_task = True
        self.default_config.update(
            {
                "首领挑战": True,
                "峰值推定": True,
                "扩编实练": True,
            }
        )

    def run(self):
        self.reset_lineup(None)
        self.ensure_main(recheck_time=2, time_out=90)
        tasks = [("首领挑战", self.boss_fast), ("峰值推定", self.peak_estimate_tion), ("扩编实练", self.deep_battle)]
        for key, func in tasks:
            if self.config.get(key):
                if func:
                    func()
        self.log_info("周常完成!", notify=True)

    def boss_fast(self):
        self.info_set("current_task", "boss_fast")
        self.wait_click_ocr(match=re.compile("战役推进"), box="top_right", after_sleep=0.5, raise_if_not_found=True)
        self.wait_click_ocr(match=re.compile("模拟作战"), box="top_right", raise_if_not_found=True)
        self.wait_click_ocr(match=re.compile("首领挑战"), raise_if_not_found=True, after_sleep=2)
        # 页面会记住上次的标签，停在「歧路挑战」（50 级解锁）时没有自律按钮，先切回「常规挑战」
        self.wait_click_ocr(match=re.compile("常规挑战"), box="top_right", time_out=3, after_sleep=1)
        # 用户要求 2026-10-25：常规挑战没到最高层（9 层）时先「开始作战」手动打，完成全部挑战目标层级才会升；
        # 到 9 层后才用「自律」。每打一场都要消耗一张「挑战权限」（右下角「消耗 有/需」），不够就停。
        for _ in range(BOSS_MAX_LEVEL):
            level, top = self._boss_level()
            if not self._boss_ticket_enough():
                break
            if level is None:
                self.log_info("没读到首领挑战的当前层级，按原来的方式直接自律")
                self.fast_combat(set_cost=1, click_all=True)
                break
            if level >= top:
                self.log_info(f"首领挑战已在最高层级 {level}/{top}，自律")
                self.fast_combat(set_cost=1, click_all=True)
                break
            self.log_info(f"首领挑战当前层级 {level}/{top}，还没到最高层，开始作战自动打", notify=True)
            if not self._boss_battle():
                break
            after, _ = self._boss_level()
            if after is None or after <= level:
                self.log_info(f"打完层级还是 {after}/{top}（挑战目标没全完成），不再重复消耗挑战权限", notify=True)
                break
        self.ensure_main()

    def _boss_level(self):
        """左上角「当前层级 4/9」，读不到返回 (None, BOSS_MAX_LEVEL)。"""
        if result := self.wait_ocr(match=boss_level_re, box="left", time_out=3):
            level, top = boss_level_re.search(result[0].name).groups()
            return int(level), int(top)
        return None, BOSS_MAX_LEVEL

    def _boss_ticket_enough(self):
        """右下角「消耗 0/1」：前面是持有的挑战权限、后面是每场要的；读不到时按够处理，交给游戏判断。

        实录 2026-10-25：持有 0 时点「开始作战」「自律」都没有任何反应，原来会白点一圈再当成完成。
        """
        if result := self.wait_ocr(match=boss_cost_re, box="bottom_right", time_out=2):
            have, need = map(int, boss_cost_re.search(result[0].name).groups())
            if have < need:
                self.log_info(f"首领挑战的挑战权限不够（消耗 {have}/{need}），跳过", notify=True)
                return False
        return True

    def _boss_battle(self):
        """点「开始作战」进部署界面自动打一场，打完回到首领挑战页；没进战斗或打输返回 False。"""
        if not self.wait_click_ocr(match="开始作战", box="bottom_right", time_out=5, after_sleep=2):
            self.log_info("首领挑战没找到「开始作战」，跳过")
            return False
        # 部署界面按「首领挑战编队」切整备室编队并补满
        self.set_lineup_kind("首领挑战")
        try:
            self.auto_battle(has_dialog=True)
        except Exception as e:
            if "没打过" not in str(e):
                raise
            self.log_info("首领挑战这一场没打过", notify=True)
            return False
        finally:
            self.set_lineup_kind(None)
            self.wait_pop_up(count=1)
        if not self.wait_ocr(match=re.compile("常规挑战"), box="top_right", time_out=15):
            self.screenshot("boss_not_back")
            self.log_info("首领挑战打完没回到挑战页面，停止")
            return False
        return True

    def peak_estimate_tion(self):
        self.info_set("current_task", "peak_estimate_tion")
        self.wait_click_ocr(match=re.compile("战役推进"), box="top_right", after_sleep=0.5, raise_if_not_found=True)
        self.wait_click_ocr(match=re.compile("模拟作战"), box="top_right", raise_if_not_found=True, after_sleep=2)
        self.wait_click_ocr(match=re.compile("峰值推定"), raise_if_not_found=True, after_sleep=2)
        self.wait_pop_up(count=1)
        self.wait_click_ocr(match=re.compile("常规峰值"), box="bottom_right", time_out=2, after_sleep=2)
        max_retry = 3
        for attempt in range(max_retry):
            temp = self.wait_ocr(match=re.compile("周期报酬"), box="bottom_left", time_out=2)
            if temp:
                self.click(temp[0], after_sleep=2)
                if self.wait_click_ocr(match=re.compile("一键领取"), time_out=2, after_sleep=2):
                    self.wait_pop_up(count=1)
                    self.back()
                break
            self.back()
        for attempt in range(max_retry):
            temp = self.wait_ocr(match=re.compile("极限峰值"), box="bottom_right", time_out=2)
            if temp:
                self.click(temp[0], after_sleep=2)
                self.click(temp[0], after_sleep=2)
                if not self._tab_selected(re.compile("极限峰值")):
                    self.log_info("极限峰值未解锁，跳过")
                    break
                if attempt == 0:
                    self.wait_pop_up(count=1)
                for i in range(max_retry):
                    if self.wait_click_ocr(match=re.compile("0" + str(i + 1)), after_sleep=2):
                        temp = self.wait_ocr(match=["开始作战"], box="bottom_right", raise_if_not_found=True, log=True)
                        if temp[0].name == "开始作战":
                            self.click(temp)
                            if not self.wait_ocr(match=re.compile("激化等级不足"), time_out=2):
                                self.auto_battle(has_dialog=True)
                            else:
                                self.back(after_sleep=2)
                            if self.wait_ocr(match=re.compile("激化阶群"), box="top_right", time_out=3):
                                self.back(after_sleep=2)
                break
            self.back()
        self.ensure_main()

    def deep_battle(self):
        """
        扩编实练：一关一关往后打特殊增强，直到当期实练奖励的星数满了 / 没有解锁的关 / 打输。
        打完一关页面会往右滚，所以每轮都重新找卡片，点最右边那张已解锁的（解锁的卡片标题底是白的，锁着的是灰的）。
        """
        self.info_set("current_task", "deep_battle")
        self.wait_click_ocr(match=re.compile("战役推进"), box="top_right", after_sleep=0.5, raise_if_not_found=True)
        self.wait_click_ocr(match=re.compile("模拟作战"), box="top_right", raise_if_not_found=True, after_sleep=2)
        self.wait_click_ocr(match=re.compile("扩编实练"), raise_if_not_found=True, after_sleep=2)
        self.wait_pop_up(count=1)
        if self.ocr(match=re.compile("扩编实练已结束")):
            self.log_info("本期扩编实练已结束，跳过")
            self.wait_click_ocr(match=re.compile("^确认$"), box="bottom", time_out=3, after_sleep=2)
            self.ensure_main()
            return
        # 特殊增强是部署关：进部署界面后按「扩编实练编队」切整备室编队并补满
        self.set_lineup_kind("扩编实练")
        try:
            for _ in range(12):
                if self._deep_stars_full():
                    break
                card = self._deep_frontier_card()
                if self.ocr(match=re.compile("扩编实练已结束")):
                    self.log_info("本期扩编实练已结束")
                    self.wait_click_ocr(match=re.compile("^确认$"), box="bottom", time_out=3, after_sleep=2)
                    break
                if card is None:
                    self.log_info("扩编实练没有已解锁的特殊增强关卡，结束")
                    break
                self.click(card, after_sleep=2)
                if not self.wait_click_ocr(match="开始作战", box="bottom_right", time_out=5, after_sleep=2, log=True):
                    self.log_info("点了特殊增强没出现「开始作战」，结束")
                    self.back(after_sleep=2)
                    break
                try:
                    self.auto_battle(has_dialog=True, need_click_auto=True, has_dialog_behind_start=True)
                except Exception as e:
                    if "没打过" not in str(e):
                        raise
                    self.log_info("扩编实练这一关没打过，停在这里", notify=True)
                    self.wait_ocr(match="扩编实练", box="left", time_out=15)
                    break
                self.wait_ocr(match="扩编实练", box="left", time_out=15, log=True)
                if self.wait_ocr(match="实练奖励", box="top", time_out=3):
                    self.back(after_sleep=2)
        finally:
            self.set_lineup_kind(None)
        self.wait_pop_up(count=1)
        if self.wait_click_ocr(match="当期实练奖励", box="bottom_right", time_out=3, after_sleep=2):
            if result := self.ocr(match="一键领取", frame_processor=self.make_hsv_isolator(hR.WHITE)):
                self.click(result[0], after_sleep=2)
                self.wait_pop_up(count=1)
        self.ensure_main()

    def _deep_stars_full(self):
        """右下角「当期实练奖励 20/40」：星数满了就不用再打。"""
        if result := self.wait_ocr(match=stamina_re, box="bottom_right", time_out=2):
            have, total = (result[0].name.split("/") + [""])[:2]
            self.log_info(f"当期实练奖励 {have}/{total}")
            if have.isdigit() and total.isdigit() and int(have) >= int(total):
                self.log_info("扩编实练星数已满，不用再打")
                return True
        return False

    def _deep_frontier_card(self):
        """最右边一张已解锁的「特殊增强」卡片标题；没有返回 None。"""
        self.next_frame()
        cards = self.ocr(match=re.compile("特殊增强"), box="bottom") or []
        unlocked = []
        for b in cards:
            pad = int(b.width * 0.3)
            region = self.frame[int(b.y) : int(b.y + b.height), max(0, int(b.x) - pad) : int(b.x + b.width) + pad]
            gray = float(cv2.cvtColor(region, cv2.COLOR_BGR2GRAY).mean()) if region.size else 0.0
            self.log_info(f"特殊增强 x={int(b.x)} 标题灰度 {round(gray)}", notify=False)
            if gray > 170:
                unlocked.append(b)
        return max(unlocked, key=lambda b: b.x) if unlocked else None

    def _tab_selected(self, match):
        """右下角标签：选中是蓝绿底（饱和度高），未选中/未解锁是浅灰底；找不到标签按选中处理，走原流程。"""
        self.next_frame()
        boxes = self.ocr(box="bottom_right", match=match)
        if not boxes or self.frame is None:
            return True
        b = boxes[0]
        region = self.frame[int(b.y) : int(b.y + b.height), int(b.x) : int(b.x + b.width)]
        if region.size == 0:
            return True
        sat = float(cv2.cvtColor(region, cv2.COLOR_BGR2HSV)[..., 1].mean())
        self.log_info(f"{b.name} 标签饱和度 {round(sat)}", notify=False)
        return sat > 50
