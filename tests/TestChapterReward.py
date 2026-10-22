"""
实录 2026-10-22：主线章节、往期活动每个页签推完后，左下角「可领取」的收集数奖励要领；
活动「剧情」页签左边的「心智回溯」要一条条看完领抽卡资源；第 11 期起的活动都 100% 了，奖励还没领，
靠列表卡片右上角的橙色「!」找出来。
"""

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import cv2

from ok import Box
from src.core import chapter_reward as cr
from src.core.base_mixin.chapter_reward_mixin import ChapterRewardMixin

FIX = Path(__file__).resolve().parents[1] / "tests/fixtures"
W, H = 1280, 720


def name_box(cx, cy, name):
    return Box(int(cx - 50), int(cy - 12), 100, 24, name=name)


class EventBadgeTest(unittest.TestCase):
    def test_badged_cards_found(self):
        frame = cv2.imread(str(FIX / "event_list_badges_1280x720.jpg"))
        badges = cr.event_badges(frame, W, H)
        self.assertEqual(4, len(badges), badges)
        for cx, name in [(593, "虚境新始"), (865, "瑞骋迎春至"), (1137, "月下安魂曲")]:
            self.assertTrue(cr.card_has_badge(name_box(cx, 555, name), badges, W), name)

    def test_orange_card_art_is_not_a_badge(self):
        """烟火迎春归的卡面是橙红色，不能当成「!」。"""
        frame = cv2.imread(str(FIX / "event_list_no_badge_1280x720.jpg"))
        self.assertEqual([], cr.event_badges(frame, W, H))

    def test_badge_belongs_to_its_own_card(self):
        badges = [0.977 * W]
        self.assertTrue(cr.card_has_badge(name_box(1137, 555, "月下安魂曲"), badges, W))
        self.assertFalse(cr.card_has_badge(name_box(865, 555, "瑞骋迎春至"), badges, W))


class MindReplayPercentTest(unittest.TestCase):
    def test_reads_card_and_percent(self):
        boxes = [Box(40, 740, 80, 20, name="心智回溯"), Box(40, 780, 40, 20, name="13%")]
        card, percent = cr.mind_replay_percent(boxes)
        self.assertEqual("心智回溯", card.name)
        self.assertEqual(13, percent)

    def test_no_card(self):
        self.assertIsNone(cr.mind_replay_percent([Box(40, 780, 40, 20, name="0%")]))


def fake_task():
    """公共 Mock：画面状态由各测试自己的 ocr / click 模拟。"""
    task = Mock()
    task.config = {}
    task.width, task.height = W, H
    task.event_name = None
    task.box_of_screen.side_effect = lambda *b: b
    task.box = SimpleNamespace(top_right="top_right")
    return task


class ClaimChapterRewardTest(unittest.TestCase):
    def run_claim(self, label, tiers):
        """label: 左下角文字；tiers: 弹窗里每档的状态（"领取" / "done" / "未完成"）。"""
        task = fake_task()
        state = {"popup": False, "tiers": list(tiers)}

        def ocr(box=None, match=None, **kw):
            if box == cr.REWARD_LABEL_BOX:
                return [Box(10, 1300, 80, 24, name=t) for t in label]
            if box == cr.REWARD_POPUP_BOX and state["popup"]:
                names = ["收集数"] + [t for t in state["tiers"] if t != "done"]
                boxes = [Box(900, 200 + i * 200, 80, 30, name=n) for i, n in enumerate(names)]
                return [b for b in boxes if match is None or match.search(b.name)]
            return []

        def click(target, **kw):
            if getattr(target, "name", "") == "可领取":
                state["popup"] = True
            elif getattr(target, "name", "") == "领取":
                state["tiers"][state["tiers"].index("领取")] = "done"

        task.ocr.side_effect = ocr
        task.click.side_effect = click
        task.wait_ocr.side_effect = lambda box=None, match=None, **kw: ocr(box=box, match=match)
        task.back.side_effect = lambda **kw: state.update(popup=False)
        got = ChapterRewardMixin.claim_chapter_reward(task)
        return task, got, state

    def test_claims_every_available_tier_and_closes_popup(self):
        task, got, state = self.run_claim(["51/51", "可领取"], ["领取", "领取", "领取"])
        self.assertEqual(3, got)
        self.assertEqual(3, task.close_got_items.call_count)
        self.assertFalse(state["popup"])
        self.assertFalse(any("未完成" in str(c) for c in task.log_info.call_args_list))

    def test_unfinished_tier_is_reported(self):
        task, got, _ = self.run_claim(["36/48", "可领取"], ["领取", "领取", "未完成"])
        self.assertEqual(2, got)
        warn = [c for c in task.log_info.call_args_list if "未完成" in c.args[0]]
        self.assertEqual(1, len(warn))
        self.assertIn("36/48", warn[0].args[0])

    def test_nothing_to_claim_does_not_click_or_press_esc(self):
        task, got, _ = self.run_claim(["章节奖励已全部领取"], [])
        self.assertEqual(0, got)
        task.click.assert_not_called()
        task.back.assert_not_called()

    def test_disabled_by_config(self):
        task = fake_task()
        task.config = {"领取章节奖励": False}
        self.assertEqual(0, ChapterRewardMixin.claim_chapter_reward(task))
        task.ocr.assert_not_called()


class WatchMindReplayTest(unittest.TestCase):
    def test_plays_each_available_story_then_returns(self):
        task = fake_task()
        rows = ["已归档", "可观看", "观看前置剧情以解锁", "观看前置剧情以解锁"]
        state = {"open": False}

        def ocr(box=None, match=None, **kw):
            if box == cr.MIND_CARD_BOX:
                return [Box(40, 740, 80, 20, name="心智回溯"), Box(40, 780, 40, 20, name="13%")]
            if box == cr.MIND_LIST_BOX and state["open"]:
                boxes = [Box(1000, 180 + i * 240, 120, 30, name=n) for i, n in enumerate(rows)]
                return [b for b in boxes if match is None or match.search(b.name)]
            return []

        def click(target, **kw):
            state["open"] = True

        def play(x, y, **kw):
            i = rows.index("可观看")
            self.assertAlmostEqual((180 + i * 240 + 15) / H, y)
            rows[i] = "已归档"
            if i + 1 < len(rows):
                rows[i + 1] = "可观看"

        task.ocr.side_effect = ocr
        task.click.side_effect = click
        task.click_relative.side_effect = play
        task.wait_ocr.side_effect = lambda box=None, match=None, **kw: ocr(box=box, match=match)
        self.assertEqual(3, ChapterRewardMixin.watch_mind_replay(task))
        self.assertEqual(["已归档"] * 4, rows)
        self.assertEqual(3, task.skip_mind_story.call_count)
        task.back.assert_called_once()

    def test_full_replay_is_not_opened(self):
        task = fake_task()
        task.ocr.return_value = [Box(40, 740, 80, 20, name="心智回溯"), Box(40, 780, 40, 20, name="100%")]
        self.assertEqual(0, ChapterRewardMixin.watch_mind_replay(task))
        task.click.assert_not_called()

    def test_no_card_on_map(self):
        task = fake_task()
        task.ocr.return_value = []
        self.assertEqual(0, ChapterRewardMixin.watch_mind_replay(task))
        task.click.assert_not_called()


if __name__ == "__main__":
    unittest.main()
