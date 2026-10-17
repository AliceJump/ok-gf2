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
        if "免费" in labels:
            self.free_clicks += 1
            self.free_categories.append(self.page)
        return False

    def box_of_screen(self, *bounds):
        """保留识别范围以验证商品区与页签分离。"""
        return bounds

    def ocr(self, *, box):
        """返回当前分类商品，并混入不能作为内容证据的价格与计时。"""
        assert box[1] >= 0.2  # 顶部页签不能成为商品内容证据。
        names = {
            "gifts": ["精选组合礼包", "精选成长礼包"],
            "periodic": ["每日补给礼包", "每周补给礼包"],
            "limited": ["限时成长礼包", "限时武器礼包"],
        }.get(self.page, [])
        return [SimpleNamespace(name=name) for name in [*names, "免费", "剩余1天", "￥6.00"]]

    def next_frame(self):
        """模型每次 OCR 都读取当前状态，无需设备抓帧。"""
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


class ShoppingTest(unittest.TestCase):
    """验证免费搜索只发生在确认切换后的对应分类。"""

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
