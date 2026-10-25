"""尘烟入口加载、次数漏读和班组失败传递的回归测试。"""

import re
import unittest
from types import SimpleNamespace

from tests.TestChenyanAssist import battle

battle["chenyan"].__globals__["stamina_re"] = re.compile(r"^\d+/\d+")


class ChenyanDevice:
    """将即时截图与加载后的页面分开，复现点击后的瞬时漏读。"""

    def __init__(self, entry=True, tickets=(0,), ready=True, opens_in=None, countdown_misses=0):
        """Initialize independent entry, ticket, and navigation state."""
        self.config = {"尘烟": True}
        self.box = SimpleNamespace(bottom_right="bottom", top_right="top", _group="group")
        self.entry = entry
        self.ready = ready
        self.tickets = iter(tickets)
        self.chosen = []
        self.clicked = []
        self.logs = []
        self.shots = []
        self.infos = {}
        self.home = False
        self.opens_in = opens_in
        self.countdown_misses = countdown_misses
        self.countdown_reads = 0

    def __getattr__(self, name):
        """Bind production methods to the simulated entry device."""
        if name in battle:
            return battle[name].__get__(self, type(self))
        raise AttributeError(name)

    def ocr(self, *args, **kwargs):
        """Simulate an immediate screenshot before the page is ready."""
        match = kwargs.get("match")
        if self.opens_in and isinstance(match, re.Pattern) and match.search(self.opens_in):
            self.countdown_reads += 1
            if self.countdown_reads <= self.countdown_misses:
                return []
            return [SimpleNamespace(name=self.opens_in)]
        return []

    def wait_ocr(self, *args, match=None, **kwargs):
        """Return delayed entry, page, and ticket OCR observations."""
        if match is battle["chenyan"].__globals__["stamina_re"]:
            value = next(self.tickets, None)
            return [] if value is None else [SimpleNamespace(name=f"{value}/3")]
        if match == ["班组"]:
            return [SimpleNamespace(name="班组")]
        if isinstance(match, list) and "每日要务已完成" in match:
            return [SimpleNamespace(name="每日要务已完成")]
        if match == "攻坚战":
            return [SimpleNamespace(name="攻坚战")] if self.ready else []
        if isinstance(match, re.Pattern):
            if match.search("尘烟前线"):
                return [SimpleNamespace(name="尘烟前线")] if self.entry else []
            for _ in range(3):
                if result := self.ocr(match=match):
                    return result
            return []
        return []

    def click(self, target, **kwargs):
        """Record the clicked navigation target."""
        self.clicked.append(target)

    def click_box_by_match_position(self, *args, **kwargs):
        """Ignore fixed navigation coordinates in the simulation."""
        pass

    def wait_click_ocr(self, *args, match=None, **kwargs):
        """Record a successful OCR navigation action."""
        self.clicked.append(match)
        return True

    def choose_chenyan(self, tickets):
        """Record the confirmed ticket count passed to assist selection."""
        self.chosen.append(tickets)
        return True

    def log_info(self, message, **kwargs):
        """Collect runtime messages for result assertions."""
        self.logs.append(message)

    log_warning = log_info
    log_error = log_info

    def info_set(self, key, value):
        """Record the status shown to the user."""
        self.infos[key] = value

    def screenshot(self, name=None, **kwargs):
        """Record diagnostic capture requests without writing images."""
        self.shots.append(name)

    def back(self, **kwargs):
        """Ignore back navigation that does not affect this fixture."""
        pass

    def sleep(self, *args):
        """Avoid real polling delays in unit tests."""
        pass

    def ensure_main(self, **kwargs):
        """Record recovery to the main page."""
        self.home = True

    def _claim_guild_supply(self):
        """Entry tests isolate supply; TestGuildSupply exercises actual claiming."""
        self.wait_click_ocr(match=["补给"])
        return True


class TestChenyanEntry(unittest.TestCase):
    def test_closed_season_is_skipped_without_clicking_entry(self):
        device = ChenyanDevice(ready=False, opens_in="6天22小时后开启")
        self.assertIs(True, device.chenyan())
        self.assertEqual([], device.clicked)
        self.assertEqual([], device.shots)
        self.assertIn("未开放", device.infos["尘烟前线"])

    def test_closed_season_does_not_skip_guild_supply(self):
        device = ChenyanDevice(ready=False, opens_in="6天22小时后开启")
        device.guild()
        self.assertIn(["补给"], device.clicked)
        self.assertTrue(device.home)

    def test_delayed_countdown_still_skips_entry_and_claims_supply(self):
        """An initial OCR miss must not turn a closed season into a guild failure."""
        device = ChenyanDevice(ready=False, opens_in="6天22小时后开启", countdown_misses=1)
        device.guild()
        self.assertEqual(2, device.countdown_reads)
        self.assertFalse(
            any(isinstance(target, list) and target and hasattr(target[0], "name") for target in device.clicked)
        )
        self.assertIn(["补给"], device.clicked)
        self.assertTrue(device.home)

    def test_real_entry_failure_retains_reason_in_runner_summary(self):
        from src.tasks.DailyTaskRunner import DailyTaskRunner

        device = ChenyanDevice(ready=False)
        device.config["班组"] = True
        device.daily_runner = DailyTaskRunner(device, [("班组", device.guild)])
        device.daily_runner.run()
        self.assertIn("点击入口后未确认进入尘烟页面", device.daily_runner.failure_details[""]["班组"])

    def test_delayed_page_still_runs_each_remaining_battle(self):
        """Wait for the entry page and consume each confirmed remaining ticket."""
        device = ChenyanDevice(tickets=(2, 1, 0))
        self.assertIs(device.chenyan(), True)
        self.assertEqual(device.chosen, [2, 1])

    def test_missing_entry_reports_failure_instead_of_success(self):
        """Report a missing entry without attempting a battle."""
        device = ChenyanDevice(entry=False)
        self.assertIs(device.chenyan(), False)
        self.assertTrue(device.shots)
        self.assertEqual(device.chosen, [])

    def test_unread_ticket_count_is_not_zero_tickets(self):
        """Preserve unread ticket counts as failures rather than zero."""
        device = ChenyanDevice(tickets=(None,))
        self.assertIs(device.chenyan(), False)
        self.assertTrue(device.shots)
        self.assertEqual(device.chosen, [])

    def test_ticket_from_wrong_page_must_not_start_battle(self):
        """Require the battle page before accepting a ticket observation."""
        device = ChenyanDevice(tickets=(2,), ready=False)
        self.assertIs(device.chenyan(), False)
        self.assertEqual(device.chosen, [])

    def test_confirmed_zero_is_logged_and_skipped(self):
        """Skip with an explicit reason after confirming zero tickets."""
        device = ChenyanDevice(tickets=(0,))
        self.assertIs(device.chenyan(), True)
        self.assertEqual(device.chosen, [])
        self.assertTrue(any("0" in line and "跳过" in line for line in device.logs))

    def test_guild_propagates_unread_tickets_as_failure(self):
        """Propagate ticket OCR failure and recover to the main page."""
        device = ChenyanDevice(tickets=(None,))
        self.assertIs(device.guild(), False)
        self.assertTrue(device.home)
        self.assertNotIn(["补给"], device.clicked)

    def test_disabled_chenyan_does_not_navigate(self):
        """Treat disabled Chenyan as a successful operation without navigation."""
        device = ChenyanDevice()
        device.config["尘烟"] = False
        self.assertIs(device.chenyan(), True)
        self.assertEqual(device.clicked, [])


if __name__ == "__main__":
    unittest.main()
