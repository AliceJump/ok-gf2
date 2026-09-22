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
        for i in range(2):
            self.wait_click_ocr(match='活动层', box=self.box.right, time_out=2, raise_if_not_found=True)
            if self.is_free_layer():
                if i == 0:
                    self.do_food_flow(
                        enter_func=self.go_drink,
                        entry_match=re.compile('茶歇一刻'),
                        main_btn='制作',
                        second_btn='确认',
                        skip_end_match=['饮品加成'],
                        need_extra_confirm=False
                    )

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
            self.ensure_main(time_out=60)

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
