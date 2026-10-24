"""公共区/调度室与商店：委托派遣、游戏内自主循环、免费礼包与心愿单购买。"""

import re
import time

import cv2

# 主页左下角一排小图标（设置 / 链接 / 消息 / 自主循环），「自主循环」是第 4 个，指挥官 50 级解锁，没解锁时那里是空的。
# 实录 2026-10-23（2560x1440）：四个图标中心 x≈0.060/0.113/0.163/0.213，y≈0.896；
# 图标框里白色像素占比 0.07~0.11，图标右边的空地是 0。
AUTO_LOOP_ICON_XY = (0.2125, 0.896)
AUTO_LOOP_ICON_BOX = (0.195, 0.865, 0.23, 0.93)
AUTO_LOOP_ICON_MIN_WHITE = 0.03
AUTO_LOOP_TIMEOUT = 30 * 60  # 循环队列里有体力本、竞技场等多项，给足时间
auto_loop_end_re = re.compile("循环结束")
# 循环途中的弹窗只点这些安全的确认；涉及花钱/坍塌晶条/更换已生效菜品的一律不点
auto_loop_unsafe_re = re.compile("晶条|购买|充值|更换")


def white_ratio(frame, box):
    """box 里白色（亮、低饱和）像素的占比，用来判断主页左下角那个图标在不在。"""
    region = frame[box.y : box.y + box.height, box.x : box.x + box.width]
    if region.size == 0:
        return 0.0
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    return float(((hsv[..., 2] > 200) & (hsv[..., 1] < 60)).mean())


