import re
import threading
import time
from typing import Union, List

from ok import BaseTask, find_boxes_by_name, Box, Logger
from src.image.frame_processs import isolate_by_hsv_ranges
from functools import partial
from src.image.hsv_config import HSVRange as hR
from src.data.FeatureList import FeatureList as fL
from src.interaction.ScreenPosition import ScreenPosition

logger = Logger.get_logger(__name__)
pop_ups = ['点击空白处关闭', '点击屏幕任意位置继续', '点击任意位置继续', '新周期开启']
number_re = re.compile(r"^\d+$")
stamina_re = re.compile(r"^\d+/\d+")
map_re = re.compile(r"^.{0,2}\s*-?\s*\d{1,2}\s*-\s*\d{1,2}\s*\*?$")


def parse_time_option(option: str) -> list[float]:
    """
    将配置中的时间字符串解析为浮点数列表
    例如 "1.087-1.4-0.5" -> [1.087, 1.4, 0.5]
    """
    return [float(x) for x in option.split('-')]


class BaseGfTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.roles_dict = {
            "物理": ["夏安", "莱妮", "威玛西娜", "巴希达", "幼熙", "绯", "波波沙", "乌尔丽德", "莉塔拉", "黛烟",
                     "维普蕾", "闪电"],
            "燃烧": ["罗蕾莱", "樱花", "刘易斯", "秋桦", "佩莉", "维克托", "桑朵莱希", "科谢尼娅", "琼玖", "奇塔",
                     "夏克里", "克罗丽科"],
            "电导": ["莱娅", "安朵丝", "比悠卡", "绛雨", "莱娜", "莫辛纳甘"],
            "冷凝": ["海伦", "埃芙", "洛贝拉", "杜莎妮", "索米", "洛塔", "玛绮朵"],
            "浊刻": ["芙洛伦", "妮基塔", "春田", "朝晖", "塞布丽娜", "托洛洛", "寇尔芙"],
            "酸蚀": ["翡图萨", "哈卜茜", "琳德", "米什缇", "可露凯", "纳甘", "佩里缇亚", "纳美西丝"]
        }
        self.box = ScreenPosition(self)
        self.default_config_group = {}

    def isolate_by_hsv_ranges(self, frame, ranges, invert=True, kernel_size=2):
        """
        :param frame: 输入图像（BGR）
        :param ranges: HSV 区间列表
        :param invert: 是否反转结果
        :param kernel_size: 形态学核大小

        作用：按 HSV 范围提取颜色区域。
        """
        return isolate_by_hsv_ranges(frame, ranges, invert, kernel_size)

    def make_hsv_isolator(self, ranges):
        """
        :param ranges: HSV 区间列表

        作用：生成固定 HSV 范围的图像处理函数。
        """
        return partial(self.isolate_by_hsv_ranges, ranges=ranges)

    def get_role_by_name(self, name):
        return next((k for k, v in self.roles_dict.items() if name in v), None)

    def ensure_main(self, recheck_time=1, time_out=30, esc=True):
        self.info_set('current_task', 'go_to_main')
        if not self.wait_until(lambda: self.is_main(recheck_time=recheck_time, esc=esc),
                               time_out=time_out):
            raise Exception("请从游戏主页进入")

    def skip_dialogs(self, end_match, end_box=None, time_out=120, has_dialog=True, raise_if_not_found=True):
        self.info_set('current_task', 'skip_dialogs')
        start = time.time()
        while time.time() - start < time_out:
            try:
                boxes = self.ocr()
            except AttributeError:
                self.log_info('WGC 抓帧返回空帧，等待 3s 后重试', notify=False)
                self.sleep(3)
                self.next_frame()
                continue
            if skip := self.find_boxes(boxes, match=['跳过']):
                self.click(skip, after_sleep=2)
            elif no_alert := self.find_boxes(boxes, match='今日不再提示'):
                self.click(no_alert)
                self.sleep(0.2)
                self.click(self.find_boxes(boxes, match='确认'), after_sleep=2)
            elif result := self.find_boxes(boxes, match=end_match, boundary=end_box):
                # 优先返回"继续前进"
                for r in result:
                    if r.name == '继续前进':
                        self.sleep(1)
                        return [r]
                self.sleep(1)
                return result
            elif self.find_boxes(boxes, match=pop_ups):
                self.back()
                self.sleep(1)
            else:
                if has_dialog:
                    self.click_relative(0.95, 0.04)
                self.sleep(2)
            self.next_frame()
        if raise_if_not_found:
            raise Exception('跳过剧情超时!')

    def auto_battle(self, end_match=None, end_box=None, has_dialog=False, need_click_auto=False,
                    has_dialog_behind_start=False):
        self.info_set('current_task', 'auto battle')
        result = self.skip_dialogs(end_match=['作战开始', '行动结束', '继续前进'], end_box=self.box.bottom, time_out=120,
                                   has_dialog=has_dialog, raise_if_not_found=False)
        if result and result[0].name == '继续前进':
            self.log_info('开局检测到继续前进，点击后开启新一轮自动战斗', notify=True)
            self.click_box(result, after_sleep=2)
            self.auto_battle(end_match=end_match, end_box=end_box, has_dialog=has_dialog,
                             need_click_auto=need_click_auto, has_dialog_behind_start=has_dialog_behind_start)
            return
        if result[0].name == '作战开始':
            self.sleep(2)
            self.click_box(result, after_sleep=1)
            start_result = self.skip_dialogs(end_match=[re.compile('行动完成'), re.compile('行动结束'), re.compile('还有可部署'), re.compile('任务完成'), re.compile('继续前进')],
                                         has_dialog=True, time_out=45, raise_if_not_found=False)
            if start_result and '继续前进' in start_result[0].name:
                self.log_info('开局后检测到继续前进，点击后开启新一轮自动战斗', notify=True)
                self.click_box(start_result, after_sleep=2)
                self.auto_battle(end_match=end_match, end_box=end_box, has_dialog=has_dialog,
                                 need_click_auto=need_click_auto, has_dialog_behind_start=has_dialog_behind_start)
                return
            ok_bool = bool(start_result) and (not ("还有可部署" in start_result[0].name or "行动结束" in start_result[0].name))
            if not ok_bool:
                if start_result and ('还有可部署' in start_result[0].name):
                    self.log_info('阵容没上满!', notify=True)

                    self.wait_click_ocr(match=['确认'], box=self.box.bottom, time_out=5,
                                        raise_if_not_found=True)
                    self.wait_ocr(match=['行动结束'], box=self.box.bottom_right,
                                  raise_if_not_found=False, time_out=15)
                    # start_result = self.wait_ocr(match=['行动结束'], box=self.box.bottom_right,
                    #                              raise_if_not_found=False, time_out=15)
                if not start_result and has_dialog_behind_start:
                    start_result = self.skip_dialogs(end_match=['作战开始', '行动结束', '继续前进'], end_box=self.box.bottom,
                                                     time_out=120,
                                                     has_dialog=has_dialog, raise_if_not_found=False)
                    if start_result and start_result[0].name == '继续前进':
                        self.log_info('开局二次检测到继续前进，点击后开启新一轮自动战斗', notify=True)
                        self.click_box(start_result, after_sleep=2)
                        self.auto_battle(end_match=end_match, end_box=end_box, has_dialog=has_dialog,
                                         need_click_auto=need_click_auto, has_dialog_behind_start=has_dialog_behind_start)
                        return
                    if self.wait_ocr(match='注意', box=self.box.top):
                        self.wait_click_ocr(match='取消', after_sleep=2)
                if start_result and need_click_auto:
                    self.sleep(0.5)
                    if self.is_adb():
                        self.click_relative(0.85, 0.05, after_sleep=1)
                    else:
                        self.click_relative(0.88, 0.04, after_sleep=1)

        clicked_continue = False
        while results := self.skip_dialogs(
                end_match=['任务完成', '任务失败', '战斗失败', '对战胜利', '对战失败', '确认', '确认结算', '继续前进'],
                time_out=900,
                has_dialog=has_dialog):
            # 优先遍历所有结果找"继续前进"
            clicked = False
            for result in results:
                if result.name == '继续前进':
                    self.click_box(result, after_sleep=2)
                    clicked = True
                    clicked_continue = True
                    break
            if not clicked:
                for result in results:
                    if result.name in ("确认", "确认结算"):
                        self.click_box(result, after_sleep=2)
                        clicked = True
                        break
            self.sleep(2)
            self.click_box(results, after_sleep=2)
            if results[0].name not in pop_ups:
                break
        if not results:
            raise Exception('自动战斗异常')
        if results[0].name == '任务失败':
            raise Exception('任务失败, 没打过!')
        if clicked_continue:
            self.log_info('检测到继续前进，点击后开启新一轮自动战斗', notify=True)
            self.auto_battle(end_match=end_match, end_box=end_box, has_dialog=has_dialog,
                             need_click_auto=need_click_auto, has_dialog_behind_start=has_dialog_behind_start)
            return
        if self.wait_click_ocr(match='继续前进', box=self.box.bottom_right, raise_if_not_found=False, time_out=3):
            self.log_info('结算后检测到继续前进，点击后开启新一轮自动战斗', notify=True)
            self.auto_battle(end_match=end_match, end_box=end_box, has_dialog=has_dialog,
                             need_click_auto=need_click_auto, has_dialog_behind_start=has_dialog_behind_start)
            return
        while self.wait_click_ocr(match='确认', box=self.box.bottom_right, raise_if_not_found=False, time_out=3):
            pass
        if end_match:
            if isinstance(end_match, list):
                end_match = end_match + pop_ups
            else:
                end_match = [end_match] + pop_ups
            end_match.append('确认')
            end_match.append('确认结算')
            end_match.append('继续前进')
            while True:
                match = self.skip_dialogs(end_match=end_match, end_box=end_box,
                                          time_out=30, has_dialog=has_dialog,
                                          raise_if_not_found=True)
                if match[0].name in pop_ups:
                    self.back(after_sleep=2)
                    continue
                if match[0].name == '继续前进':
                    self.log_info('最后阶段检测到继续前进，点击后开启新一轮自动战斗', notify=True)
                    self.click_box(match, after_sleep=2)
                    self.auto_battle(end_match=end_match, end_box=end_box, has_dialog=has_dialog,
                                     need_click_auto=need_click_auto, has_dialog_behind_start=has_dialog_behind_start)
                    return
                if match[0].name in ("确认", "确认结算"):
                    self.click_box(match, after_sleep=8)
                break
        self.sleep(2)

    def is_main(self, recheck_time=0.0, esc=True):
        boxes = self.ocr(match=['整备室', '公共区', '活动层', re.compile('招募')], box='right', log=True)
        feature_boxes = []
        for feature in [fL.dog_icon, fL.message_icon]:
            if result := self.find_one(feature, vertical_variance=0.002, horizontal_variance=0.002):
                feature_boxes.append(result)
        total = len(boxes) + len(feature_boxes)
        self.log_info(f'is main ocr={len(boxes)} features={len(feature_boxes)} total={total}')
        if total >= 2:
            return True
        # if not self.do_handle_alert()[0]:
        if self.ocr(match=re.compile('^是否离开活动层'), log=True):
            self.wait_click_ocr(match='确认', after_sleep=2)
        if box := self.ocr(box=self.box.bottom, match=["点击开始", "点击空白处关闭", "取消"],
                           log=True):
            self.click(box, after_sleep=2)
            return False
        if esc:
            self.back(after_sleep=2)
        self.next_frame()
        return None

    def click(self, x: Union[float, Box, List[Box]] = 0.0, y: Union[float, int] = 0.0, move_back=False, name=None,
              interval=-1, move=True,
              down_time=0.01, after_sleep=0, key="left"):
        frame = self.frame
        super().click(x, y, move_back=move_back, name=name, move=move, down_time=0.04, after_sleep=after_sleep,
                      interval=interval, key=key)
        if self.debug:
            self.screenshot('click', frame=frame)

    def back(self, after_sleep=0):
        frame = self.frame
        self.send_key('esc', down_time=0.04, after_sleep=after_sleep)
        if self.debug:
            self.screenshot('back', frame=frame)

    def free_layer_click(self, x=0, y=0, move_back=False, name=None, interval=-1, move=True,
                         down_time=0.01, after_sleep=0, key="left"):
        frame = self.frame
        self.send_key_down('alt')
        self.click(x, y, move_back=move_back, name=name, move=move, down_time=down_time, after_sleep=after_sleep,
                   interval=interval, key=key)
        self.send_key_up('alt')
        if self.debug:
            self.screenshot('free_layer_click', frame=frame)

    def click_with_key(self, hold_key, result, delay1=1, delay2=0.5, after_sleep=0):
        def start_task1():
            self.send_key(key=hold_key, down_time=delay1)

        def start_task2():
            time.sleep(delay2)  # 控制任务2启动延迟
            self.click(result)

        t1 = threading.Thread(target=start_task1)
        t2 = threading.Thread(target=start_task2)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        self.sleep(after_sleep)

    def find_top_right_count(self):
        result = self.ocr(0.89, 0.01, 0.99, 0.1, match=re.compile(r"^\d+/\d+$"), box='top_right')
        if not result:
            raise Exception('找不到当前体力或票')
        return int(result[0].name.split('/')[0])

    def find_cost(self, boxes=None, default=30):
        boundary = self.box_of_screen(0.48, 0.56, 0.57, 0.7)
        if not boxes:
            boxes = self.ocr(box=boundary)

        if costs := self.find_boxes(boxes, match=number_re, boundary=boundary):
            cost = int(costs[0].name)
        else:
            cost = default
        return cost

    def out_free_layer(self):
        self.info_set('current_task', 'out_free_layer')
        while not self.wait_click_ocr(match=['确认'], time_out=2):
            self.back()
            self.sleep(2)

    def is_free_layer(self, time_out=20, every_time=1):
        max_count = int(time_out / every_time)

        for _ in range(max_count):
            result = self.wait_ocr(
                match=['Esc', 'P', 'M', 'F1', 'F2', 'F3', 'F4'],
                settle_time=every_time,
                box=self.box.top,
                time_out=0
            )

            if result and len(result) >= 5:
                return True

        return False

    def break_if_not_enough(self):
        if self.wait_ocr(match=re.compile('坍塌晶条'), time_out=2, log=True):
            self.wait_click_ocr(match=['取消'], after_sleep=2, time_out=2, raise_if_not_found=True)
            return True
        return False

    def back_if_not_ocr_match(self, match, box=None, max_back_count=1, raise_if_not_found=False):
        for count in range(max_back_count + 1):
            temp_raise_if_not_found = False
            if count == max_back_count:
                temp_raise_if_not_found = True
            if self.wait_ocr(match=match, box=box, raise_if_not_found=temp_raise_if_not_found):
                return
            else:
                self.back(after_sleep=2)
        return

    def fast_combat(self, *, set_cost, battle_max=10, plus_x=0.616, plus_y=0.52, click_all=False,
                    activity=False):
        if activity:
            click_all = True
        if click_all:
            plus_x = 0.65
            plus_y = 0.52
            self.wait_click_ocr(match=['自律'], box=self.box.bottom_right, after_sleep=2, raise_if_not_found=True)
            if self.break_if_not_enough():
                self.wait_ocr(match=['自律'], box=self.box.bottom_right, raise_if_not_found=True)
                return 0
            self.click(plus_x, plus_y)
            self.wait_click_ocr(match=["确认"], after_sleep=1, raise_if_not_found=False)
            if not self.wait_click_ocr(match=["取消"], time_out=2, raise_if_not_found=False):   
                self.wait_pop_up(count=1)
            self.back_if_not_ocr_match(match=['自律'], box=self.box.bottom_right, raise_if_not_found=True)
            return 0

        self.wait_click_ocr(match=['自律'], box=self.box.bottom_right, after_sleep=2, raise_if_not_found=True)
        if self.break_if_not_enough():
            self.wait_ocr(match=['自律'], box=self.box.bottom_right, raise_if_not_found=True)
            return 0
        boxes = self.ocr(log=True, threshold=0.8, frame_processor=self.make_hsv_isolator(hR.WHITE))
        if next_step := self.find_boxes(boxes, '下一步', self.box.bottom_right):
            self.click(next_step, after_sleep=1)
            boxes = self.ocr(log=True, threshold=0.8, frame_processor=self.make_hsv_isolator(hR.WHITE))
            # default_cost = 30
        current = self.ocr(match=[stamina_re, number_re], box=self.box_of_screen(0.84, 0, 0.99, 0.10))
        if current:
            current = int(current[0].name.split('/')[0])
        else:
            current = 1
        self.sleep(1)
        if len(find_boxes_by_name(boxes, ["确认", "取消", "上一步"])) != 2 and len(
                find_boxes_by_name(boxes, ["确认", "取消", "上", "一步"])) != 3:
            if self.debug:
                self.screenshot('fast_no_zilv')
            self.log_info("自律没有弹窗, 可能是调度权限不足")
            return current
        cost = set_cost
        # if set_cost:
        #     cost = set_cost
        # else:
        #     cost = self.find_cost(boxes, default=default_cost)

        self.info_set('current_stamina', current)
        self.info_set('battle_cost', cost)
        self.info_set('battle_max', battle_max)
        can_fast_count = min(int(current / cost), battle_max)
        self.info_set('can_fast_count', can_fast_count)
        self.info_set('click_battle_plus', 0)
        self.log_info(f'battle cost: {cost} current_stamina: {current} can_fast_count: {can_fast_count}')

        for _ in range(can_fast_count - 1):
            self.click(plus_x, plus_y)
            self.info_incr('click_battle_plus')
            self.sleep(0.2)
        self.sleep(1)
        remaining = current - can_fast_count * cost
        self.info_set('remaining_stamina', remaining)
        if can_fast_count <= 0:
            self.click(find_boxes_by_name(boxes, "取消"))
            return remaining

        self.click(find_boxes_by_name(boxes, "确认"), after_sleep=2)

        if self.click(find_boxes_by_name(boxes, "前往"), after_sleep=2):
            if self.enter_fast_disassemble():
                self.fast_disassemble_loop(stamina_re)

            self.click(find_boxes_by_name(boxes, "确认"), after_sleep=2)

        self.wait_pop_up(count=1)
        self.wait_ocr(match=['自律'], box=self.box.bottom_right, raise_if_not_found=True)

        return remaining

    def click_box_by_match_position(self, box: Union[Box, list[Box]], match: Union[str, re.Pattern], after_sleep=None):
        if isinstance(box, list):
            box = box[0]
        text = box.name

        # 找匹配位置
        if isinstance(match, str):
            start = text.find(match)
            if start == -1:
                return self.click_box(box)
            end = start + len(match)

        else:  # regex
            m = match.search(text)
            if not m:
                return self.click_box(box)
            start = m.start()
            end = m.end()

        mid = (start + end) / 2
        ratio = mid / len(text)

        x = box.x
        y = box.y
        w = box.width
        h = min(box.height, int(30/1080 * self.height))  # 限制高度，避免匹配到下方的按钮

        click_y = y + h // 2

        if ratio < 0.33:
            click_x = x + h
        elif ratio > 0.66:
            click_x = x + w - h
        else:
            click_x = x + w // 2

        self.click(click_x, click_y, after_sleep=after_sleep)

    def fast_disassemble_loop(self, model_re):
        while self.wait_click_ocr(match=['快捷选择'], after_sleep=2):
            ocr_select_num = self.wait_ocr(
                match=re.compile(model_re),
                box=self.box.bottom_right
            )

            if not ocr_select_num:
                self.back(after_sleep=2)
                break

            self.wait_click_ocr(match=['拆解'], box=self.box.bottom_right, after_sleep=2)
            self.wait_pop_up(count=1)

    def enter_fast_disassemble(self):
        # 拆解入口是硬条件
        if not self.wait_click_ocr(match=['拆解'], box=self.box.top_right, after_sleep=2):
            return False

        # 以下是“尽力而为”的筛选条件
        self.wait_click_ocr(match=['工业级及以下未培养'], after_sleep=2)
        self.wait_click_ocr(match=['精密级及以下未培养'], after_sleep=2)

        return True

    def loop_click_ocr(self, match_list, box=None, pop_up_count=1, sleep_after_click=0.5):
        """
        循环点击 OCR 匹配元素，直到找不到为止。
        处理弹窗 pop_up_count。
        """
        if box is None:
            box = self.box.bottom_right
        while self.wait_click_ocr(match=match_list, box=box, raise_if_not_found=False, after_sleep=sleep_after_click):
            if pop_up_count:
                self.wait_pop_up(count=pop_up_count)

    def wait_pop_up(self, time_out=15, other=None, box=None, count=100):
        if box is None:
            box = self.box.bottom
        start = time.time()
        check = pop_ups.copy()
        if other:
            if isinstance(other, list):
                check += other
            else:
                check.append(other)
        found_count = 0
        while self.wait_ocr(match=pop_ups, box=box, settle_time=2, time_out=int(time_out - (time.time() - start)),
                            raise_if_not_found=False) and found_count < count:
            found_count += 1
            self.back(after_sleep=3)

    def press_keys_sequence(self, keys, times, sleep_between=0.5, sleep_after_last=False):
        """
        按顺序按下按键，每次按键后等待 sleep_between 秒，可选择最后一个按键后不等待。
        当按键持续时间为 0 时，不传 down_time 参数给 send_key。
        """
        for i, (key, t) in enumerate(zip(keys, times)):
            if t:  # t != 0
                self.send_key(key, down_time=t)
            else:  # t == 0
                self.send_key(key)
            if i < len(keys) - 1 or sleep_after_last:
                self.sleep(sleep_between)

    def run_steps_with_retry_and_rollback(self, steps):
        """
        执行带重试与回退机制的步骤序列。

        参数:
            steps: List[List[Callable, bool, bool]]
                每个元素为 [func, retry_on_fail, rollback_on_fail]
                - func: 无参可调用对象，成功返回 True，失败返回 False
                - retry_on_fail: 是否允许重试（最多尝试 2 次）
                - rollback_on_fail: 失败且未达重试上限时，是否回退到上一步

        返回:
            bool: 全部成功返回 True，中途失败返回 False
        """
        if not steps:
            return True

        retries = [0] * len(steps)
        i = 0

        while 0 <= i < len(steps):
            func, retry_on_fail, rollback_on_fail = steps[i]

            # 执行当前步骤
            try:
                success = func()
            except Exception as e:
                success = False

            if success:
                retries[i] = 0
                i += 1
                continue

            # === 处理失败 ===
            if retry_on_fail:
                retries[i] += 1
                if retries[i] >= 2:
                    return False
            else:
                return False

            # 决定是否回退
            if rollback_on_fail and i > 0:
                i -= 1
            # 否则：留在当前步，下一轮重试（因 i 未变）

        return True
    def kill_all_related_processes(self):
        """尝试杀死游戏进程和本软件自身进程（除当前进程外）"""
        import os, sys
        import win32process, win32gui, win32api, win32con
        import psutil

        # 1. 杀死游戏进程
        try:
            hwnd = getattr(self, "hwnd", None)
            if hwnd is not None:
                hwnd_val = getattr(hwnd, "hwnd", None)
                if hwnd_val:
                    tid, pid = win32process.GetWindowThreadProcessId(hwnd_val)
                    handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, False, pid)
                    win32api.TerminateProcess(handle, 0)
                    win32api.CloseHandle(handle)
                    self.log_info(f"已终止游戏进程 pid={pid}", notify=True)
                else:
                    self.log_info("未获取到 hwnd，无法终止游戏进程", notify=True)
            else:
                self.log_info("未获取到 hwnd 属性，无法终止游戏进程", notify=True)
        except Exception as e:
            self.log_info(f"终止游戏进程失败: {e}", notify=True)
        # 2. 杀死本软件所有同名进程（除当前进程）
        try:
            current_pid = os.getpid()
            exe_name = psutil.Process(current_pid).name()
            for proc in psutil.process_iter(["pid", "name"]):
                if proc.info["name"] == exe_name and proc.info["pid"] != current_pid:
                    try:
                        proc.kill()
                        self.log_info(f"已终止本软件进程 pid={proc.info['pid']}", notify=True)
                    except Exception as e2:
                        self.log_info(f"终止本软件进程失败: {e2}", notify=True)
        except Exception as e:
            self.log_info(f"查找/终止本软件进程失败: {e}", notify=True)
