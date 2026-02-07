import re

from ok import Logger, find_boxes_by_name, find_boxes_within_boundary
from src.tasks.BaseGfTask import BaseGfTask, pop_ups, stamina_re, map_re, parse_time_option
from src.tasks.CommunityClient import CommunityClient

logger = Logger.get_logger(__name__)


class DailyTask(BaseGfTask):

    def __init__(self, *args, **kwargs):
        """
            该模块总启动配置
        """
        super().__init__(*args, **kwargs)
        self.name = "一键日常"
        self.description = "收菜"

        self._init_default_config()
        self._init_stamina_options()
        self.add_exit_after_config()

    def _init_default_config(self):
        """

            输入框和选择框配置

        """
        self.default_config.update({
            '已确认启用游戏内全局自动功能': False,
            '当前物资关卡名称': '铸碑者的黎明',
            '体力本': "军备解析",
            '用户名': "",
            '密码': "",
            '喝水': '1.087-1.4-0.5',
            '吃饭': '1.0',
            "社区每日": False,
            '邮件': True,
            "情报补给": False,
            '闪耀星愿': False,
            '活动自律': True,
            '活动层': True,
            '公共区/调度室': True,
            '自主循环': False,
            '购买免费礼包': True,
            '商店心愿单购买': True,
            '自动刷体力': True,
            '刷钱本': False,
            '竞技场': True,
            '班组': True,
            '尘烟': True,
            '领任务': True,
            '大月卡': True,
        })

    def _init_stamina_options(self):
        """

            下拉框配置

        """
        self.stamina_options = ['军备解析', '深度搜索', '决策构象', '定向']
        self.config_type["体力本"] = {'type': "drop_down", 'options': self.stamina_options}

    def run(self):
        if not self.config.get('已确认启用游戏内全局自动功能'):
            self.confirm_auto_battle_up()
        tasks = [
            ("社区每日", self.community_daily),
            ("ensure_main", lambda: self.ensure_main(
                recheck_time=2,
                time_out=90
            )),
            ('邮件', self.mail),
            (['情报补给', '闪耀星愿'], self.activities),
            ('活动自律', self.activity),
            ('活动层', self.free_time_layer),
            ('公共区/调度室', self.gongongqu),
            ('购买免费礼包', self.shopping),
            ('自动刷体力', self.battle),
            ('竞技场', self.arena),
            ('班组', self.guild),
            ('领任务', self.claim_quest),
            ('大月卡', self.xunlu),
        ]

        failed_tasks = []
        for key, func in tasks:
            # -------- 关键逻辑开始 --------
            if key != "ensure_main":
                # 统一转为列表
                keys = [key] if isinstance(key, str) else list(key)

                # or 规则：任一为 True 即执行
                if not any(self.config.get(k) for k in keys):
                    continue

            result = func()  # 不捕获异常，异常自然向上传递
            if result is False:
                self.log_info(f"任务 {key} 执行失败或未完成")
                failed_tasks.append(key)

        if failed_tasks:
            self.log_info(f"以下任务未完成或失败: {failed_tasks}", notify=True)
        else:
            self.log_info("日常完成!", notify=True)

    def community_daily(self):
        user = self.config.get('用户名')
        pwd = self.config.get('密码')
        com = CommunityClient()
        self.info_set('current_task', 'community_daily')
        com.main(user, pwd)

    def confirm_auto_battle_up(self):
        """
        确认启用游戏内的全局自动战斗
        如果未启用，抛出异常提醒用户
        """
        raise Exception(
            "请先确认启用游戏内的全局自动战斗(设置->其他->自动战斗设置),"
            "然后勾选本软件内一键日常内的确认项"
        )

    def go_drink(self, after_sleep=None):
        down_times = parse_time_option((self.config.get('喝水')))
        self.press_keys_sequence(['a', 'w', 'd'], down_times, sleep_between=0.5)
        if after_sleep and after_sleep > 0:
            self.sleep(after_sleep)

    def go_eat(self, after_sleep=None):
        down_time = float(self.config.get('吃饭'))
        self.press_keys_sequence(['s', 'd'], [down_time, 0], sleep_between=1)
        if after_sleep and after_sleep > 0:
            self.sleep(after_sleep)

    def do_food_flow(
            self,
            *,
            enter_func,
            entry_match,
            main_btn,
            second_btn,
            skip_end_match,
            need_extra_confirm=False,
            need_again_test=False
    ):
        enter_func(after_sleep=1)
        times = 1
        if need_again_test:
            times = 2
        for attempt in range(times):
            if result := self.wait_ocr(match=entry_match, time_out=3):
                self.click_with_key('alt', result)
            else:
                return False
            if self.wait_click_ocr(match=main_btn, box='bottom_right', time_out=10):
                if self.wait_click_ocr(match=second_btn, time_out=3):
                    if need_extra_confirm:
                        self.wait_click_ocr(match='确认', time_out=3)
                    self.skip_dialogs(end_match=skip_end_match, time_out=60)
                    self.wait_click_ocr(match='确认', time_out=3)
                    self.wait_pop_up(count=1)
                return True
            else:
                if need_again_test and attempt == 0:
                    continue
                else:
                    self.back(after_sleep=2)
                    return False
        return False

    def free_time_layer(self):
        self.info_set('current_task', 'free_time_layer')
        for i in range(3):
            self.wait_click_ocr(match='活动层', box='right', time_out=2, raise_if_not_found=True)
            if self.is_free_layer():
                if i == 0:
                    self.do_food_flow(
                        enter_func=self.go_drink,
                        entry_match=re.compile('茶歇一刻'),
                        main_btn='制作',
                        second_btn='确认',
                        skip_end_match=['饮品加成', '确认'],
                        need_extra_confirm=False
                    )

                else:
                    self.do_food_flow(
                        enter_func=self.go_eat,
                        entry_match=re.compile('美味烹调'),
                        main_btn='下一步',
                        second_btn='确认邀请',
                        skip_end_match=['前往战役', '确认'],
                        need_extra_confirm=True,
                        need_again_test=True
                    )

            else:
                self.log_error('没检测到活动层页面')
            self.ensure_main(time_out=60)

    def activities(self):
        self.info_set('current_task', 'activity_stamina')
        self.wait_click_ocr(match=['活动'], box='bottom_right', after_sleep=0.5, raise_if_not_found=True)
        if self.config.get("情报补给"):
            if self.wait_click_ocr(match=['情报补给'], box='left', time_out=3, raise_if_not_found=False, after_sleep=1):
                while self.wait_click_ocr(match=['领取'], box='bottom_right', time_out=3, raise_if_not_found=False,
                                          after_sleep=1):
                    self.wait_pop_up(time_out=6)
        if not self.config.get('闪耀星愿'):
            self.ensure_main()
            return
        if not self.wait_click_ocr(match=[re.compile("闪耀星愿")], box='left', time_out=3, settle_time=2):
            self.ensure_main()
            return

        if not self.wait_click_ocr(match=['前往'], box='right', time_out=3, settle_time=2):
            self.ensure_main()
            return
        if not self.wait_click_ocr(match=['开始作战'], box='bottom_right', time_out=3, settle_time=2, after_sleep=2):
            self.ensure_main()
            return
        if self.wait_click_ocr(match=['取消'], time_out=1, after_sleep=2):
            self.ensure_main()
            return
        self.auto_battle(need_click_auto=True)
        self.wait_click_ocr(match=['自律'], box='bottom_right', after_sleep=2, settle_time=2)
        self.fast_combat(click_all=True, set_cost=1)
        self.ensure_main()

    def claim_quest(self):
        self.info_set('current_task', 'claim_quest')
        self.wait_click_ocr(match=['委托'], box='bottom_right', after_sleep=0.5, raise_if_not_found=True)
        self.wait_click_ocr(match=['一键领取', '领取全部'], box='bottom_right', time_out=3,
                            raise_if_not_found=False, after_sleep=2)
        results = self.wait_ocr(match=['领取全部', '无可领取报酬', '已全部领取'], box='left', time_out=15,log=True)
        # if results and results[0].name == '一键领取':
        if len(results) != 0:
            if results[0].name == '领取全部':
                self.click(results[0])
                self.wait_pop_up(time_out=4)
            elif results[0].name == '已全部领取' or results[0].name == '无可领取报酬':
                pass
            else:
                self.log_error("委托未领取")
        self.ensure_main()

    def mail(self):
        self.info_set('current_task', 'mail')
        if self.is_adb():
            self.click(0.07, 0.63)
        else:
            self.click(0.06, 0.7)
        self.wait_click_ocr(match=['领取全部'], box='bottom_left', time_out=4, after_sleep=2, raise_if_not_found=False)
        self.ensure_main()

    def xunlu(self):
        self.info_set('current_task', 'xunlu')
        if self.wait_click_ocr(match=['巡录'], box='bottom', after_sleep=0.5, time_out=2, raise_if_not_found=False):
            self.wait_click_ocr(match=['沿途行动'], box='top_right', time_out=4,
                                raise_if_not_found=True, after_sleep=1)
            self.wait_click_ocr(match=['一键领取', '领取全部'], box='bottom_right', time_out=4,
                                raise_if_not_found=False, after_sleep=1)
            self.ensure_main()

    def activity(self):
        activity_wuzi_names = str(self.config.get('当前物资关卡名称')).split(
            "-")
        self.info_set('current_task', 'activity')
        if to_activity_page := self.wait_click_ocr(match=['限时开启'], box='top_right', after_sleep=2,
                                                   raise_if_not_found=False,
                                                   time_out=4):
            if activities := self.wait_ocr(match=['开启中'], box='bottom_left', time_out=4):
                activity_count = 0
                for activity in activities:
                    self.ensure_main()
                    self.click(to_activity_page, after_sleep=2)
                    self.click(activity)
                    if activity_count >= len(activity_wuzi_names):
                        activity_count -= 1
                    if to_clicks := self.wait_ocr(match=[f"{activity_wuzi_names[activity_count]}·上篇",
                                                         f"{activity_wuzi_names[activity_count]}·下篇"],
                                                  raise_if_not_found=False, time_out=6, settle_time=2, log=True):
                        activity_count += 1
                        to_clicks2 = None
                        for click in to_clicks:
                            if "下篇" in click.name:
                                self.click(click)
                                break
                            else:
                                to_clicks2 = click
                        if to_clicks2:
                            self.sleep(1)
                            self.click(to_clicks2)
                    elif to_clicks := self.wait_ocr(match=['活动战役', re.compile('物资')], box='bottom',
                                                    raise_if_not_found=False, time_out=4, settle_time=2, log=True):
                        self.click(to_clicks, after_sleep=2)
                    if to_clicks:
                        self.sleep(2)
                        if wu_zi := self.ocr(match=re.compile('物资'), box='bottom_right'):
                            self.click(wu_zi, after_sleep=0.5)
                        battles = self.wait_ocr(match=map_re, time_out=4)
                        if battles:
                            self.click(battles[-1])
                            self.fast_combat(set_cost=1, battle_max=6, activity=True)
            else:
                self.log_info("找不到开启的活动")
        self.ensure_main()

    def find_activities(self):
        return self.wait_ocr(match=[re.compile(r'^\d+天\d+小时')], box='bottom_left',
                             raise_if_not_found=False, time_out=4)

    def find_latest_activity(self):
        boxs = self.find_activities()

        def parse_time(name):
            match = re.match(r'^(\d+)天(\d+)小时', name)
            if match:
                days = int(match.group(1))
                hours = int(match.group(2))
                return days * 24 + hours
            return 0

        if not boxs:
            return None
        longest = max(boxs, key=lambda b: parse_time(b.name))
        return longest

    def gongongqu(self):
        self.info_set('current_task', 'gongongqu')
        self.wait_click_ocr(match=['委托'], box='right', after_sleep=2.5, raise_if_not_found=True)
        buttons = self.find_feature(feature_name='ggq_can_button', box='left')
        if not self.config.get('自主循环'):
            self.click(buttons[0])
            if self.wait_ocr(match=['最小'], time_out=4, settle_time=2, log=True):
                self.wait_click_ocr(match=['确认'], after_sleep=2.5, raise_if_not_found=True)
            self.back(after_sleep=2)
        self.click(buttons[1], after_sleep=2)
        if self.wait_ocr(match='获得道具', box='top', time_out=2, log=True):
            self.back(after_sleep=2)
        else:
            self.wait_pop_up(count=1)
        if len(buttons) > 2:
            self.click(buttons[2], after_sleep=2)
            self.wait_click_ocr(match=['再次派遣'], box='bottom', after_sleep=2, raise_if_not_found=False)
        if self.config.get("自主循环"):
            self.auto_loop()
        self.ensure_main()
        steps = [
            lambda: self.wait_click_ocr(
                match=[re.compile("自主循环")],
                box="bottom_left",
                time_out=5,
                after_sleep=2,
                log=True,
            ),
            lambda: self.wait_click_ocr(
                match="开始循环", box="bottom_left", time_out=5, after_sleep=2, log=True
            ),
            lambda: self.wait_click_ocr(match=["确认"], after_sleep=2),
            lambda: self.wait_click_ocr(
                match=["循环结束"], time_out=600, box="top", after_sleep=2
            ),
            lambda: self.wait_click_ocr(match=["确认"], after_sleep=2),
        ]

        if self.config.get("自主循环"):

            retries = [0] * len(steps)
            i = 0

            while 0 <= i < len(steps):

                if steps[i]():
                    retries[i] = 0
                    i += 1
                    continue

                # 失败
                retries[i] += 1

                if retries[i] >= 2:
                    print(f"步骤{i}失败两次，终止流程")
                    break

                # 回退上一层
                if i > 0:
                    i -= 1
    def auto_loop(self):
        steps = [
            [
                lambda: self.wait_click_ocr(
                    match=[re.compile("自主循环")],
                    box="bottom_left",
                    time_out=5,
                    after_sleep=2,
                    log=True,
                ),
                True,
                True,  # retry_on_fail, rollback_on_fail
            ],
            [
                lambda: self.wait_click_ocr(
                    match="开始循环",
                    box="bottom_left",
                    time_out=5,
                    after_sleep=2,
                    log=True,
                ),
                True,
                True,  # retry_on_fail, rollback_on_fail
            ],
            [
                lambda: self.wait_click_ocr(match=["确认"], after_sleep=2),
                True,
                True,  # retry_on_fail, rollback_on_fail
            ],
            [
                lambda: self.wait_click_ocr(
                    match=["循环结束"], time_out=600, box="top", after_sleep=2
                ),
                True,
                False,  # retry_on_fail, rollback_on_fail (关键：失败时不回退)
            ],
            [
                lambda: self.wait_click_ocr(match=["确认"], after_sleep=2),
                True,
                False,  # retry_on_fail, rollback_on_fail
            ],
        ]
        # 执行
        success = self.run_steps_with_retry_and_rollback(steps)
        if not success:
            raise Exception("自主循环失败")
    def shopping(self):
        self.info_set('current_task', 'shopping')
        self.wait_click_ocr(match=['商城'], box='bottom_right', after_sleep=1.5, raise_if_not_found=True)
        self.wait_click_ocr(match=['品质甄选'], box='top_left', after_sleep=1, raise_if_not_found=True)
        self.wait_click_ocr(match=['周期礼包', '常驻礼包'], box='top', after_sleep=1, raise_if_not_found=True)
        if self.wait_click_ocr(match=['免费'], after_sleep=0.5, raise_if_not_found=False, time_out=1):
            self.log_info('found free item to buy')
            self.wait_click_ocr(match=['确认', '购买'], box='bottom', after_sleep=1.5, raise_if_not_found=True)
            self.wait_pop_up(time_out=5, count=1)
            self.back()
            self.sleep(1)
        self.wait_click_ocr(match=['限时礼包'], box='top', after_sleep=0.5, raise_if_not_found=True, time_out=2)
        if self.wait_click_ocr(match=['免费'], after_sleep=0.5, raise_if_not_found=False, time_out=1):
            self.log_info('found free item to buy')
            if self.wait_click_ocr(match=['确认', '购买'], box='bottom', after_sleep=1.5, raise_if_not_found=True):
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
            if not self.wait_click_ocr(match="一键购买", box="bottom_right", time_out=1, raise_if_not_found=False):
                continue  # 找不到一键购买按钮就跳过
            if self.wait_click_ocr(match='购买', after_sleep=1, raise_if_not_found=False):
                self.wait_pop_up(time_out=5, count=1)

    def arena(self):
        if self.config.get('自主循环'):
            self.ensure_main()
            return
        self.info_set('current_task', 'arena')
        self.wait_click_ocr(match=re.compile('战役推进'), box='top_right', after_sleep=1, raise_if_not_found=True)
        self.wait_ocr(match=re.compile('补给作战'), box='top_right', raise_if_not_found=True)
        self.sleep(1)
        self.click_relative(0.89, 0.05)  # 模拟战斗
        self.wait_click_ocr(match=['实兵演习'], box='bottom', after_sleep=0.5, raise_if_not_found=True)
        self.wait_pop_up(time_out=15)
        remaining_count = self.arena_remaining()
        if remaining_count > 1:
            self.wait_click_ocr_with_pop_up("进攻", box='bottom_right')
            self.sleep(2)
            self.challenge_arena_opponent()
            self.back()
            self.sleep(1)
        # if count > 0:
        #     self.click_relative(0.34 if self.is_adb() else 0.26, 0.89, after_sleep=0.5)
        #     if not self.wait_ocr(match=['演习补给'], box='top', time_out=4):
        #         self.wait_pop_up(time_out=4)
        if self.wait_click_ocr(match=['周期奖励'], box='left', after_sleep=1, raise_if_not_found=True):
            self.wait_click_ocr(match=['一键领取'], after_sleep=1, raise_if_not_found=False)
        self.ensure_main()

    def bingqi(self):
        if self.config.get('自主循环'):
            self.ensure_main()
            return
        self.info_set('current_task', 'bingqi')
        self.wait_click_ocr(match=re.compile('战役推进'), box='top_right', after_sleep=1, raise_if_not_found=True)
        self.wait_ocr(match=re.compile('补给作战'), box='top_right', raise_if_not_found=True)
        self.sleep(1)
        self.click_relative(0.90, 0.05, after_sleep=0.95)  # 补给
        self.click_relative(0.98, 0.49, after_sleep=0.52)
        self.wait_ocr(match='防御阵容', box='right', time_out=30,
                      post_action=lambda: self.click_relative(0.5, 0.5, after_sleep=2))
        while self.find_top_right_count():
            self.info_incr('bingqi')
            self.wait_click_ocr(match=['匹配'], box='bottom', after_sleep=0.5, raise_if_not_found=True)
            self.auto_battle(end_match='匹配')
            self.sleep(2)
        self.ensure_main()

    def guild(self):
        self.info_set('current_task', 'guild')
        self.wait_click_ocr(match=['班组'], box='bottom_right', after_sleep=0.5, raise_if_not_found=True)
        self.wait_click_ocr(match=['要务'], box='bottom_right', after_sleep=0.5, raise_if_not_found=True, settle_time=2)
        result = self.wait_ocr(match=['开始作战', '每日要务已完成'], box='bottom_right',
                               raise_if_not_found=True, log=True)
        if result[0].name == '开始作战':
            self.click(result)
            self.auto_battle()
            self.wait_ocr(match=['开始作战', '每日要务已完成', '要务'], box='bottom_right',
                          raise_if_not_found=True)
        else:
            self.log_info('每日要务已完成')
        self.back()
        self.sleep(1)
        self.chenyan()

        self.wait_click_ocr(match=['补给'], box='bottom_right', after_sleep=0.5)
        if result := self.wait_ocr(match=['领取全部'], box='bottom_right', time_out=4,
                                   raise_if_not_found=False):
            self.click_box(result)
            self.wait_pop_up()
        self.back()
        self.sleep(1)
        self.ensure_main()

    def chenyan(self):
        if not self.config.get('尘烟'):
            return
        end = self.ocr(match=re.compile('后结束$'), box='bottom_right')
        if not end:
            return
        self.click(end, after_sleep=1)
        result = self.ocr(0.89, 0.01, 0.99, 0.1, match=stamina_re, box='top_right')
        if not result:
            raise Exception('找不到尘烟票')
        while True:
            tickets = int(result[0].name.split('/')[0])
            self.log_info(f'chenyan tickets {tickets}')
            self.info_set('chenyan tickets', tickets)
            if tickets == 0:
                break
            self.wait_click_ocr(match='攻坚战', box='top_right', after_sleep=0.5, raise_if_not_found=True)
            self.wait_click_ocr(match='开始作战', box='bottom_right', after_sleep=2, raise_if_not_found=True)
            self.choose_chenyan(tickets)
            self.sleep(2)
            result = self.ocr(0.89, 0.01, 0.99, 0.1, match=stamina_re, box='top_right')
        self.back(after_sleep=2)

    def choose_chenyan(self, tickets):
        existing = self.ocr(box=self.box_of_screen(0.61, 0.69, 0.88, 0.83), match=re.compile(r"^\d+$"))
        for exist in existing:
            self.click_box(exist, after_sleep=0.1)
        self.click_relative(0.28, 0.35, after_sleep=0.2)
        self.click_relative(0.21, 0.64, after_sleep=0.2)
        self.click_relative(0.28, 0.35, after_sleep=0.2)
        if tickets == 2:
            self.click_relative(0.16, 0.47, after_sleep=0.2)  # 编队1
        else:
            self.click_relative(0.16, 0.56, after_sleep=0.2)  # 编队2
        x_start = 0.06
        step = (0.24 - 0.03) / 3
        for i in range(4):
            self.click_relative(x_start + step * i, 0.45, after_sleep=0.2)

        self.wait_click_ocr(match='助战', box='bottom_right', settle_time=1, after_sleep=1, raise_if_not_found=True)
        priority = ['威玛西娜', '可露凯', '夏安', '罗蕾莱', '春田', '莱妮', '妮基塔', '玛绮朵', '洛贝拉', '托洛洛',
                    '琼玖']
        selected = False
        my_chars = []

        for name, m in [(i, self.get_role_by_name(i)) for i in priority]:
            self.wait_click_ocr(match=m, time_out=2, after_sleep=2)

            chars = self.ocr(0.18, 0.27, 0.82, 0.79, match=re.compile(r'^\D*$'))
            solved_chars = [char for char in chars if char.name == name]

            if not solved_chars:
                continue

            self.click(solved_chars[0], after_sleep=1)

            join = self.ocr(match='入队', box='bottom_right')
            if not join:
                continue

            self.click_box(join, after_sleep=1)

            if self.ocr(box='bottom_right', match="确认"):
                my_chars.append(name)
                self.back(after_sleep=1)
                self.log_info(f'duplicate char {my_chars}')
            else:
                selected = True
                break
        if not selected:
            self.log_info('no priority char joined, fallback start')

            attr_order = ['物理', '酸蚀', '浊刻', '燃烧', '冷凝', '电导']

            for attr in attr_order:
                self.wait_click_ocr(match=attr, time_out=2, after_sleep=2)

                chars = self.ocr(
                    0.18, 0.27, 0.82, 0.79,
                    match=re.compile(r'^\D*$')
                )

                for char in chars:
                    if char.name in my_chars:
                        continue

                    self.click(char, after_sleep=1)

                    join = self.ocr(match='入队', box='bottom_right')
                    if not join:
                        continue

                    self.click_box(join, after_sleep=1)

                    if self.ocr(box='bottom_right', match="确认"):
                        my_chars.append(char.name)
                        self.back(after_sleep=1)
                        self.log_info(f'duplicate char {char.name}')
                    else:
                        self.log_info(f'fallback joined char: {char.name}')
                        selected = True
                        break

                if selected:
                    break

        self.wait_click_ocr(match='确定', box='bottom_right')
        self.auto_battle('开始作战', 'bottom_right')

    def wait_click_ocr_with_pop_up(self, match, box=None):
        if self.wait_until(lambda: self.do_wait_pop_up_and_click(match, box), time_out=10, raise_if_not_found=True):
            self.sleep(0.5)
            return True
        return None

    def do_wait_pop_up_and_click(self, match, box):
        boxes = self.ocr()
        if find_boxes_by_name(boxes, pop_ups):
            self.back(after_sleep=2)
            return False
        elif click := find_boxes_by_name(boxes, match):
            if click := find_boxes_within_boundary(click, self.get_box_by_name(box)):
                self.click(click)
                return True
            return None
        return None

    def wait_ocr_with_possible_pop_up(self, match, box=None, raise_if_not_found=True,
                                      time_out=30):
        if self.wait_until(lambda: self.do_wait_pop_up_and_click(match, box), time_out=time_out,
                           raise_if_not_found=raise_if_not_found):
            self.sleep(0.5)
            return True
        return None

    def do_wait_ocr_with_possible_pop_up(self, match, box):
        boxes = self.ocr()
        if find_boxes_by_name(boxes, pop_ups):
            self.back(after_sleep=2)
            return False
        elif click := find_boxes_by_name(boxes, match):
            if box:
                return find_boxes_within_boundary(click, self.get_box_by_name(box))
            else:
                return click
        return None

    def arena_remaining(self):
        return int(self.ocr(0.89, 0.01, 0.99, 0.1, match=stamina_re)[0].name.split('/')[0])

    def challenge_arena_opponent(self):
        challenged = 0
        waited_pop_up = False
        while True:
            remaining_count = self.arena_remaining()
            self.log_info(f'challenge_arena_opponent remaining_count {remaining_count}')
            if remaining_count <= 1:
                self.log_info(f'challenge arena complete {remaining_count}')
                break
            boxes = self.ocr(0, 0.51, 0.94, 0.59, match=re.compile(r"^[1-9]\d*$"))
            if len(boxes) < 3:
                if not waited_pop_up:
                    waited_pop_up = True
                    self.wait_pop_up(time_out=15) and self.wait_pop_up(time_out=15) and self.wait_pop_up(time_out=15)
                    continue
                else:
                    raise Exception("找不到五个演习对手")
            self.log_info(f'arena opponents {boxes}')
            for box in boxes:
                if remaining_count - challenged <= 1:
                    self.log_info(f'challenged enough return {remaining_count} {challenged}')
                    return challenged
                if int(box.name) < 5000:
                    search_success = box.copy()
                    search_success.width = self.width_of_screen(0.17)
                    search_success.height = self.height_of_screen(0.15)
                    search_success.y -= search_success.height
                    if not self.ocr(match=re.compile('挑战'), box=search_success, log=True):
                        self.log_info(f'challenge opponent {box.name}')
                        self.click(box)
                        self.wait_click_ocr(match=['进攻'], box='bottom_right', after_sleep=0.5,
                                            raise_if_not_found=True)
                        self.auto_battle(end_match='刷新')
                        self.sleep(3)
                        challenged += 1
                        continue
            if self.ocr(match=['刷新消耗'], box='bottom_right'):
                self.log_info(f'no refresh count remains')
                return challenged
            self.wait_click_ocr(match='刷新', box='bottom_right', after_sleep=2, raise_if_not_found=True)
        return challenged

    def battle(self):
        if self.config.get('自主循环'):
            self.ensure_main()
            return
        self.info_set('current_task', 'battle')
        self.wait_click_ocr(match=re.compile('战役推进'), box='top_right', after_sleep=0.5, raise_if_not_found=True)
        self.wait_ocr(match=re.compile('补给作战'), box='top_right', raise_if_not_found=True)
        self.click_relative(0.78, 0.05)
        if self.is_adb():
            self.swipe_relative(0.8, 0.6, 0.5, 0.6, duration=1)
        self.sleep(1)
        remaining = 10000
        if self.config.get('刷钱本'):
            self.wait_click_ocr(match=['标准同调'], box='right', after_sleep=0.5, raise_if_not_found=True)
            remaining = self.fast_combat(battle_max=4, set_cost=20)
            self.back(after_sleep=1)
        target = self.config.get('体力本')
        cost_dict = {"深度搜索": 10, "军备解析": 10, "决策构象": 20, "定向精研": 30}
        min_stamina = cost_dict.get(target, 30)
        if remaining >= min_stamina:
            ding_xiang = self.stamina_options.index(target) >= 3
            if ding_xiang:
                target = '定向精研'
            self.wait_click_ocr(match=target, settle_time=1, after_sleep=0.5, raise_if_not_found=True, log=True)
            # if ding_xiang:
            #     self.wait_click_ocr(match=re.compile(self.config.get('体力本')),
            #                         box=self.box_of_screen(0.01, 0.21, 0.73, 0.31),
            #                         settle_time=0.5,
            #                         after_sleep=0.5, log=True,
            #                         raise_if_not_found=True)
            while remaining >= min_stamina:
                if ding_xiang:
                    remaining = self.fast_combat(plus_x=0.69, plus_y=0.59, set_cost=cost_dict[target])
                else:
                    remaining = self.fast_combat(set_cost=cost_dict.get(target, None))
        self.ensure_main()


def sort_characters_by_priority(chars, priority):
    """
    Sorts a list of character objects based on their 'char_name' attribute,
    according to a priority list.

    Characters whose 'char_name' attribute appears in the priority list are
    placed at the front, sorted by their order within the priority list.
    Characters not in the priority list retain their original order.

    Args:
        chars: A list of character objects, where each object has a 'char_name' attribute (string).
        priority: A list of character names (strings) representing the priority order.

    Returns:
        A new list of character objects, sorted according to the priority.  The
        original `chars` list is not modified.
    """

    priority_map = {name: index for index, name in enumerate(priority)}
    sorted_chars = []

    for i, the_char in enumerate(chars):  # Use enumerating to get the original index
        char_name = the_char.name.lower()
        if char_name in priority_map:
            sorted_chars.append((priority_map[char_name], i, the_char))  # (priority_index, original_index, char_object)
        else:
            sorted_chars.append((len(priority), i, the_char))  # (lowest_priority, original_index, char_object)

    sorted_chars.sort()  # Sort the list of tuples

    return [char_object for _, _, char_object in sorted_chars]  # Extract the character objects


text_fix = {
    '再次派造': '再次派遣',
}
