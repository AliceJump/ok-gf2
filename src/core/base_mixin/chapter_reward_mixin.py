"""
推图 / 往期活动推完一个页签后的收尾：领左下角的章节收集奖励，看心智回溯领抽卡资源。画面说明见 src/core/chapter_reward.py。
"""

import re

from src.core.chapter_reward import (
    MIND_CARD_BOX,
    MIND_LIST_BOX,
    MIND_LIST_DRAG,
    MIND_PLAY_X,
    REWARD_LABEL_BOX,
    REWARD_POPUP_BOX,
    claim_button_re,
    claim_label_re,
    close_hint_re,
    got_items_re,
    mind_replay_percent,
    mind_row_re,
    playable_re,
    popup_title_re,
    story_skip_all_re,
    unfinished_re,
)
from src.core.stage_card import parse_medals

REWARD_TIERS_MAX = 6  # 收集数弹窗最多点几次「领取」（一般三档）
MIND_REPLAY_MAX = 30  # 一次最多看几条心智回溯（一般八条）


class ChapterRewardMixin:
    def claim_chapter_reward(self):
        """
        停在关卡地图上：左下角是「可领取」就点开收集数弹窗，把能领的档位都领掉；还有「未完成」的档位说明
        有关卡没推或没三星通关，通知出来。返回领了几档。
        """
        if not self.config.get("领取章节奖励", True):
            return 0
        self.close_map_panel()
        self.next_frame()
        label = self.ocr(box=self.box_of_screen(*REWARD_LABEL_BOX)) or []
        medals = parse_medals([b.name for b in label])
        claim = [b for b in label if claim_label_re.search(b.name or "")]
        if not claim:
            return 0
        self.click(claim[0], after_sleep=1.5)
        popup = self.box_of_screen(*REWARD_POPUP_BOX)
        if not self.wait_ocr(box=popup, match=popup_title_re, time_out=5, raise_if_not_found=False):
            self.log_info("点了左下角「可领取」，没等到收集数弹窗", notify=False)
            self.debug_shot("chapter_reward_no_popup")
            return 0
        got = 0
        for _ in range(REWARD_TIERS_MAX):
            buttons = self.ocr(box=popup, match=claim_button_re)
            if not buttons:
                break
            self.click(buttons[0], after_sleep=1.5)
            self.close_got_items()
            got += 1
        boxes = self.ocr(box=popup) or []
        unfinished = sum(1 for b in boxes if unfinished_re.search(b.name or ""))
        self.debug_shot("chapter_reward", boxes)
        where = f"「{self.event_name}」" if getattr(self, "event_name", None) else "本章"
        self.log_info(f"{where}领了 {got} 档章节奖励（收集 {medals[0]}/{medals[1]}）" if medals else f"{where}领了 {got} 档章节奖励", notify=True)
        if unfinished:
            self.log_info(
                f"{where}还有 {unfinished} 档章节奖励「未完成」"
                f"{f'（收集 {medals[0]}/{medals[1]}）' if medals else ''}：可能漏了关卡或有关卡没三星通关",
                notify=True,
            )
        if self.ocr(box=popup, match=popup_title_re):
            self.back(after_sleep=1.5)  # 只在弹窗还开着时按 ESC，地图上按 ESC 会退出去
        return got

    def close_got_items(self, time_out=8):
        """关掉「获得道具」：点「点击空白处关闭」，读不到提示就点画面底部空白处。"""
        wait = time_out
        for _ in range(4):
            found = self.wait_ocr(match=[close_hint_re, got_items_re], time_out=wait, raise_if_not_found=False)
            if not found:
                return True
            hints = [b for b in found if close_hint_re.search(b.name)]
            if hints:
                self.click(hints[0], after_sleep=1.5)
            else:
                self.click_relative(0.5, 0.9, after_sleep=1.5)
            wait = 2
        self.log_info("「获得道具」点了几次还没关掉", notify=False)
        return False

    def watch_mind_replay(self):
        """
        活动「剧情」页签左边有「心智回溯」卡片且没到 100%：点开，把「可观看」的一条条播放（进去点「全部跳过」也算看完），
        每条领 30 抽卡资源，看完回地图。返回看了几条。
        """
        if not self.config.get("看心智回溯", True):
            return 0
        self.close_map_panel()
        self.next_frame()
        hit = mind_replay_percent(self.ocr(box=self.box_of_screen(*MIND_CARD_BOX)) or [])
        if hit is None:
            return 0
        card, percent = hit
        if percent is not None and percent >= 100:
            return 0
        self.log_info(f"心智回溯 {percent if percent is not None else '?'}%，点开看剧情领奖励", notify=False)
        self.click(card, after_sleep=2)
        listing = self.box_of_screen(*MIND_LIST_BOX)
        if not self.wait_ocr(box=listing, match=mind_row_re, time_out=8, raise_if_not_found=False):
            self.log_info("点了心智回溯，没看到剧情列表", notify=True)
            self.debug_shot("mind_replay_no_list")
            self.ensure_map()
            return 0
        watched = 0
        for _ in range(MIND_REPLAY_MAX):
            self.next_frame()
            rows = self.ocr(box=listing, match=playable_re)
            if rows:
                row = min(rows, key=lambda b: b.y)
                self.click_relative(MIND_PLAY_X, (row.y + row.height / 2) / self.height, after_sleep=2)
                self.skip_mind_story()
                watched += 1
                continue
            before = [b.name for b in self.ocr(box=listing) or []]
            self.swipe_relative(*MIND_LIST_DRAG, duration=0.6)
            self.sleep(1.5)
            self.next_frame()
            if [b.name for b in self.ocr(box=listing) or []] == before:
                break  # 翻到底了，也没有可观看的
        self.log_info(f"心智回溯看了 {watched} 条", notify=True)
        self.debug_shot("mind_replay_done")
        self.back(after_sleep=2)
        self.ensure_map()
        return watched

    def skip_mind_story(self):
        """心智回溯的一条剧情：点「全部跳过」，再关掉「获得道具」。"""
        if self.wait_click_ocr(box=self.box.top_right, match=story_skip_all_re, time_out=15, after_sleep=2):
            self.close_got_items()
            return
        # 没看到「全部跳过」（加载慢或别的形式）：按普通剧情跳过，等回到列表或弹出获得道具
        self.skip_dialogs(
            end_match=[got_items_re, mind_row_re, re.compile("点击空白处关闭")], time_out=90, raise_if_not_found=False
        )
        self.close_got_items()
