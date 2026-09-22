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
        self.info_set('每日行动', '未检查')
        self.info_set('巡录奖励', '未检查')
        box = self.wait_ocr(match=[re.compile(r'^巡录$')], box=self.box._xunlun, time_out=3, raise_if_not_found=False)
        if not box:
            self.log_info('未找到「巡录」入口，跳过')
            self.ensure_main()
            return False
        self.click_box_by_match_position(box, '巡录', after_sleep=2)
        # 预览页入口是可选的；通行证奖励页并不是每日行动页。
        if self.wait_click_ocr(match=[re.compile(r'^开启远航巡录$')], box=self.box.bottom_left,
                               time_out=3, raise_if_not_found=False, after_sleep=2):
            self.log_info('已通过「开启远航巡录」进入大月卡主页')
        # 必须切换到沿途行动；两个页面都有“一键领取”，不能仅凭按钮判断。
        if not self.wait_click_ocr(match=[re.compile(r'^沿途行动$')], box=self.box.top,
                                   time_out=4, raise_if_not_found=False, after_sleep=1):
            self.log_info('未找到「沿途行动」页签，巡录每日奖励未完成')
            self.ensure_main()
            return False
        if not self.wait_ocr(match=[re.compile(r'^每日行动$')], box=self.box.left,
                             time_out=4, raise_if_not_found=False):
            self.log_info('未确认进入每日行动页面，跳过领取')
            self.ensure_main()
            return False
        # 单项“领取”也在右下半屏，只匹配底部的一键领取，避免仅领取一项就离开。
        # 分别确认行动里程和巡录道具，不能用行动按钮是否存在决定整项成败。
        action_box = self.box_of_screen(0.70, 0.88, 1, 1)
        claim_match = re.compile(r'^一\s*键\s*领\s*取$')
        clicked = self.wait_click_ocr(match=[claim_match], box=action_box, time_out=4,
                                      raise_if_not_found=False, after_sleep=1)
        if clicked:
            # 行动里程直接入账：确认仍在行动页，且原先可见的领取按钮消失。
            if not self.wait_ocr(match=[re.compile(r'^每日行动$')], box=self.box.left,
                                 time_out=3, raise_if_not_found=False):
                action_result = '待核查'
            elif self.wait_ocr(match=[claim_match], box=action_box,
                               time_out=2, raise_if_not_found=False):
                self.log_error('每日行动点击领取后按钮仍在，未确认领取完成')
                action_result = False
            else:
                action_result = True
        else:
            action_result = self._xunlu_no_reward_status()
        self._record_xunlu_result('每日行动', action_result)
        # 先收集行动里程，再回到远航巡录页领取等级/盈余奖励。
        if not self.wait_click_ocr(match=[re.compile(r'^远航巡录$')],
                                   box=self.box_of_screen(0.25, 0, 0.65, 0.12),
                                   time_out=4, raise_if_not_found=False, after_sleep=1):
            self.log_error('未能切换到远航巡录，奖励领取未完成')
            self.ensure_main()
            return False
        if self.wait_click_ocr(match=[claim_match], box=self.box.bottom_right, time_out=4,
                               raise_if_not_found=False, after_sleep=1):
            reward_result = self._claim_xunlu_rewards()
        else:
            # 必须仍在巡录页；不能把错误页面上的按钮缺失当作已领取。
            if not self.wait_ocr(match=[re.compile(r'^大奖预览$|^通行证$')],
                                 box=self.box_of_screen(0, 0, 1, 1),
                                 time_out=3, raise_if_not_found=False):
                self.log_error('未确认巡录奖励页面，无法检查领取状态')
                reward_result = False
            else:
                reward_result = self._xunlu_no_reward_status()
        self._record_xunlu_result('巡录奖励', reward_result)
        self.ensure_main()
        if action_result is False or reward_result is False:
            return False
        if action_result == '待核查' or reward_result == '待核查':
            return '待核查'
        return True

    def _xunlu_no_reward_status(self):
        # 仅接受明确的整体状态；单条任务的“已领取”不能证明全部领完。
        if self.wait_ocr(match=[re.compile(r'^\s*(?:已全部领取|全部已领取|暂无可领取奖励|无可领取奖励)\s*$')],
                         box=self.box.bottom_right, time_out=2, raise_if_not_found=False, log=True):
            return True
        return '待核查'

    def _record_xunlu_result(self, name, result):
        status = ('领取已确认／已无可领取奖励' if result is True else
                  '执行失败' if result is False else '待核查：缺少领取结果证据')
        self.info_set(name, status)
        self.log_info(f'{name}：{status}')

    def _claim_xunlu_rewards(self):
        # 自选补给包可能直接出现，也可能跟在普通奖励确认之后。
        pack_title = re.compile(r'^拂晓之光补给包$')
        reward_title = re.compile(r'^领取奖励$')
        # 「获得道具」是奖励到账的正面证据，缺少它不能判定领取成功。
        obtained_title = re.compile(r'^获得道具$')
        obtained = False
        for _ in range(8):
            titles = self.wait_ocr(match=[pack_title, reward_title, obtained_title],
                                   box=self.box_of_screen(0, 0, 1, 1),
                                   time_out=4, raise_if_not_found=False, log=True)
            if not titles:
                if obtained:
                    return True
                self.log_info('未看到获得道具，巡录领取结果待核查')
                return '待核查'
            if any(obtained_title.search(title.name) for title in titles):
                obtained = True
                self.log_info('巡录已显示获得道具，确认奖励到账')
                self.click(0.5, 0.95, after_sleep=1)
                continue
            if any(pack_title.search(title.name) for title in titles):
                reward = self.config.get('拂晓之光补给包奖励', '数据链路')
                if not reward:
                    self.log_error('未配置拂晓之光补给包奖励，请手动选择')
                    return False
                reward_match = re.compile(r'^\s*' + r'\s*'.join(re.escape(c) for c in reward) + r'\s*$')
                if not self.wait_click_ocr(match=[reward_match],
                                           box=self.box_of_screen(0.20, 0.34, 0.80, 0.53),
                                           time_out=4, raise_if_not_found=False, after_sleep=0.5):
                    self.log_error(f'补给包未找到配置奖励「{reward}」，请手动选择')
                    return False
                button = re.compile(r'^开启$')
                # 仅匹配选择弹窗底部右侧的“开启”。
                button_box = self.box_of_screen(0.51, 0.67, 0.71, 0.76)
            else:
                button = re.compile(r'^确认$')
                button_box = self.box.bottom_right
            if not self.wait_click_ocr(match=[button], box=button_box,
                                       time_out=4, raise_if_not_found=False, after_sleep=1, log=True):
                self.log_error('未找到巡录奖励弹窗操作按钮，领取未完成')
                return False
        self.log_error('巡录奖励弹窗连续出现或未关闭，请手动检查')
        return False

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