class DailyPublicMixin:
    def gongongqu(self):
        self.info_set("current_task", "gongongqu")
        self._auto_loop_done = False
        if self.config.get("自主循环"):
            if self.auto_loop():
                self._auto_loop_done = True
                return
            # 没解锁 / 没跑完：照手动流程派遣，之后的体力本和竞技场也照常手动打
            self.ensure_main()
        if result := self.wait_ocr(match=re.compile("委托"), box=self.box._claim, raise_if_not_found=True, log=True):
            self.click_box_by_match_position(result, "委托", after_sleep=2)
            start_time = time.time()
            while True:
                if time.time() - start_time > 10:
                    self.log_info("公共区委托界面停留过久，返回")
                    break
                # 实录 2026-10-22：循环里不取新帧，10 秒都在看点「委托」之前的主页旧帧，调度室按钮永远找不到，
                # 资源没领、也没再次派遣，日志里却记成功
                self.next_frame()
                buttons = self.find_feature(feature_name="ggq_can_button", box=self.box.left)
                if buttons and len(buttons) >= 2:
                    break
            if buttons:
                self.click(buttons[0])
            if self.wait_ocr(match=["最小"], time_out=4, settle_time=2, log=True):
                self.wait_click_ocr(match=["确认"], after_sleep=2.5, raise_if_not_found=True)
            self.back(after_sleep=2)

            if buttons and len(buttons) >= 2:
                self.click(buttons[1], after_sleep=2)
            if self.wait_ocr(match="获得道具", box=self.box.top, time_out=2, log=True):
                self.back(after_sleep=2)
            else:
                self.wait_pop_up(count=1)
            if buttons and len(buttons) > 2:
                self.click(buttons[2], after_sleep=2)
                self.wait_click_ocr(
                    match=[re.compile("再次派[遣造]")], box=self.box.bottom, after_sleep=2, raise_if_not_found=False
                )

    def has_auto_loop_icon(self):
        """主页左下角第 4 个图标（自主循环）在不在。"""
        self.next_frame()
        ratio = white_ratio(self.frame, self.box_of_screen(*AUTO_LOOP_ICON_BOX))
        self.log_info(f"主页左下角自主循环图标白色占比 {ratio:.3f}")
        return ratio >= AUTO_LOOP_ICON_MIN_WHITE

    def auto_loop(self):
        """
        游戏内「自主循环」（指挥官 50 级解锁）：主页左下角图标 → 循环页「开始循环」→ 等「循环结束」→ 确认。
        循环队列在游戏里自己配（调度室、体力本、竞技场等），吃完饭再跑。
        返回 True = 循环跑完；False = 没解锁或没跑完，调用方退回手动流程。
        """
        self.info_set("current_task", "自主循环")
        if not self.has_auto_loop_icon():
            self.log_info("主页左下角没有自主循环图标（50 级解锁），按手动流程跑日常", notify=True)
            return False
        self.click_relative(*AUTO_LOOP_ICON_XY, after_sleep=2)
        start = self.wait_ocr(match="开始循环", box=self.box.bottom_left, time_out=8, raise_if_not_found=False)
        if not start:
            self.log_info("点了左下角图标但没看到「开始循环」，按手动流程跑日常", notify=True)
            self.screenshot("auto_loop_no_page")
            return False
        self.debug_shot("auto_loop_page")
        self.click(start, after_sleep=2)
        deadline = time.time() + AUTO_LOOP_TIMEOUT
        started = time.time()
        last_log = 0
        while time.time() < deadline:
            self.next_frame()
            if end := self.ocr(match=auto_loop_end_re, log=True):
                self.debug_shot("auto_loop_end", end)
                self.log_info(f"自主循环结束，用时 {int(time.time() - started)} 秒", notify=True)
                self.sleep(2)
                self.wait_click_ocr(
                    match=["确认"], box=self.box.bottom, time_out=5, after_sleep=2, raise_if_not_found=False
                )
                self.ensure_main()
                return True
            if confirm := self.ocr(match=["确认"], box=self.box.center):
                texts = "".join(b.name for b in self.ocr(box=self.box.center) or [])
                if auto_loop_unsafe_re.search(texts):
                    self.log_info(f"自主循环弹窗涉及消耗资源，不点确认，停止：{texts}", notify=True)
                    self.screenshot("auto_loop_unsafe")
                    self.wait_click_ocr(match=["取消"], box=self.box.center, time_out=2, raise_if_not_found=False)
                    return False
                self.log_info(f"自主循环弹窗点确认：{texts}")
                self.debug_shot("auto_loop_confirm", confirm)
                self.click(confirm, after_sleep=2)
                continue
            if time.time() - last_log > 60:
                # 循环途中画面一直在变但脚本不点东西，定时记一笔，免得看门狗当成卡死
                last_log = time.time()
                self.log_info(f"自主循环进行中（{int(time.time() - started)} 秒）")
                self.debug_shot("auto_loop_running")
            self.sleep(3)
        self.log_info(f"自主循环 {AUTO_LOOP_TIMEOUT // 60} 分钟还没结束，退回手动流程", notify=True)
        self.screenshot("auto_loop_timeout")
        return False

    def _shop_category_content(self):
        """用连续两帧稳定的商品文字确认内容，排除页签、价格和倒计时。"""
        box = self.box_of_screen(0.20, 0.20, 0.96, 0.87)

        def read_names():
            return frozenset(
                item.name for item in self.ocr(box=box) if re.fullmatch(r"[\u4e00-\u9fff·]{4,}", item.name)
            )

        first = read_names()
        if len(first) < 2:
            return None
        self.next_frame()
        return first if first == read_names() else None

    def _switch_shop_category(self, labels, previous):
        """只有商品名称稳定且发生替换才确认切换，点击结果不作页面证据。"""
        if not previous or not self.wait_click_ocr(
            match=labels, box=self.box.top, after_sleep=0.5, time_out=2, raise_if_not_found=False
        ):
            return False

        def changed():
            current = self._shop_category_content()
            return current and bool(current - previous) and bool(previous - current)

        return bool(self.wait_until(changed, time_out=2, settle_time=0))

    def shopping(self):
        """确认礼包商品区切换后领取免费物品；缺少证据则保留待核查结果。"""
        self.info_set("current_task", "shopping")
        self.wait_click_ocr(match=["商城"], box=self.box.bottom_right, after_sleep=1.5, raise_if_not_found=True)
        for _ in range(3):
            self.wait_click_ocr(
                match=["品质甄选"], box=self.box.top_left, after_sleep=1, time_out=2, raise_if_not_found=False
            )
            # 先建立另一分类的内容对照，兼容默认已选中周期礼包的情况。
            # 此次点击可以失败；后续仍必须观测到目标点击带来的稳定内容替换。
            self.wait_click_ocr(
                match=["臻品礼包", "限时礼包"],
                box=self.box.top,
                after_sleep=0.5,
                time_out=2,
                raise_if_not_found=False,
            )
            previous = self.wait_until(self._shop_category_content, time_out=2, settle_time=0)
            if self._switch_shop_category(["周期礼包", "常驻礼包"], previous):
                break
        else:
            self.info_set("免费礼包", "待核查：未确认礼包页面")
            self.log_warning("未确认礼包商品内容切换，跳过免费礼包并继续后续任务")
            self.ensure_main()
            return "待核查"
        if self.wait_click_ocr(match=["免费"], after_sleep=0.5, raise_if_not_found=False, time_out=1):
            self.log_info("found free item to buy")
            self.wait_click_ocr(match=["确认", "购买"], box=self.box.bottom, after_sleep=1.5, raise_if_not_found=True)
            self.wait_pop_up(time_out=5, count=1)
            self.back()
            self.sleep(1)
        previous = self.wait_until(self._shop_category_content, time_out=2, settle_time=0)
        if not self._switch_shop_category(["臻品礼包", "限时礼包"], previous):
            self.info_set("免费礼包", "待核查：未确认限时礼包页面")
            self.ensure_main()
            return "待核查"
        if self.wait_click_ocr(match=["免费"], after_sleep=0.5, raise_if_not_found=False, time_out=1):
            self.log_info("found free item to buy")
            if self.wait_click_ocr(
                match=["确认", "购买"], box=self.box.bottom, after_sleep=1.5, raise_if_not_found=True
            ):
                self.back()
                self.sleep(1)
        if self.config.get("商店心愿单购买"):
            self.buy_others()
        self.ensure_main()

    def buy_others(self):
        self.info_set("current_task", "心愿单购买")
        self.click(0.055, 0.946, after_sleep=1)
        others_list = ["家具商店", "班组商店", "调度商店", "讯段交易", "心智统合", "人形堆栈"]
        for other in others_list:
            if not self.wait_click_ocr(match=other, after_sleep=1, raise_if_not_found=False):
                continue  # 找不到商店就跳过
            if not self.wait_click_ocr(
                match=re.compile("购买"), box=self.box.bottom_right, time_out=1, raise_if_not_found=False
            ):
                continue  # 找不到一键购买按钮就跳过
            if self.wait_click_ocr(match="购买", after_sleep=1, raise_if_not_found=False):
                self.wait_pop_up(time_out=5, count=1)
