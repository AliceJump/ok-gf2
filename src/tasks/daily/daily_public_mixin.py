"""公共区/调度室与商店：委托派遣、游戏内自主循环、免费礼包与心愿单购买。"""

import re
import time


class DailyPublicMixin:
    def gongongqu(self):
        self.info_set("current_task", "gongongqu")
        if result := self.wait_ocr(match=re.compile("委托"), box=self.box._claim, raise_if_not_found=True, log=True):
            self.click_box_by_match_position(result, "委托", after_sleep=2)
            start_time = time.time()
            while True:
                if time.time() - start_time > 10:
                    self.log_info("公共区委托界面停留过久，返回")
                    break
                buttons = self.find_feature(feature_name="ggq_can_button", box=self.box.left)
                if buttons and len(buttons) >= 2:
                    break
            if not self.config.get("自主循环"):
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
            if self.config.get("自主循环"):
                self.auto_loop()

    def _auto_loop_step_with_retry(
        self, step_num, match, need_confirm=False, box=None, time_out=5, after_sleep=2, **kwargs
    ):
        """
        点击OCR匹配元素，等待点击特征在 3s 内消失。
        若特征未消失则重试，最多尝试 3 次。
        Args:
            step_num (int): 步骤编号
            match (str or list): OCR匹配内容
            box (Box): OCR匹配范围
            time_out (int): OCR匹配超时时间
            after_sleep (int): 点击后等待时间
            **kwargs: 其他参数，传递给 wait_click_ocr
        Returns:
            bool: 是否成功点击
        """
        for attempt in range(3):
            result = self.wait_click_ocr(match=match, box=box, time_out=time_out, after_sleep=0, log=True, **kwargs)
            if not result:
                self.log_info(f"自主循环步骤{step_num}未完成，退出循环", notify=True)
                return False
            # 等待最多 3s，检测点击特征是否消失
            start = time.time()
            while time.time() - start < 3:
                self.next_frame()
                if not self.ocr(box=box, match=match):
                    self.sleep(after_sleep)
                    return result
                if need_confirm and self.ocr(box=self.box.center, match="确认"):
                    return result

                self.sleep(0.3)
            if attempt < 2:
                self.log_info(f"自主循环步骤{step_num}点击后特征未消失，重试 ({attempt + 2}/3)", notify=True)
        self.log_info(f"自主循环步骤{step_num}未完成，退出循环", notify=True)
        return False

    def auto_loop(self):
        # 步骤 1: 点击"自主循环"，带重试
        if not self._auto_loop_step_with_retry(
            step_num=1,
            match=[re.compile("自主循环")],
            box=self.box.bottom_left,
            time_out=5,
            after_sleep=2,
        ):
            return

        # 步骤 2: 点击"开始循环"，带重试
        if not self._auto_loop_step_with_retry(
            step_num=2,
            match="开始循环",
            box=self.box.bottom_left,
            need_confirm=True,
            time_out=5,
            after_sleep=2,
        ):
            return

        # 步骤 3: 点击"确认"，带重试
        self._auto_loop_step_with_retry(
            step_num=3,
            match=["确认"],
            box=self.box.center,
            settle_time=2,
            after_sleep=2,
        )
        # 步骤 4: 等待"循环结束"出现并点击（仅作为一次识别完成的角色，不需要重试）
        if not self.wait_click_ocr(
            match=re.compile("循环结束"), time_out=600, box=self.box.top, after_sleep=2, log=True
        ):
            self.log_info("自主循环步骤4未完成，退出循环", notify=True)
            return

        # 步骤 5: 点击"确认"，带重试
        if not self._auto_loop_step_with_retry(
            step_num=5, match=["确认"], settle_time=2, after_sleep=2, box=self.box.bottom
        ):
            return

    def _shop_category_content(self):
        """用连续两帧稳定商品文字确认列表，排除详情、奖励及加载画面。"""
        box = self.box_of_screen(0.20, 0.20, 0.96, 0.87)

        def read_names():
            items = self.ocr(box=box)
            if any(item.name.strip() in {"取消", "获得道具", "点击空白处关闭"} for item in items):
                return frozenset()
            return frozenset(item.name for item in items if re.fullmatch(r"[\u4e00-\u9fff·]{4,}", item.name))

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

    def _daily_shop_gift_claimed(self):
        """核对每日补给箱自身下方的售罄标记，不借用其他付费商品状态。"""
        names = self.ocr(match=re.compile(r"^每日补给箱$"), box=self.box_of_screen(0.20, 0.20, 0.96, 0.87))
        for name in names:
            center = (name.x + name.width / 2) / self.width
            bottom = (name.y + name.height) / self.height
            price = self.box_of_screen(
                max(0.20, center - 0.07), bottom, min(0.96, center + 0.07), min(0.95, bottom + 0.08)
            )
            if self.ocr(match=re.compile(r"已售罄|已领取|日限购\s*0"), box=price):
                return True
        return False

    def _claim_shop_free_item(self, status_key="免费礼包", daily=False):
        """只购买免费项；以奖励或每日售罄标记及返回列表共同确认领取。"""
        content_box = self.box_of_screen(0.20, 0.20, 0.96, 0.87)
        price_box = self.box_of_screen(0.70, 0.23, 0.83, 0.32)
        cancel_box = self.box_of_screen(0.28, 0.73, 0.48, 0.81)
        purchase_box = self.box_of_screen(0.52, 0.73, 0.72, 0.81)
        free_match = re.compile(r"^\s*免费\s*$")
        entry_attempted = False
        reward_seen = False
        for attempt in range(3):
            if not self.wait_click_ocr(
                match=free_match, box=content_box, time_out=3, after_sleep=0.5, raise_if_not_found=False
            ):
                # 页面稳定且没有可领取入口时才允许结束，空白/加载页不能算完成。
                if (
                    self._shop_category_content()
                    and not self.ocr(match=free_match, box=content_box)
                    and (not daily or self._daily_shop_gift_claimed())
                    and (not entry_attempted or daily or reward_seen)
                ):
                    status = "领取已确认" if entry_attempted else "已领取" if daily else "无可领取免费礼包"
                    self.info_set(status_key, status)
                    return True
                continue
            entry_attempted = True
            free_detail = bool(
                self.wait_ocr(match=free_match, box=price_box, time_out=2, raise_if_not_found=False)
                and self.ocr(match="取消", box=cancel_box)
            )
            # 领取后游戏会自动切到付费礼包详情，每次尝试都必须重查价格。
            if (
                free_detail
                and self.wait_click_ocr(
                    match=re.compile(r"^\s*(?:确认|购买)\s*$"),
                    box=purchase_box,
                    time_out=2,
                    after_sleep=0.5,
                    raise_if_not_found=False,
                )
                and self.wait_ocr(match=["获得道具", "点击空白处关闭"], time_out=3, raise_if_not_found=False)
            ):
                reward_seen = True
                self.back(after_sleep=0.5)
            if self.ocr(match="取消", box=cancel_box):
                self.back(after_sleep=0.5)
            if self.wait_until(
                lambda reward_seen=reward_seen: (
                    self._shop_category_content()
                    and not self.ocr(match=free_match, box=content_box)
                    and (self._daily_shop_gift_claimed() if daily else reward_seen)
                ),
                time_out=3,
                settle_time=0.3,
            ):
                self.log_info("免费礼包领取已确认")
                self.info_set(status_key, "领取已确认")
                return True
            self.log_warning(f"免费礼包未确认领取，重试 {attempt + 1}/3")
        self.info_set("免费礼包", "待核查：未确认领取")
        self.info_set(status_key, "待核查：未确认领取或已领取标记")
        runner = getattr(self, "daily_runner", None)
        if runner is not None:
            runner.set_task_failure("免费礼包点击后未确认领取")
        self.screenshot("shop_free_claim_unconfirmed")
        return False

    def shopping(self):
        """确认礼包商品区切换后领取免费物品；缺少证据则保留待核查结果。"""
        self.info_set("current_task", "shopping")
        self.info_set("每日礼包", "检查中")
        self.info_set("限时礼包", "待核查：未确认限时礼包页面")
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
            self.info_set("每日礼包", "待核查：未确认礼包页面")
            self.info_set("限时礼包", "待核查：未确认礼包页面")
            self.log_warning("未确认礼包商品内容切换，跳过免费礼包并继续后续任务")
            self.ensure_main()
            return "待核查"
        if not self._claim_shop_free_item(status_key="每日礼包", daily=True):
            self.ensure_main()
            return "待核查"
        previous = self.wait_until(self._shop_category_content, time_out=2, settle_time=0)
        if not self._switch_shop_category(["臻品礼包", "限时礼包"], previous):
            self.info_set("免费礼包", "待核查：未确认限时礼包页面")
            self.info_set("限时礼包", "待核查：未确认限时礼包页面")
            self.ensure_main()
            return "待核查"
        if not self._claim_shop_free_item(status_key="限时礼包"):
            self.ensure_main()
            return "待核查"
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
