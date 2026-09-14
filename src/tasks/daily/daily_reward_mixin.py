"""日常任务的各类奖励领取：邮件、委托、巡录、探索、闪耀星愿、社区每日。"""

import re


class DailyRewardMixin:
    def community_daily(self):
        user = self.config.get('用户名')
        pwd = self.config.get('密码')
        self.info_set('current_task', 'community_daily')
        self.run_community_flow(user, pwd)

    def mail(self):
        self.info_set('current_task', 'mail')
        if self.is_adb():
            self.click(0.07, 0.63)
        else:
            self.click(0.06, 0.7)
        self.wait_click_ocr(match=['领取全部'], box=self.box.bottom_left, time_out=4, after_sleep=2,
                            raise_if_not_found=False)
        self.ensure_main()

    def claim_quest(self):
        self.info_set('current_task', 'claim_quest')
        if result := self.wait_ocr(match=re.compile('委托'), box=self.box._claim, raise_if_not_found=True):
            self.click_box_by_match_position(result, "委托", after_sleep=2)
            self.wait_click_ocr(match=[re.compile('领取')], box=self.box_of_screen(1423/1920,939/1080,1,1), time_out=6,
                                log=True,raise_if_not_found=False, after_sleep=2)
            results = self.wait_ocr(match=['领取全部', '已全部领取'], box=self.box.left, time_out=15, log=True)
            # if results and results[0].name == '一键领取':
            if results:
                if results[0].name == '领取全部':
                    self.click(results[0])
                    self.wait_pop_up(time_out=4, count=1)
                elif results[0].name == '已全部领取':
                    pass
                else:
                    self.log_error("未知的领取状态")
            else:
                self.log_error("委托未领取")
        self.ensure_main()

    def xunlu(self):
        self.info_set('current_task', 'xunlu')
        box = self.wait_ocr(match=[re.compile(r'^巡录$')], box=self.box._xunlun, time_out=3, raise_if_not_found=False)
        if not box:
            self.log_info('未找到「巡录」入口，跳过')
            self.ensure_main()
            return
        self.click_box_by_match_position(box, '巡录', after_sleep=2)
        # 「巡录」入口会随版本/活动状态呈现两种形态，依次兼容：
        #   A) 直接进入「远航巡录」主页：底部有「沿途行动」标签与「一键领取」按钮
        #   B) 先弹出奖励预览页，需点左下「开启远航巡录」再进入主页
        if self.wait_click_ocr(match=['开启远航巡录', '远航巡录'], box=self.box.bottom_left,
                               time_out=3, raise_if_not_found=False, after_sleep=2):
            self.log_info('已通过「开启远航巡录」进入大月卡主页')
        # 兼容 A：主页可见「一键领取」时直接领取「沿途行动」免费档奖励
        self.wait_click_ocr(match=[re.compile('一键领取')], box=self.box.bottom,
                            time_out=3, raise_if_not_found=False, after_sleep=1.5)
        # 兼容两种形态的奖品格「领取」按钮
        self.wait_click_ocr(match=[re.compile('领取')], box=self.box.bottom_right, time_out=3,
                            raise_if_not_found=False, after_sleep=1)
        self.back()
        self.sleep(1)
        self.ensure_main()

    def explore_claim(self):
        self.info_set('current_task', 'explore_claim')
        if not self.wait_click_ocr(match='限时开启', box=self.box.top_right, after_sleep=2, time_out=2,
                                   raise_if_not_found=True, log=True):
            return
        if not self.wait_click_ocr(match=re.compile('边界推进'), box=self.box.top_right, after_sleep=6, time_out=2,
                                   raise_if_not_found=True, log=True):
            return
        if not self.wait_click_ocr(match=re.compile('采集'), box=self.box.bottom_right, after_sleep=2, time_out=2,
                                   raise_if_not_found=True, log=True):
            return
        if not self.wait_click_ocr(match=re.compile('领取'), box=self.box.bottom_right, time_out=2,
                                   raise_if_not_found=True, after_sleep=2, log=True):
            return
        self.wait_pop_up(count=1)
        if not self.wait_click_ocr(match=re.compile('派遣'), box=self.box.bottom_right, after_sleep=2, time_out=2,
                                   raise_if_not_found=False, log=True):
            return

    def star_wish(self):
        self.info_set('current_task', 'star_wish')
        if not self.wait_click_ocr(match=[re.compile("闪耀星愿")], box=self.box_of_screen(0.036, 0.185, 0.229, 0.819), time_out=3, settle_time=0.5):
            self.ensure_main()
            return

        if not self.wait_click_ocr(match=['开始作战'], box=self.box.bottom_right, time_out=3, settle_time=0.5,
                                   after_sleep=0.5):
            if self.wait_click_ocr(match=re.compile("一{0,1}键领取"), box=self.box.bottom_right, time_out=3, settle_time=0.5,
                                   after_sleep=0.5):
                self.wait_pop_up(count=1)
                self.ensure_main()
                return
            self.log_info('闪耀星愿未找到开始作战和一键领取，尝试跳过对话框后重试', notify=True)
            result = self.skip_dialogs(end_match=['开始作战'], end_box=self.box.bottom_right, time_out=30,
                                       has_dialog=True, raise_if_not_found=False)
            if not result:
                self.ensure_main()
                return
            self.click_box(result, after_sleep=1)
        if self.wait_click_ocr(match=['取消'], time_out=1, after_sleep=0.5):
            self.ensure_main()
            return
        self.auto_battle(need_click_auto=True)
        self.wait_click_ocr(match=['自律'], box=self.box.bottom_right, after_sleep=0.5, settle_time=0.5)
        self.fast_combat(click_all=True, set_cost=1)
        self.ensure_main()
