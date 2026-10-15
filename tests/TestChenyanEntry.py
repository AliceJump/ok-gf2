"""尘烟入口加载、次数漏读和班组失败传递的回归测试。"""

import re
import unittest
from types import SimpleNamespace

from tests.TestChenyanAssist import battle


battle["chenyan"].__globals__["stamina_re"] = re.compile(r"^\d+/\d+")


class ChenyanDevice:
    """将即时截图与加载后的页面分开，复现点击后的瞬时漏读。"""

    def __init__(self, entry=True, tickets=(0,), ready=True):
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

    def __getattr__(self, name):
        if name in battle:
            return battle[name].__get__(self, type(self))
        raise AttributeError(name)

    def ocr(self, *args, **kwargs):
        return []

    def wait_ocr(self, *args, match=None, **kwargs):
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
            return [SimpleNamespace(name="尘烟前线")] if self.entry else []
        return []

    def click(self, target, **kwargs):
        self.clicked.append(target)

    def click_box_by_match_position(self, *args, **kwargs):
        pass

    def wait_click_ocr(self, *args, match=None, **kwargs):
        self.clicked.append(match)
        return True

    def choose_chenyan(self, tickets):
        self.chosen.append(tickets)
        return True

    def log_info(self, message, **kwargs):
        self.logs.append(message)

    log_warning = log_info
    log_error = log_info

    def info_set(self, key, value):
        self.infos[key] = value

    def screenshot(self, name=None, **kwargs):
        self.shots.append(name)

    def back(self, **kwargs):
        pass

    def sleep(self, *args):
        pass

    def ensure_main(self, **kwargs):
        self.home = True


class TestChenyanEntry(unittest.TestCase):
    def test_delayed_page_still_runs_each_remaining_battle(self):
        device = ChenyanDevice(tickets=(2, 1, 0))
        self.assertIs(device.chenyan(), True)
        self.assertEqual(device.chosen, [2, 1])

    def test_missing_entry_reports_failure_instead_of_success(self):
        device = ChenyanDevice(entry=False)
        self.assertIs(device.chenyan(), False)
        self.assertTrue(device.shots)
        self.assertEqual(device.chosen, [])

    def test_unread_ticket_count_is_not_zero_tickets(self):
        device = ChenyanDevice(tickets=(None,))
        self.assertIs(device.chenyan(), False)
        self.assertTrue(device.shots)
        self.assertEqual(device.chosen, [])

    def test_ticket_from_wrong_page_must_not_start_battle(self):
        device = ChenyanDevice(tickets=(2,), ready=False)
        self.assertIs(device.chenyan(), False)
        self.assertEqual(device.chosen, [])

    def test_confirmed_zero_is_logged_and_skipped(self):
        device = ChenyanDevice(tickets=(0,))
        self.assertIs(device.chenyan(), True)
        self.assertEqual(device.chosen, [])
        self.assertTrue(any("0" in line and "跳过" in line for line in device.logs))

    def test_guild_propagates_unread_tickets_as_failure(self):
        device = ChenyanDevice(tickets=(None,))
        self.assertIs(device.guild(), False)
        self.assertTrue(device.home)
        self.assertNotIn(["补给"], device.clicked)

    def test_disabled_chenyan_does_not_navigate(self):
        device = ChenyanDevice()
        device.config["尘烟"] = False
        self.assertIsNone(device.chenyan())
        self.assertEqual(device.clicked, [])


if __name__ == "__main__":
    unittest.main()
