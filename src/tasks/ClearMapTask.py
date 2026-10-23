from ok import Logger

from src.core.BaseGfTask import BaseGfTask, map_re
from src.data.FeatureList import FeatureList as fL
from src.tasks.map_recognition import MapRecognizer, extract_map_name, stable_map_names

logger = Logger.get_logger(__name__)


class ClearMapTask(BaseGfTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "推图"
        self.description = "从要推的图的最左边开始"
        self._map_recognizer = MapRecognizer()

    def find_map_names(self):
        boxes = self._map_recognizer.recognize(self.frame)
        self.draw_boxes("map_names", boxes, color="green")
        self.log_debug(f"关卡编号: {boxes}")
        return boxes

    def wait_stable_map_names(self):
        previous = None

        def stable():
            nonlocal previous
            self.sleep(0.15)
            if self.frame is None:
                previous = None
                return None
            current = self.find_map_names()
            if previous is not None and stable_map_names(previous, current, 8 / 1920 * self.width):
                # 空列表也必须连续确认，不能将识别抖动误判为推图结束。
                return (current,)
            previous = current
            return None

        result = self.wait_until(stable, time_out=5)
        if result is None:
            raise RuntimeError("关卡页面仍在移动或编号识别不稳定，请等待地图静止后重试")
        return result[0]

    def find_map_by_name(self, name):
        canonical = extract_map_name(name)
        if canonical is None:
            return []
        return [box for box in self.find_map_names() if box.name == canonical]

    def find_boxes(self, boxes, match=None, boundary=None):
        # auto_battle / skip_dialogs 的地图结束判定也走同一套高分辨率识别。
        patterns = match if isinstance(match, list) else [match]
        if not any(pattern is map_re for pattern in patterns):
            return super().find_boxes(boxes, match=match, boundary=boundary)
        other_patterns = [pattern for pattern in patterns if pattern is not map_re]
        result = super().find_boxes(boxes, match=other_patterns, boundary=boundary) if other_patterns else []
        if result:
            return result
        return super().find_boxes(self.find_map_names(), boundary=boundary)

    def run(self):
        count = 0
        clicked = []
        last_fallback_name = None
        last_failed_name = None  # 用来保存上次进入 if not text 分支的关卡名
        last_failed_flag = False  # 标记上次循环是否进入过 if not text 分支
        map_ocr_box = self.box_of_screen(x=0, y=100 / 1080, to_x=1.0, to_y=980 / 1080)

        while True:
            last_clicked = None
            self.sleep(2)
            # 先确认地图静止，再按完整编号重试或枚举关卡。
            self.next_frame()
            maps = self.wait_stable_map_names()
            map_name_groups = []
            if last_failed_flag and last_failed_name:
                canonical = extract_map_name(last_failed_name)
                maps = [box for box in maps if canonical is not None and box.name == canonical]

                if maps:
                    maps = [maps[0]]  # 只保留第一个，避免重复点击
                    maps[0].name = "before_one_" + maps[0].name
                    maps[0].x = max(0, int(maps[0].x - 80 / 256 * self.width))
                    map_name_groups = [{maps[0].name}]
                else:
                    map_name_groups = []
                last_failed_flag = False
            else:
                maps.extend(self.find_feature(feature_name=fL.not_clear_one, box=map_ocr_box))
                now_icon_y_offset = 0.489 - 0.380
                now_icon = [self.wait_feature(feature=fL.now_icon, box=map_ocr_box, time_out=1)]
                if now_icon[0]:
                    for i in range(len(now_icon)):
                        now_icon[i].y = int(now_icon[i].y + now_icon_y_offset * self.height)
                else:
                    now_icon = []

                maps.extend(now_icon)
                maps, map_name_groups = merge_maps(
                    maps, x_threshold=40 / 1920 * self.width, y_threshold=40 / 1080 * self.height
                )

            # 关卡框和名称组必须一起排序，否则已点击判定会关联到另一个关卡。
            ordered = sorted(zip(maps, map_name_groups, strict=True), key=lambda item: item[0].x)
            maps = [box for box, _ in ordered]
            map_name_groups = [names for _, names in ordered]
            self.log_debug(f"maps: {maps}")

            if len(maps) == 0:
                if count == 0:
                    raise Exception("未找到要推的图!")
                else:
                    self.log_info(f"推图完成, 共{count}个!", notify=True)
                    return

            checked = False
            current_map = None
            for i, current_map in enumerate(maps):
                name_group = map_name_groups[i]

                # 特殊特征永远允许点击
                if fL.not_clear_one in name_group or fL.now_icon in name_group:
                    checked = True
                    last_clicked = current_map
                    self.click(current_map, after_sleep=2)
                    break

                if not any(name in clicked for name in name_group):
                    clicked.extend(name_group)
                    checked = True
                    last_clicked = current_map
                    self.click(current_map, after_sleep=2)
                    break

            if not checked:
                # 当前兜底目标
                fallback = maps[-1]
                if last_fallback_name == fallback.name:
                    self.log_info(f"推图完成, 共{count}个!", notify=True)
                    return
                last_fallback_name = fallback.name
                self.click(fallback, after_sleep=2)
                self.back(after_sleep=2)
                continue

            self.sleep(1)
            if boxes := self.wait_ocr(box="right", match=["特殊奖励", "观看", "挑战"], time_out=3, log=True):
                if self.find_boxes(boxes, match=["特殊奖励"]):
                    text = self.find_boxes(boxes, match=["观看", "挑战"])
                    if not text:
                        # 保存当前失败的关卡名，标记上次进入过该分支
                        last_failed_name = current_map.name
                        last_failed_flag = True
                        clicked = [name for name in clicked if name not in name_group]
                        self.back(after_sleep=2)
                        continue

                    # 正常处理挑战或观看
                    self.click(text, after_sleep=2)
                    count += 1
                    if text[0].name == "挑战":
                        self.auto_battle(end_match=map_re, has_dialog=True)
                    else:
                        self.skip_dialogs(end_match=map_re)

                    if last_clicked:
                        self.log_debug(f"重新点击上一次关卡: {last_clicked.name}")
                        if boxes := self.wait_until(
                            lambda name=last_clicked.name: self.find_map_by_name(name), time_out=3
                        ):
                            self.click(boxes, after_sleep=1)
                            self.back(after_sleep=2)
                else:
                    self.back(after_sleep=2)
            self.sleep(1)


def merge_maps(maps, x_threshold=40, y_threshold=40):
    merged = []  # 存最终的 map 对象
    merged_names = []  # 存每个合并组的所有 name

    for m in maps:
        for i, exist in enumerate(merged):
            if abs(m.x - exist.x) < x_threshold and abs(m.y - exist.y) < y_threshold:
                # 坐标取平均
                exist.x = int((exist.x + m.x) / 2)
                exist.y = int((exist.y + m.y) / 2)
                # 将当前 map 的名字加入该组
                merged_names[i].add(m.name)
                break
        else:
            merged.append(m)
            merged_names.append({m.name})  # 新组，名字放入 set

    return merged, merged_names
