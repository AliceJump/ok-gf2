"""日常任务的通用工具：OCR 轮询、弹窗兜底、候选框筛选。"""

import re
import time
from ok import Logger, find_boxes_by_name, Box
from src.core.BaseGfTask import BaseGfTask, pop_ups, stamina_re, map_re, parse_time_option


# 活动章节后缀："筒"是"篇"的 OCR 常见误读。
# 部分活动用等价命名：初篇 = 上篇，转篇 = 下篇。
chapter_suffix_re = r'[上下中初转][篇筒]'
up_chapter_re = re.compile(r'(?:上|初)[篇筒]')
middle_chapter_re = re.compile(r'中[篇筒]')
down_chapter_re = re.compile(r'(?:下|转)[篇筒]')


def find_boxes_within_boundary(
        boxes: list["Box"],
        boundary_box: "Box",
        sort: bool = False
) -> list["Box"]:
    """
    查找完全包含在边界框内的框。
    """

    if not boxes or not boundary_box:
        return []

    # 计算边界框四个边
    bx1 = boundary_box.x
    by1 = boundary_box.y
    bx2 = boundary_box.x + boundary_box.width
    by2 = boundary_box.y + boundary_box.height

    result = []

    for box in boxes:
        x1 = box.x
        y1 = box.y
        x2 = box.x + box.width
        y2 = box.y + box.height

        # 完全包含判断
        if x1 >= bx1 and y1 >= by1 and x2 <= bx2 and y2 <= by2:
            result.append(box)

    if sort:
        # 从上到下，再从左到右
        result.sort(key=lambda b: (b.y, b.x))

    return result


class DailyCommonMixin:
    def wait_ocr_until_count(self, match, box=None, min_count=2, timeout=5, interval=0.5, **kwargs):
        """
        固定时间内循环OCR，检测到对象数>=min_count立即返回，否则超时。
        """
        start_time = time.time()
        while True:
            results = self.wait_ocr(match=match, box=box, raise_if_not_found=False, time_out=interval, **kwargs)
            if results and len(results) >= min_count:
                return results
            if time.time() - start_time >= timeout:
                return results  # 可能为None或不足min_count

    def confirm_auto_battle_up(self):
        """
        确认启用游戏内的全局自动战斗
        如果未启用，抛出异常提醒用户
        """
        raise Exception(
            "请先确认启用游戏内的全局自动战斗(设置->其他->自动战斗设置),"
            "然后勾选本软件内一键日常内的确认项"
        )

    def _box_center_ratio(self, box):
        return (
            (box.x + box.width / 2) / self.width,
            (box.y + box.height / 2) / self.height,
        )

    def _filter_boxes_near_candidates(
            self, row_boxes, candidate_boxes, max_x_distance=0.15, max_y_distance=0.06
    ):
        filtered = []
        for row_box in row_boxes:
            row_x, row_y = self._box_center_ratio(row_box)
            for candidate in candidate_boxes:
                candidate_x, candidate_y = self._box_center_ratio(candidate)
                x_distance = abs(row_x - candidate_x)
                y_distance = abs(row_y - candidate_y)
                if x_distance <= max_x_distance and y_distance <= max_y_distance:
                    filtered.append(row_box)
                    break

        return filtered

    def _chapter_click_order(self, box):
        if down_chapter_re.search(box.name):
            return 0
        if middle_chapter_re.search(box.name):
            return 1
        if up_chapter_re.search(box.name):
            return 2
        return 3

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
