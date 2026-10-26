"""独立记录分类状态，复现根入口与两个礼包页签的无效点击。"""

import unittest
from types import SimpleNamespace

from src.tasks.daily.daily_public_mixin import DailyPublicMixin


class ShopScreen(DailyPublicMixin):
    """模拟独立的根入口、周期礼包与限时礼包页面状态。"""

    def __init__(self, dropped=1, periodic_dropped=0, limited_dropped=0):
        """配置各个入口可以丢失多少次点击。"""
        self.page = "home"
        self.dropped = dropped
        self.category_clicks = 0
        self.free_clicks = 0
        self.periodic_dropped = periodic_dropped
        self.limited_dropped = limited_dropped
        self.periodic_clicks = 0
        self.limited_clicks = 0
        self.free_categories = []
        self.box = SimpleNamespace(bottom_right="right", top_left="left", top="top", bottom="bottom")
        self.config = {}
        self.status = {}
        self.ensure_main_count = 0
        self.width, self.height = 1920, 1080

    def info_set(self, key, value):
        """记录任务状态，供失败路径断言。"""
        self.status[key] = value

    def log_info(self, *args, **kwargs):
        """测试不输出设备日志。"""
        pass

    log_warning = log_info

    def wait_click_ocr(self, *, match, raise_if_not_found=False, **kwargs):
        """识别页签后仍允许点击丢失，不隐式确认页面切换。"""
        labels = match if isinstance(match, list) else [match]
        if "商城" in labels:
            self.page = "recommended"
            return True
        if "品质甄选" in labels:
            self.category_clicks += 1
            if self.category_clicks > self.dropped and self.page == "recommended":
                self.page = "gifts"
            return True
        if any(label in labels for label in ["周期礼包", "常驻礼包"]):
            if self.page not in {"gifts", "periodic", "limited"}:
                return False
            self.periodic_clicks += 1
            if self.periodic_clicks > self.periodic_dropped:
                self.page = "periodic"
            return True
        if any(label in labels for label in ["臻品礼包", "限时礼包"]):
            if self.page not in {"gifts", "periodic", "limited"}:
                return False
            self.limited_clicks += 1
            # 首次仅建立对照分类，第二次才是实际领取阶段。
            if self.limited_clicks == 1 or self.limited_clicks > self.limited_dropped + 1:
                self.page = "limited"
            return True
        if matches(match, "免费"):
            self.free_clicks += 1
            self.free_categories.append(self.page)
        return False

    def box_of_screen(self, *bounds):
        """保留识别范围以验证商品区与页签分离。"""
        return bounds

    def ocr(self, *, box, match=None):
        """返回当前分类商品，并混入不能作为内容证据的价格与计时。"""
        assert box[1] >= 0.2  # 顶部页签不能成为商品内容证据。
        names = {
            "gifts": ["精选组合礼包", "精选成长礼包"],
            "periodic": ["每日补给箱", "每周补给礼包", "每月补给礼包", "已售罄"],
            "limited": ["限时成长礼包", "限时武器礼包"],
        }.get(self.page, [])
        labels = [*names, "剩余1天", "￥6.00"]
        if match is not None:
            labels = [name for name in labels if matches(match, name)]
        return [SimpleNamespace(name=name, x=400, y=450, width=150, height=30) for name in labels]

    def next_frame(self):
        """模型每次 OCR 都读取当前状态，无需设备抓帧。"""
        pass

    def screenshot(self, name):
        """纯页面模型不保存设备截图。"""
        pass

    def wait_until(self, predicate, **kwargs):
        """有限轮询真实谓词，不能把点击当作确认。"""
        for _ in range(3):
            if result := predicate():
                return result
        return None

    def ensure_main(self):
        """模拟安全退出商店。"""
        self.ensure_main_count += 1
        self.page = "home"


def matches(pattern, text):
    if isinstance(pattern, list):
        return any(matches(item, text) for item in pattern)
    return bool(pattern.search(text)) if hasattr(pattern, "search") else pattern in text


