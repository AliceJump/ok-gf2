import re

from ok import Logger, find_boxes_by_name, find_boxes_within_boundary
from src.tasks.BaseGfTask import BaseGfTask, pop_ups, stamina_re, map_re

logger = Logger.get_logger(__name__)


class DailyTask(BaseGfTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "一键日常"
        self.description = "收菜"
        self.default_config.update({
            '体力本': "军备解析",
            '活动情报补给': False,
            '活动自律': True,
            '公共区/调度室': True,
            '购买免费礼包': True,
            '购买调度商店': False,
            '自动刷体力': True,
            '刷钱本': False,
            '竞技场': True,
            '兵棋推演': False,
            '班组': True,
            '尘烟': True,
            '领任务': True,
            '大月卡': True,
            '邮件': True,
        })
        self.stamina_options = ['军备解析', '深度搜索', '决策构象', '突击', '冲锋',
                                '狙击', '手枪']
        self.config_type["体力本"] = {'type': "drop_down",
                                      'options': self.stamina_options}
        self.add_exit_after_config()
        # self.add_text_fix()

    def run(self):
        self.ensure_main(recheck_time=2, time_out=90)
        if self.config.get('活动情报补给'):
            self.activity_stamina()
        if self.config.get('活动自律'):
            self.activity()
        if self.config.get('公共区/调度室'):
            self.gongongqu()
        if self.config.get('购买免费礼包'):
            self.shopping()
        if self.config.get('自动刷体力'):
            self.battle()
        if self.config.get('竞技场'):
            self.arena()
        if self.config.get('兵棋推演'):
            self.bingqi()
        if self.config.get('班组'):
            self.guild()
        if self.config.get('领任务'):
            self.claim_quest()
        if self.config.get('大月卡'):
            self.xunlu()
        if self.config.get('邮件'):
            self.mail()
        self.log_info('少前2日常完成!', notify=True)

    def activity_stamina(self):
        self.info_set('current_task', 'activity_stamina')
        self.wait_click_ocr(match=['活动'], box='bottom_right', after_sleep=0.5, raise_if_not_found=True)
        if self.wait_click_ocr(match=['情报补给'], box='left', time_out=3,
                               raise_if_not_found=False, after_sleep=1):
            while self.wait_click_ocr(match=['领取'], box='bottom_right', time_out=3,
                                      raise_if_not_found=False, after_sleep=1):
                self.wait_pop_up(time_out=6)
        self.ensure_main()

    def claim_quest(self):
        self.info_set('current_task', 'claim_quest')
        self.wait_click_ocr(match=['委托'], box='bottom_right', after_sleep=0.5, raise_if_not_found=True)
        self.wait_click_ocr(match=['一键领取', '领取全部'], box='bottom_right', time_out=3,
                            raise_if_not_found=False, after_sleep=2)
        results = self.ocr(match=['领取全部', '无可领取报酬', '已全部领取'], box='bottom_left')
        if len(results) == 0:
            results = self.ocr(match=['领取全部', '无可领取报酬', '已全部领取'], box='left')
            # if results and results[0].name == '一键领取':
        if results[0].name == '领取全部':
            self.click(results[0])
            self.wait_pop_up(time_out=4)
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
        self.info_set('current_task', 'activity')
        if self.wait_click_ocr(match=re.compile('限时开启'), box='top_right', after_sleep=0.5, raise_if_not_found=False,
                               time_out=4):
            if latest_activity := self.find_latest_activity():
                self.click(latest_activity)
                to_clicks=None
                if to_clicks := self.wait_ocr(match=["战术补给·下篇","战术补给·上篇"], box='right',
                                             raise_if_not_found=False, time_out=4, settle_time=2, log=True):
                    to_clicks2= None
                    for click in to_clicks:
                        if "下篇" in click.name:
                            self.click(click)
                            break
                        else:
                            to_clicks2= click
                    if to_clicks2:
                        self.sleep(1)
                        self.click(to_clicks2)
                elif to_clicks := self.wait_ocr(match=['活动战役', re.compile('物资')], box='bottom',
                                                raise_if_not_found=False, time_out=4, settle_time=2, log=True):
                    self.click(to_clicks, after_sleep=2)
                if to_clicks:
                    if wuzi := self.ocr(match=re.compile('物资'), box='bottom_right'):
                        self.click(wuzi, after_sleep=0.5)
                    battles = self.wait_ocr(match=map_re, time_out=4)
                    if battles:
                        self.click(battles[-1])
                        self.fast_combat(6, default_cost=1)
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
        self.info_set('current_task', 'public area')
        if self.wait_click_ocr(match=['公共区'], box='right', after_sleep=0.5, raise_if_not_found=False):
            self.wait_click_ocr(match=['调度室'], box='left', settle_time=0.5, after_sleep=0.5, raise_if_not_found=True)
            self.wait_click_ocr(match=['调度收益'], box='bottom', after_sleep=0.5, raise_if_not_found=True)
            self.wait_click_ocr(match=['取出'], box='bottom', after_sleep=0.5, raise_if_not_found=True)
            self.wait_click_ocr(match=['资源生产'], box='left', after_sleep=0.5, raise_if_not_found=True)
            self.wait_click_ocr(match=['收取'], box='bottom', after_sleep=0.5, raise_if_not_found=True)
            self.wait_pop_up(count=1)
            self.back()
            self.sleep(1)
            if self.wait_click_ocr(match=['一键领取', '领取全部'], settle_time=0.5, box='bottom_right', after_sleep=1,
                                   time_out=5):
                self.wait_click_ocr(match=['再次派遣'], box='bottom', after_sleep=1, raise_if_not_found=False)
        else:
            self.wait_click_ocr(match=['委托'], box='right', after_sleep=0.5, raise_if_not_found=True)
            self.sleep(1)
            self.click(0.184, 0.524)
            self.sleep(1)
            self.wait_click_ocr(match=['确认'], after_sleep=0.5, raise_if_not_found=True)
            self.sleep(1)
            self.click(0.042, 0.541)
            self.sleep(1)
            self.click(0.184, 0.583)
            self.sleep(1)
            self.click(0.042, 0.541)
            self.sleep(1)
            self.click(0.184, 0.643)
            self.wait_click_ocr(match=['再次派遣'], box='bottom', after_sleep=1, raise_if_not_found=False)
        self.back()
        self.ensure_main()

    def shopping(self):
        self.info_set('current_task', 'shopping')
        self.wait_click_ocr(match=['商城'], box='bottom_right', after_sleep=1.5, raise_if_not_found=True)
        self.wait_click_ocr(match=['品质甄选'], box='top_left', after_sleep=1, raise_if_not_found=True)
        self.wait_click_ocr(match=['周期礼包', '常驻礼包'], box='top', after_sleep=1, raise_if_not_found=True)
        if self.wait_click_ocr(match=['免费'], after_sleep=0.5, raise_if_not_found=False, time_out=1):
            self.log_info('found free item to buy')
            self.wait_click_ocr(match=['确认', '购买'], box='bottom', after_sleep=1.5, raise_if_not_found=True)
            self.wait_pop_up(time_out=5, count=1)
        self.wait_click_ocr(match=['限时礼包'], box='top', after_sleep=0.5, raise_if_not_found=True)
        if self.wait_click_ocr(match=['免费'], after_sleep=0.5, raise_if_not_found=False, time_out=1):
            self.log_info('found free item to buy')
            if self.wait_click_ocr(match=['确认', '购买'], box='bottom', after_sleep=1.5, raise_if_not_found=True):
                self.back()
        if self.config.get('购买调度商店'):
            self.buy_diaodu()
        self.ensure_main()

    def buy_diaodu(self):
        self.info_set('current_task', '调度商店')
        self.wait_click_ocr(match=['易物所'], box='left', after_sleep=0.5, raise_if_not_found=True)
        self.wait_click_ocr(match=['调度商店'], after_sleep=1, raise_if_not_found=True)
        while True:
            buy = self.ocr(match=re.compile(r"周限购[1-9]\d*"))
            if not buy:
                return
            self.click(buy[0], after_sleep=0.5)
            max = self.ocr(match="最大", box="bottom_right")
            if max:
                self.click(max[0], after_sleep=0.5)
            self.wait_click_ocr(match="购买", box="bottom_right", time_out=1, raise_if_not_found=True)
            if self.wait_ocr(match=re.compile(r"派遣记录不足")):
                break
            self.wait_pop_up(time_out=5, count=1)

    def arena(self):
        self.info_set('current_task', 'arena')
        self.wait_click_ocr(match=re.compile('战役推进'), box='top_right', after_sleep=1, raise_if_not_found=True)
        self.wait_ocr(match=re.compile('补给作战'), box='top_right', raise_if_not_found=True)
        self.sleep(1)
        self.click_relative(0.89, 0.05)  # 模拟战斗
        self.wait_click_ocr(match=['实兵演习'], box='bottom', after_sleep=0.5, raise_if_not_found=True)
        self.wait_pop_up(time_out=15)
        remaining_count = self.arena_remaining()
        count = 0
        if remaining_count > 1:
            self.wait_click_ocr_with_pop_up("进攻", box='bottom_right')
            self.sleep(2)
            count = self.challenge_arena_opponent()
            self.back()
            self.sleep(1)
        # if count > 0:
        #     self.click_relative(0.34 if self.is_adb() else 0.26, 0.89, after_sleep=0.5)
        #     if not self.wait_ocr(match=['演习补给'], box='top', time_out=4):
        #         self.wait_pop_up(time_out=4)
        self.ensure_main()

    def bingqi(self):
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
        priority = ['可露凯', '妮基塔', '莱娅', '绛雨', '玛绮朵', '琼玖', '托洛洛', 'jiangyu', 'klukai', 'leva',
                    'nikketa', 'Makiatto', 'qiongjiu', 'tololo']
        chars = self.ocr(0.18, 0.27, 0.82, 0.79, match=re.compile(r'^\D*$'))
        my_chars = []
        sorted_chars = sort_characters_by_priority(chars, priority)
        for char in sorted_chars:
            if char.name in my_chars:
                continue
            self.click(char, after_sleep=1)
            join = self.ocr(match='入队', box='bottom_right')
            if join:
                self.click_box(join, after_sleep=1)
                if self.ocr(box='bottom_right', match="确认"):
                    my_chars.append(char.name)
                    self.back(after_sleep=1)
                    self.log_info(f'duplicate char {my_chars}')
                else:
                    break
        self.wait_click_ocr(match='确定', box='bottom_right')
        self.auto_battle('开始作战', 'bottom_right')

    def wait_click_ocr_with_pop_up(self, match, box=None):
        if self.wait_until(lambda: self.do_wait_pop_up_and_click(match, box), time_out=10, raise_if_not_found=True):
            self.sleep(0.5)
            return True

    def do_wait_pop_up_and_click(self, match, box):
        boxes = self.ocr()
        if find_boxes_by_name(boxes, pop_ups):
            self.back(after_sleep=2)
            return False
        elif click := find_boxes_by_name(boxes, match):
            if click := find_boxes_within_boundary(click, self.get_box_by_name(box)):
                self.click(click)
                return True

    def wait_ocr_with_possible_pop_up(self, match, box=None, raise_if_not_found=True,
                                      time_out=30):
        if self.wait_until(lambda: self.do_wait_pop_up_and_click(match, box), time_out=time_out,
                           raise_if_not_found=raise_if_not_found):
            self.sleep(0.5)
            return True

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
            remaining = self.fast_combat(battle_max=4)
            self.back(after_sleep=1)
        target = self.config.get('体力本')
        min_stamina = 10 if self.stamina_options.index(target) < 2 else 20
        if remaining >= min_stamina:
            ding_xiang = self.stamina_options.index(target) >= 3
            if ding_xiang:
                target = '定向精研'
            self.wait_click_ocr(match=target, settle_time=1, after_sleep=0.5, raise_if_not_found=True, log=True)
            if ding_xiang:
                self.wait_click_ocr(match=re.compile(self.config.get('体力本')),
                                    box=self.box_of_screen(0.01, 0.21, 0.73, 0.31),
                                    settle_time=0.5,
                                    after_sleep=0.5, log=True,
                                    raise_if_not_found=True)
            while remaining >= min_stamina:
                if ding_xiang:
                    remaining = self.fast_combat(plus_x=0.69, plus_y=0.59)
                else:
                    remaining = self.fast_combat()
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

    for i, the_char in enumerate(chars):  # Use enumerate to get the original index
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
