import unittest
from types import SimpleNamespace

from src.tasks.daily.daily_public_mixin import DailyPublicMixin


class ShopScreen(DailyPublicMixin):
    def __init__(self, dropped=1):
        self.page = "home"
        self.dropped = dropped
        self.category_clicks = 0
        self.free_clicks = 0
        self.box = SimpleNamespace(bottom_right="right", top_left="left", top="top", bottom="bottom")
        self.config = {}
        self.status = {}
        self.ensure_main_count = 0

    def info_set(self, key, value):
        self.status[key] = value

    def log_info(self, *args, **kwargs):
        pass

    log_warning = log_info

    def wait_click_ocr(self, *, match, raise_if_not_found=False, **kwargs):
        labels = match if isinstance(match, list) else [match]
        if "商城" in labels:
            self.page = "recommended"
            return True
        if "品质甄选" in labels:
            self.category_clicks += 1
            if self.category_clicks > self.dropped:
                self.page = "gifts"
            return True
        if any(label in labels for label in ["周期礼包", "常驻礼包", "臻品礼包", "限时礼包"]):
            if self.page == "gifts":
                return True
            if raise_if_not_found:
                raise RuntimeError("gift tab missing")
            return False
        if "免费" in labels:
            self.free_clicks += 1
        return False

    def ensure_main(self):
        self.ensure_main_count += 1
        self.page = "home"


class ShoppingTest(unittest.TestCase):
    def test_dropped_category_click_is_retried_before_free_item_search(self):
        task = ShopScreen(dropped=1)
        self.assertIsNot(task.shopping(), False)
        self.assertEqual(2, task.category_clicks)
        self.assertEqual(2, task.free_clicks)
        self.assertEqual("home", task.page)

    def test_unavailable_gift_category_is_bounded_and_returns_uncertain(self):
        task = ShopScreen(dropped=100)
        self.assertEqual("待核查", task.shopping())
        self.assertEqual(3, task.category_clicks)
        self.assertEqual(0, task.free_clicks)
        self.assertEqual("home", task.page)
