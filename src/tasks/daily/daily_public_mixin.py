"""公共区/调度室与商店：委托派遣、游戏内自主循环、免费礼包与心愿单购买。"""

import re
import time
from ok import Logger, find_boxes_by_name, Box


class DailyPublicMixin:
    def gongongqu(self):
        self.info_set('current_task', 'gongongqu')
        if result := self.wait_ocr(match=re.compile('委托'), box=self.box._claim, raise_if_not_found=True, log=True):
            self.click_box_by_match_position(result, "委托", after_sleep=2)
            start_time = time.time()
            while True:
                if time.time() - start_time > 10:
                    self.log_info("公共区委托界面停留过久，返回")
                    break
                buttons = self.find_feature(feature_name='ggq_can_button', box=self.box.left)
                if buttons and len(buttons) >= 2:
                    break            
            if not self.config.get('自主循环'):
                if buttons:
                    self.click(buttons[0])
                if self.wait_ocr(match=['最小'], time_out=4, settle_time=2, log=True):
                    self.wait_click_ocr(match=['确认'], after_sleep=2.5, raise_if_not_found=True)
                self.back(after_sleep=2)

            if buttons and len(buttons) >= 2:
                self.click(buttons[1], after_sleep=2)
            if self.wait_ocr(match='获得道具', box=self.box.top, time_out=2, log=True):
                self.back(after_sleep=2)
            else:
                self.wait_pop_up(count=1)
            if buttons and len(buttons) > 2:
                self.click(buttons[2], after_sleep=2)
                self.wait_click_ocr(match=[re.compile('再次派[遣造]')], box=self.box.bottom, after_sleep=2, raise_if_not_found=False)
            if self.config.get("自主循环"):
                self.auto_loop()

    def _auto_loop_step_with_retry(self, step_num, match, need_confirm=False, box=None, time_out=5, after_sleep=2, **kwargs):
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
            result = self.wait_click_ocr(
                match=match, box=box, time_out=time_out, after_sleep=0, log=True, **kwargs
            )
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
                if need_confirm and self.ocr(box=self.box.center, match='确认'):
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
            step_num=5,
            match=["确认"],
            settle_time=2,
            after_sleep=2,
            box=self.box.bottom
        ):
            return

    def shopping(self):
        self.info_set('current_task', 'shopping')
        self.wait_click_ocr(match=['商城'], box=self.box.bottom_right, after_sleep=1.5, raise_if_not_found=True)
        self.wait_click_ocr(match=['品质甄选'], box=self.box.top_left, after_sleep=1, raise_if_not_found=True)
        self.wait_click_ocr(match=['周期礼包', '常驻礼包'], box=self.box.top, after_sleep=1, raise_if_not_found=True)
        if self.wait_click_ocr(match=['免费'], after_sleep=0.5, raise_if_not_found=False, time_out=1):
            self.log_info('found free item to buy')
            self.wait_click_ocr(match=['确认', '购买'], box=self.box.bottom, after_sleep=1.5, raise_if_not_found=True)
            self.wait_pop_up(time_out=5, count=1)
            self.back()
            self.sleep(1)
        self.wait_click_ocr(match=["臻品礼包", "限时礼包"], box=self.box.top, after_sleep=0.5,
                            raise_if_not_found=True, time_out=2)
        if self.wait_click_ocr(match=['免费'], after_sleep=0.5, raise_if_not_found=False, time_out=1):
            self.log_info('found free item to buy')
            if self.wait_click_ocr(match=['确认', '购买'], box=self.box.bottom, after_sleep=1.5,
                                   raise_if_not_found=True):
                self.back()
                self.sleep(1)
        if self.config.get('商店心愿单购买'):
            self.buy_others()
        self.ensure_main()

    def buy_others(self):
        self.info_set('current_task', '心愿单购买')
        self.click(0.055, 0.946, after_sleep=1)
        others_list = ['家具商店', '班组商店', '调度商店', '讯段交易', '心智统合', '人形堆栈']
        for other in others_list:
            if not self.wait_click_ocr(match=other, after_sleep=1, raise_if_not_found=False):
                continue  # 找不到商店就跳过
            if not self.wait_click_ocr(match=re.compile("购买"), box=self.box.bottom_right, time_out=1,
                                       raise_if_not_found=False):
                continue  # 找不到一键购买按钮就跳过
            if self.wait_click_ocr(match='购买', after_sleep=1, raise_if_not_found=False):
                self.wait_pop_up(time_out=5, count=1)