class ClaimShopScreen(ShopScreen):
    """领取后自动切付费详情，点击成功与实际到账分别建模。"""

    def __init__(self, purchase_dropped=0, entry_dropped=0, wrong_price=False):
        super().__init__(dropped=0)
        self.modal = None
        self.claimed = False
        self.purchase_dropped = purchase_dropped
        self.entry_dropped = entry_dropped
        self.wrong_price = wrong_price
        self.purchases = 0
        self.paid_purchases = 0
        self.shots = []

    def wait_click_ocr(self, *, match, **kwargs):
        if matches(match, "免费"):
            self.free_clicks += 1
            if self.page != "periodic" or self.claimed:
                return False
            if self.entry_dropped:
                self.entry_dropped -= 1
            else:
                self.modal = "paid" if self.wrong_price else "free"
            return True
        if matches(match, "购买"):
            self.purchases += 1
            if self.modal == "paid":
                self.paid_purchases += 1
            if self.purchase_dropped:
                self.purchase_dropped -= 1
            elif self.modal == "free":
                self.modal = "reward"
                self.claimed = True
            return True
        return super().wait_click_ocr(match=match, **kwargs)

    def ocr(self, *, box=None, match=None):
        if self.modal == "reward":
            labels = ["获得道具", "点击空白处关闭"]
        elif self.modal:
            labels = ["免费" if self.modal == "free" else "$0.99"] if box and box[0] >= 0.7 else ["取消", "购买"]
        else:
            names = super().ocr(box=box or (0.20, 0.20, 0.96, 0.87))
            labels = [item.name for item in names]
            if self.page == "periodic" and not self.claimed:
                labels.append("免费")
        if self.page == "periodic" and not self.claimed:
            labels = [text for text in labels if text != "已售罄"]
        return [
            SimpleNamespace(name=text, x=400, y=450, width=150, height=30)
            for text in labels
            if match is None or matches(match, text)
        ]

    def wait_ocr(self, **kwargs):
        return self.ocr(box=kwargs.get("box"), match=kwargs.get("match"))

    def wait_pop_up(self, **kwargs):
        if self.modal == "reward":
            self.modal = "paid"

    def back(self, **kwargs):
        self.modal = "paid" if self.modal == "reward" else None

    def sleep(self, *args):
        pass

    def screenshot(self, name):
        self.shots.append(name)


