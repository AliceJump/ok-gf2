"""限时活动相关：活动自律（物资关卡）、活动层（喝水/吃饭/领奖）、活动列表识别。"""

import re
from src.core.BaseGfTask import map_re, parse_time_option
from src.tasks.daily.daily_common_mixin import (
    chapter_suffix_re,
    up_chapter_re,
    middle_chapter_re,
    down_chapter_re,
)


activity_time_re = re.compile(r'^(\d+)\s*(?:天|days?)\s*(\d+)\s*(?:小时|hours?)', re.I)


class DailyActivityMixin:
    def activities(self):
        self.info_set('current_task', 'activity_stamina')
        self.wait_click_ocr(match=['活动'], box=self.box._activities, after_sleep=0.5, raise_if_not_found=True)
        reward_activities = ['情报补给', '战前补给']
        for reward_activity in reward_activities:
            if self.wait_click_ocr(match=reward_activity, box=self.box.left, time_out=3, raise_if_not_found=False):
                while self.wait_click_ocr(match=['领取'], box=self.box.right, time_out=3,
                                        raise_if_not_found=False,
                                        after_sleep=0.2):
                    self.wait_pop_up(time_out=6, count=1)
        self.ensure_main()

    def free_time_layer(self):
        self.info_set('current_task', 'free_time_layer')
        completed = True
        for i in range(2):
            self.wait_click_ocr(match='活动层', box=self.box.right, time_out=2, raise_if_not_found=True)
            if self.is_free_layer():
                if i == 0:
                    drink_entered = self.do_food_flow(
                        enter_func=self.go_drink,
                        entry_match=re.compile('茶歇一刻'),
                        main_btn='制作',
                        second_btn='确认',
                        skip_end_match=['饮品加成'],
                        need_extra_confirm=False
                    )
                    if drink_entered is False:
                        self.log_warning('未找到茶歇一刻入口，角色可能被挡住，请检查「喝水」按键时长，参考 1.087-1.0-0.8')

                else:
                    self.do_food_flow(
                        enter_func=self.go_eat,
                        entry_match=re.compile('美味烹调'),
                        main_btn='下一步',
                        second_btn='确认邀请',
                        skip_end_match=['前往战役'],
                        need_extra_confirm=True,
                        need_again_test=True
                    )
            else:
                self.log_error('没检测到活动层页面')
                completed = False
            self.ensure_main(time_out=60)
        if self.config.get('活动层浇花', True):
            self.wait_click_ocr(match='活动层', box=self.box.right, time_out=2, raise_if_not_found=True)
            if self.is_free_layer():
                completed = self.water_flowers() and completed
            else:
                self.log_error('没检测到活动层页面，跳过浇花')
                completed = False
            self.ensure_main(time_out=60)
        return completed

    def _ensure_activity_panel(self):
        panel_match = re.compile(
            r'逸\s*趣\s*事\s*件|宜\s*居\s*值|栽\s*培|生\s*长\s*阶\s*段|浇\s*灌')
        panel_box = self.box_of_screen(0.13, 0.16, 0.87, 0.82)

        def is_open(timeout):
            return bool(self.wait_ocr(match=panel_match, box=panel_box,
                                      time_out=timeout, raise_if_not_found=False, log=True))

        # 已打开时不要再次按 F2，以免把面板关闭。
        if is_open(1):
            self.log_info('活动层面板已打开')
            return True
        for attempt in range(2):
            self.log_info(f'尝试打开活动层面板：发送 F2（第 {attempt + 1}/2 次）')
            self.send_key('f2', down_time=0.15, after_sleep=1)
            if is_open(4):
                self.log_info('已确认 F2 面板打开')
                return True
        self.log_info('F2 后未检测到面板，尝试点击顶部 F2 入口')
        if self.wait_click_ocr(match=re.compile(r'^F\s*2$'),
                               box=self.box_of_screen(0.65, 0, 0.74, 0.12),
                               time_out=2, raise_if_not_found=False, after_sleep=1, log=True):
            if is_open(4):
                self.log_info('点击入口后已确认活动层面板打开')
                return True
        self.log_error('活动层 F2 面板未打开：按键重试及入口点击未成功，跳过浇花')
        return False

    def water_flowers(self):
        self.info_set('current_task', 'water_flowers')
        if not self._ensure_activity_panel():
            return False
        watering_match = re.compile(r'浇\s*灌')
        # F2 可能直接选中栽培页；优先识别内容，避免依赖选中页签的黑字。
        on_watering_page = self.wait_ocr(match=watering_match, box=self.box.right,
                                         time_out=2, raise_if_not_found=False)
        on_overview = False
        if not on_watering_page:
            on_overview = self.wait_ocr(match=re.compile(r'栽\s*培\s*天\s*数|生\s*长\s*阶\s*段'),
                                        box=self.box_of_screen(0.36, 0.43, 0.85, 0.59),
                                        time_out=2, raise_if_not_found=False, log=True)
        if on_overview:
            self.log_info('F2 已打开栽培概览，直接前往浇灌')
        if not on_watering_page and not on_overview:
            # 未进入栽培页时才切换页签，允许文字前带图标。
            if not self.wait_click_ocr(match=re.compile(r'栽\s*培'),
                                       box=self.box_of_screen(0.30, 0.15, 0.42, 0.25),
                                       time_out=10, raise_if_not_found=False, after_sleep=2, log=True):
                self.log_error('未找到栽培入口，跳过浇花')
                return False
        if not self.wait_ocr(match=watering_match, box=self.box.right, time_out=3,
                             raise_if_not_found=False):
            # 部分界面先显示栽培概览，需点击“前往”才进入花盆页面。
            if not self.wait_click_ocr(match=re.compile('前往'), box=self.box.bottom_right,
                                       time_out=5, raise_if_not_found=False, after_sleep=3, log=True):
                self.log_error('栽培页面未找到浇灌或前往入口')
                return False
        if not self.wait_ocr(match=watering_match, box=self.box.right, time_out=10,
                             raise_if_not_found=False):
            self.log_error('未进入浇灌页面，跳过浇花')
            return False
        # 仅检查浇灌按钮下方次数，避免把施肥的 1/1 当成浇水完成。
        count_box = self.box_of_screen(0.75, 0.51, 0.87, 0.59)
        done_match = re.compile(r'^\s*1\s*[/／]\s*1\s*$')
        if self.wait_ocr(match=done_match, box=count_box, time_out=1, raise_if_not_found=False):
            self.log_info('今日已浇灌，跳过重复浇花')
            self.back(after_sleep=2)
            return True
        if not self.wait_click_ocr(match=watering_match, box=self.box.right, time_out=5,
                                   raise_if_not_found=False, after_sleep=2, log=True):
            self.log_error('未找到浇灌按钮，跳过浇花')
            return False
        self.wait_pop_up(count=1, time_out=5)
        completed = bool(self.wait_ocr(match=done_match, box=count_box, time_out=10,
                                       raise_if_not_found=False, log=True))
        if not completed:
            self.log_error('点击浇灌后未检测到次数 1/1，浇花未确认完成')
        # 关闭栽培页面后，由活动层共用的 ensure_main 处理退出确认。
        self.back(after_sleep=2)
        return completed

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
            if self.wait_click_ocr(match=main_btn, box=self.box.bottom_right, time_out=10):
                if self.wait_click_ocr(match=second_btn, time_out=3, after_sleep=2):
                    if need_extra_confirm:
                        self.wait_click_ocr(match='确认', time_out=3, after_sleep=1)
                    self.skip_dialogs(end_match=skip_end_match, time_out=60)
                    self.wait_click_ocr(match="确认", time_out=3, box = self.box.bottom, after_sleep=1)
                    self.wait_pop_up(count=1)
                return True
            else:
                if need_again_test and attempt == 0:
                    continue
                else:
                    self.back(after_sleep=2)
                    return False
        return False

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

    def activity(self):
        activity_wuzi_names = [name.strip() for name in str(self.config.get('当前物资关卡名称')).split("-")]
        self.info_set('current_task', 'activity')
        if to_activity_page := self.wait_click_ocr(match=['限时开启'], box=self.box.top_right, after_sleep=2,
                                                   raise_if_not_found=False,
                                                   time_out=4):
            if activities := self.wait_ocr(match=['开启中'], box=self.box.bottom_left, time_out=4):
                activity_count = 0
                for activity in activities:
                    self.ensure_main()
                    self.click(to_activity_page, after_sleep=2)
                    self.click(activity)
                    if activity_count >= len(activity_wuzi_names):
                        activity_count -= 1
                    name_re = activity_wuzi_names[activity_count]
                    chapter_re = re.compile(rf"{re.escape(name_re)}[·・：]{chapter_suffix_re}")
                    to_clicks = self.wait_ocr_until_count(
                        match=[chapter_re],
                        box=None,
                        min_count=2,
                        timeout=5,
                        settle_time=2,
                        log=True
                    )
                    if to_clicks:
                        up = None
                        middle = None
                        down = None
                        for click in to_clicks:
                            if up_chapter_re.search(click.name):
                                up = click
                            elif middle_chapter_re.search(click.name):
                                middle = click
                            elif down_chapter_re.search(click.name):
                                down = click

                        chapter_boxes = [box for box in (up, middle, down) if box]
                        wuzi_boxes = self.wait_ocr(
                            match=re.compile('物资'), box=None, time_out=4, settle_time=2, log=True
                        )
                        click_boxes = self._filter_boxes_near_candidates(chapter_boxes, wuzi_boxes) if wuzi_boxes else []

                        if not click_boxes:
                            click_boxes = chapter_boxes

                        click_boxes = sorted(click_boxes, key=self._chapter_click_order)

                        for chapter in click_boxes:
                            self.click(chapter, after_sleep=0.2)
                    elif to_clicks := self.wait_ocr(match=['活动战役', re.compile('物资')], box=self.box.bottom,
                                                    raise_if_not_found=False, time_out=4, settle_time=2, log=True):
                        self.click(to_clicks, after_sleep=2)
                    if to_clicks:
                        self.sleep(2)
                        if wu_zi := self.ocr(match=re.compile('物资'), box=self.box.bottom_right):
                            self.click(wu_zi, after_sleep=0.5)
                        battles = self.wait_ocr(match=map_re, time_out=4)
                        if battles:
                            self.click(battles[-1])
                            self.fast_combat(set_cost=1, battle_max=6, activity=True)
            else:
                self.log_info("找不到开启的活动")
        self.ensure_main()

    def find_activities(self):
        return self.wait_ocr(match=[activity_time_re], box=self.box.bottom_left,
                             raise_if_not_found=False, time_out=4)

    def find_latest_activity(self):
        boxs = self.find_activities()

        def parse_time(name):
            match = activity_time_re.match(name)
            if match:
                days = int(match.group(1))
                hours = int(match.group(2))
                return days * 24 + hours
            return 0

        if not boxs:
            return None
        longest = max(boxs, key=lambda b: parse_time(b.name))
        return longest
