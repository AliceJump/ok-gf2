"""战斗与班组：体力本、竞技场、兵棋推演、班组尘烟。"""

import re
from src.tasks.BaseGfTask import BaseGfTask, pop_ups, stamina_re, map_re, parse_time_option


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


class DailyBattleMixin:
    def battle(self):
        if self.config.get('自主循环'):
            self.ensure_main()
            return
        self.info_set('current_task', 'battle')
        self.wait_click_ocr(match=re.compile('战役推进'), box=self.box.top_right, after_sleep=0.5,
                            raise_if_not_found=True)
        self.wait_ocr(match=re.compile('补给作战'), box=self.box.top_right, raise_if_not_found=True)
        self.click_relative(0.78, 0.05)
        if self.is_adb():
            self.swipe_relative(0.8, 0.6, 0.5, 0.6, duration=1)
        self.sleep(1)
        remaining = 10000
        if self.config.get('刷钱本'):
            self.wait_click_ocr(match=['标准同调'], box=self.box.right, after_sleep=0.5, raise_if_not_found=True)
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

    def arena(self):
        if self.config.get('自主循环'):
            self.ensure_main()
            return
        self.info_set('current_task', 'arena')
        self.wait_click_ocr(match=re.compile('战役推进'), box=self.box.top_right, after_sleep=1,
                            raise_if_not_found=True)
        self.wait_ocr(match=re.compile('补给作战'), box=self.box.top_right, raise_if_not_found=True)
        self.sleep(1)
        self.click_relative(0.89, 0.05)  # 模拟战斗
        self.wait_click_ocr(match=['实兵演习'], box=self.box.bottom, after_sleep=0.5, raise_if_not_found=True)
        self.wait_pop_up(time_out=15, count=1)
        remaining_count = self.arena_remaining()
        if remaining_count > 1:
            self.wait_click_ocr_with_pop_up("进攻", box=self.box.bottom_right)
            self.sleep(2)
            self.challenge_arena_opponent()
            self.back()
            self.sleep(1)
        # if count > 0:
        #     self.click_relative(0.34 if self.is_adb() else 0.26, 0.89, after_sleep=0.5)
        #     if not self.wait_ocr(match=['演习补给'], box=self.box.top, time_out=4):
        #         self.wait_pop_up(time_out=4)
        if self.wait_click_ocr(match=['周期奖励'], box=self.box.left, after_sleep=1, raise_if_not_found=True):
            self.wait_click_ocr(match=[re.compile('键领取')], after_sleep=1, raise_if_not_found=False)
        self.ensure_main()

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
                        self.wait_click_ocr(match=['进攻'], box=self.box.bottom_right, after_sleep=0.5,
                                            raise_if_not_found=True)
                        self.auto_battle(end_match='刷新')
                        self.sleep(3)
                        challenged += 1
                        continue
            if self.ocr(match=['刷新消耗'], box=self.box.bottom_right):
                self.log_info(f'no refresh count remains')
                return challenged
            self.wait_click_ocr(match='刷新', box=self.box.bottom_right, after_sleep=2, raise_if_not_found=True)
        return challenged

    def bingqi(self):
        if self.config.get('自主循环'):
            self.ensure_main()
            return
        self.info_set('current_task', 'bingqi')
        self.wait_click_ocr(match=re.compile('战役推进'), box=self.box.top_right, after_sleep=1,
                            raise_if_not_found=True)
        self.wait_ocr(match=re.compile('补给作战'), box=self.box.top_right, raise_if_not_found=True)
        self.sleep(1)
        self.click_relative(0.90, 0.05, after_sleep=0.95)  # 补给
        self.click_relative(0.98, 0.49, after_sleep=0.52)
        self.wait_ocr(match='防御阵容', box=self.box.right, time_out=30,
                      post_action=lambda: self.click_relative(0.5, 0.5, after_sleep=2))
        while self.find_top_right_count():
            self.info_incr('bingqi')
            self.wait_click_ocr(match=['匹配'], box=self.box.bottom, after_sleep=0.5, raise_if_not_found=True)
            self.auto_battle(end_match='匹配')
            self.sleep(2)
        self.ensure_main()

    def guild(self):
        self.info_set('current_task', 'guild')
        if result := self.wait_ocr(match=['班组'], box=self.box._group, raise_if_not_found=True):
            self.click_box_by_match_position(result, "班组", after_sleep=2)
            self.wait_click_ocr(match=['要务'], box=self.box.bottom_right, after_sleep=0.5, settle_time=2)
            result = self.wait_ocr(match=['开始作战', '每日要务已完成'], box=self.box.bottom_right, raise_if_not_found=True, log=True)
            if result[0].name == '开始作战':
                self.click(result)
                self.auto_battle()
                self.wait_ocr(match=['开始作战', '每日要务已完成', '要务'], box=self.box.bottom_right,
                              raise_if_not_found=True)
            else:
                self.log_info('每日要务已完成')
            self.back()
            self.sleep(1)
            self.chenyan()

            self.wait_click_ocr(match=['补给'], box=self.box.bottom_right, after_sleep=0.5)
            if result := self.wait_ocr(match=['领取全部'], box=self.box.bottom_right, time_out=4,
                                       raise_if_not_found=False):
                self.click_box(result)
                self.wait_pop_up(count=1)
            self.back()
            self.sleep(1)
        self.ensure_main()

    def chenyan(self):
        if not self.config.get('尘烟'):
            return
        end = self.ocr(match=re.compile('前线'), box=self.box.bottom_right, log=True)
        if not end:
            return
        self.click(end, after_sleep=1)
        result = self.ocr(0.89, 0.01, 0.99, 0.1, match=stamina_re, box=self.box.top_right)
        if not result:
            return
        while True:
            tickets = int(result[0].name.split('/')[0])
            self.log_info(f'chenyan tickets {tickets}')
            self.info_set('chenyan tickets', tickets)
            if tickets == 0:
                break
            self.wait_click_ocr(match='攻坚战', box=self.box.top_right, after_sleep=0.5, raise_if_not_found=True)
            self.wait_click_ocr(match='开始作战', box=self.box.bottom_right, after_sleep=2, raise_if_not_found=True)
            self.choose_chenyan(tickets)
            self.sleep(2)
            result = self.ocr(0.89, 0.01, 0.99, 0.1, match=stamina_re, box=self.box.top_right)
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

        self.wait_click_ocr(match='助战', box=self.box.bottom_right, settle_time=1, after_sleep=1,
                            raise_if_not_found=True)
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

            join = self.ocr(match='入队', box=self.box.bottom_right)
            if not join:
                continue

            self.click_box(join, after_sleep=1)

            if self.ocr(box=self.box.bottom_right, match="确认"):
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

                    join = self.ocr(match='入队', box=self.box.bottom_right)
                    if not join:
                        continue

                    self.click_box(join, after_sleep=1)

                    if self.ocr(box=self.box.bottom_right, match="确认"):
                        my_chars.append(char.name)
                        self.back(after_sleep=1)
                        self.log_info(f'duplicate char {char.name}')
                    else:
                        self.log_info(f'fallback joined char: {char.name}')
                        selected = True
                        break

                if selected:
                    break

        self.wait_click_ocr(match='确定', box=self.box.bottom_right)
        self.auto_battle('开始作战', self.box.bottom_right)