class ShoppingTest(unittest.TestCase):
    """验证免费搜索只发生在确认切换后的对应分类。"""

    def test_already_claimed_daily_gift_has_explicit_status(self):
        task = ClaimShopScreen()
        task.claimed = True
        task.shopping()
        self.assertEqual("已领取", task.status["每日礼包"])
        self.assertEqual(0, task.purchases)

    def test_newly_claimed_daily_gift_has_verified_status(self):
        task = ClaimShopScreen()
        task.shopping()
        self.assertEqual("领取已确认", task.status["每日礼包"])

    def test_limited_category_cannot_overwrite_daily_claim_status(self):
        task = ClaimShopScreen()
        task.claimed = True
        task.limited_dropped = 100
        self.assertEqual("待核查", task.shopping())
        self.assertEqual("已领取", task.status["每日礼包"])

    def test_repeated_run_clears_previous_limited_success_on_early_exit(self):
        """本轮未检查限时礼包时不能沿用上轮成功状态。"""
        for failure in ["gift_category", "daily_claim", "limited_category"]:
            with self.subTest(failure=failure):
                task = ClaimShopScreen()
                self.assertIsNone(task.shopping())
                self.assertNotIn("待核查", task.status["限时礼包"])
                if failure == "gift_category":
                    task.dropped = task.category_clicks + 100
                elif failure == "daily_claim":
                    task.claimed = False
                    task.purchase_dropped = 100
                else:
                    task.limited_dropped = task.limited_clicks + 100
                self.assertEqual("待核查", task.shopping())
                self.assertIn("待核查", task.status["限时礼包"])
                if failure == "limited_category":
                    self.assertEqual("已领取", task.status["每日礼包"])
                else:
                    self.assertIn("待核查", task.status["每日礼包"])

    def test_missing_daily_product_does_not_mean_already_claimed(self):
        task = ShopScreen(dropped=0)
        original = task.ocr
        task.ocr = lambda **kwargs: [item for item in original(**kwargs) if item.name != "每日补给箱"]
        self.assertEqual("待核查", task.shopping())
        self.assertIn("待核查", task.status["每日礼包"])

    def test_dropped_free_purchase_retries_until_claimed(self):
        task = ClaimShopScreen(purchase_dropped=1)
        self.assertIsNone(task.shopping())
        self.assertTrue(task.claimed)
        self.assertEqual(2, task.purchases)
        self.assertEqual(0, task.paid_purchases)

    def test_dropped_free_entry_retries_before_purchase(self):
        task = ClaimShopScreen(entry_dropped=1)
        task.shopping()
        self.assertTrue(task.claimed)
        self.assertEqual(1, task.purchases)

    def test_persistent_free_purchase_failure_is_not_success(self):
        task = ClaimShopScreen(purchase_dropped=100)
        self.assertEqual("待核查", task.shopping())
        self.assertFalse(task.claimed)
        self.assertLessEqual(task.purchases, 3)
        self.assertIn("未确认领取", task.status["免费礼包"])

    def test_paid_dialog_never_authorizes_purchase(self):
        task = ClaimShopScreen(wrong_price=True)
        self.assertEqual("待核查", task.shopping())
        self.assertEqual(0, task.purchases)

    def test_paid_detail_with_dropped_back_cannot_confirm_limited_claim(self):
        """付费详情中的稳定中文不能冒充已返回商品列表。"""
        task = ClaimShopScreen(wrong_price=True)
        task.page = "periodic"
        original_ocr = task.ocr

        def read_paid_detail(**kwargs):
            items = original_ocr(**kwargs)
            if task.modal == "paid" and kwargs.get("match") is None:
                items += [SimpleNamespace(name=name) for name in ["特惠成长礼包", "购买可获得丰厚奖励"]]
            return items

        task.ocr = read_paid_detail
        task.back = lambda **kwargs: None
        self.assertFalse(task._claim_shop_free_item(status_key="限时礼包"))
        self.assertEqual(0, task.purchases)
        self.assertEqual("paid", task.modal)
        self.assertIn("待核查", task.status["限时礼包"])

    def test_missing_reward_evidence_cannot_confirm_limited_claim(self):
        """点击后免费入口消失但奖励未被观察到时保留待核查。"""
        task = ClaimShopScreen()
        task.page = "periodic"
        original_click = task.wait_click_ocr

        def purchase_with_unobserved_reward(**kwargs):
            result = original_click(**kwargs)
            if task.modal == "reward":
                task.modal = None
            return result

        task.wait_click_ocr = purchase_with_unobserved_reward
        self.assertFalse(task._claim_shop_free_item(status_key="限时礼包"))
        self.assertEqual(1, task.purchases)
        self.assertIn("待核查", task.status["限时礼包"])

    def test_observed_reward_and_closed_detail_confirm_limited_claim(self):
        """实际奖励和返回列表共同确认领取，不重复购买自动出现的付费项。"""
        task = ClaimShopScreen()
        task.page = "periodic"
        self.assertTrue(task._claim_shop_free_item(status_key="限时礼包"))
        self.assertEqual("领取已确认", task.status["限时礼包"])
        self.assertIsNone(task.modal)
        self.assertEqual(1, task.purchases)
        self.assertEqual(0, task.paid_purchases)

    def test_successful_claim_does_not_retry_automatic_paid_tab(self):
        task = ClaimShopScreen()
        task.shopping()
        self.assertTrue(task.claimed)
        self.assertEqual(1, task.purchases)
        self.assertEqual(0, task.paid_purchases)

    def test_dropped_category_click_is_retried_before_free_item_search(self):
        """根入口点击丢失后可以恢复并按顺序处理两类礼包。"""
        task = ShopScreen(dropped=1)
        self.assertIsNot(task.shopping(), False)
        self.assertEqual(2, task.free_clicks)
        self.assertEqual(["periodic", "limited"], task.free_categories)
        self.assertEqual("home", task.page)

    def test_dropped_periodic_click_is_retried_before_search(self):
        """周期页签丢失一次后先重试再搜索。"""
        task = ShopScreen(dropped=0, periodic_dropped=1)
        self.assertIsNone(task.shopping())
        self.assertEqual(2, task.periodic_clicks)
        self.assertEqual(["periodic", "limited"], task.free_categories)

    def test_periodic_click_always_dropped_returns_uncertain(self):
        """周期分类始终未切换时不搜索免费物品。"""
        task = ShopScreen(dropped=0, periodic_dropped=100)
        self.assertEqual("待核查", task.shopping())
        self.assertEqual([], task.free_categories)
        self.assertLessEqual(task.periodic_clicks, 3)

    def test_limited_click_dropped_never_searches_periodic_twice(self):
        """限时分类未切换时不能在周期分类重复搜索。"""
        task = ShopScreen(dropped=0, limited_dropped=100)
        self.assertEqual("待核查", task.shopping())
        self.assertEqual(["periodic"], task.free_categories)

    def test_blank_product_area_does_not_confirm_switch(self):
        """加载空白不能成为另一个分类的证据。"""
        task = ShopScreen(dropped=0)
        task.ocr = lambda **kwargs: []
        self.assertEqual("待核查", task.shopping())
        self.assertEqual([], task.free_categories)

    def test_unstable_ocr_does_not_confirm_switch(self):
        """两帧不一致时保留待核查。"""
        task = ShopScreen(dropped=0)
        frames = iter([[SimpleNamespace(name="不同商品名称")] if i % 2 else [] for i in range(100)])
        task.ocr = lambda **kwargs: next(frames)
        self.assertEqual("待核查", task.shopping())
        self.assertEqual([], task.free_categories)

    def test_unavailable_gift_category_is_bounded_and_returns_uncertain(self):
        """根入口持续失败时有限退出并恢复主页。"""
        task = ShopScreen(dropped=100)
        self.assertEqual("待核查", task.shopping())
        self.assertEqual(3, task.category_clicks)
        self.assertEqual(0, task.free_clicks)
        self.assertEqual("home", task.page)
