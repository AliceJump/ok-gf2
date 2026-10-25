"""班组补给必须核验领取后的列表，不能以点击作为完成证据。"""

import unittest
from types import SimpleNamespace

import numpy as np

from tests.TestChenyanAssist import battle
from tests.TestChenyanEntry import ChenyanDevice


class SupplyDevice(ChenyanDevice):
    _claim_guild_supply = battle["_claim_guild_supply"]

    def __init__(self, bulk_dropped=0, individual_dropped=0, pending=True, readable=True):
        super().__init__(ready=False, opens_in="6天21小时后开启")
        self.pending = pending
        self.readable = readable
        self.bulk_dropped = bulk_dropped
        self.individual_dropped = individual_dropped
        self.bulk_clicks = 0
        self.individual_clicks = 0
        self.reward = False

    def _guild_supply_status(self):
        if not self.readable:
            return None
        return {"pending": self.pending, "individual": ["领取"] if self.pending else [], "bulk": ["领取全部"]}

    def click_box(self, target, **kwargs):
        if target == ["领取全部"]:
            self.bulk_clicks += 1
            dropped = self.bulk_clicks <= self.bulk_dropped
        else:
            self.individual_clicks += 1
            dropped = self.individual_clicks <= self.individual_dropped
        if not dropped:
            self.pending = False
            self.reward = True

    def wait_ocr(self, *args, match=None, **kwargs):
        if match == ["获得道具", "点击空白处关闭"]:
            return ["获得道具"] if self.reward else []
        return super().wait_ocr(*args, match=match, **kwargs)

    def wait_until(self, predicate, **kwargs):
        for _ in range(3):
            if result := predicate():
                return result
        return None

    def next_frame(self):
        pass

    def back(self, **kwargs):
        self.reward = False


class TestGuildSupply(unittest.TestCase):
    def test_claim_failure_keeps_specific_runner_reason(self):
        from src.tasks.DailyTaskRunner import DailyTaskRunner

        task = SupplyDevice(bulk_dropped=100, individual_dropped=100)
        task.config["班组"] = True
        task.daily_runner = DailyTaskRunner(task, [("班组", task.guild)])
        task.daily_runner.run()
        self.assertIn("班组补给待核查", task.daily_runner.failure_details[""]["班组"])

    def test_visual_status_distinguishes_claimed_and_unread_claim_button(self):
        for width, height in [(1280, 720), (1920, 1080), (3840, 2160)]:
            for pending in [False, True]:
                with self.subTest(resolution=(width, height), pending=pending):
                    frame = np.zeros((height, width, 3), dtype=np.uint8)
                    frame[int(height * 0.30) : int(height * 0.40), int(width * 0.86) : int(width * 0.95)] = (
                        110,
                        165,
                        100,
                    )
                    if pending:
                        frame[int(height * 0.89) : int(height * 0.94), int(width * 0.79) : int(width * 0.95)] = (
                            40,
                            180,
                            245,
                        )

                    def ocr(*, match, pending=pending, **kwargs):
                        if match == ["分配中", "已分配"]:
                            return ["分配中"]
                        return ["领取全部"] if pending and match == "领取全部" else []

                    task = SimpleNamespace(
                        frame=frame,
                        ocr=ocr,
                        box_of_screen=lambda *bounds: bounds,
                        box=SimpleNamespace(top_right="top", bottom_right="bottom"),
                    )
                    status = battle["_guild_supply_status"](task)
                    self.assertIsNotNone(status)
                    self.assertEqual(pending, status["pending"])

    def test_dropped_bulk_claim_falls_back_to_individual(self):
        task = SupplyDevice(bulk_dropped=100)
        self.assertIsNot(task.guild(), False)
        self.assertFalse(task.pending)
        self.assertGreater(task.individual_clicks, 0)
        self.assertIn("已确认", task.infos["班组补给"])

    def test_persistent_claim_failure_is_reported(self):
        task = SupplyDevice(bulk_dropped=100, individual_dropped=100)
        self.assertIs(task.guild(), False)
        self.assertTrue(task.pending)
        self.assertIn("待核查", task.infos["班组补给"])
        self.assertLessEqual(task.bulk_clicks + task.individual_clicks, 5)

    def test_already_claimed_does_not_click(self):
        task = SupplyDevice(pending=False)
        task.guild()
        self.assertEqual(0, task.bulk_clicks + task.individual_clicks)
        self.assertIn("已领取", task.infos["班组补给"])

    def test_unreadable_page_is_not_claimed(self):
        task = SupplyDevice(readable=False)
        self.assertIs(task.guild(), False)
        self.assertEqual(0, task.bulk_clicks + task.individual_clicks)
