import re
from ok import Logger
from src.tasks.BaseGfTask import BaseGfTask, map_re
from src.image.hsv_config import HSVRange as hR
logger = Logger.get_logger(__name__)


class ClearMapTask(BaseGfTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "推图"
        self.description = "从要推的图的最左边开始"
        self.default_config.update({
            '普通OCR': True,
            '除杂色OCR1': True,
            '除杂色OCR2': True,
        })
        self.config_description.update({
            '普通OCR': (
                '普通OCR：不做任何图像预处理，直接识别关卡名称\n'
                '适用场景：背景和关卡卡片颜色与白色差异明显，文字清晰可辨'
            ),
            '除杂色OCR1': (
                '除杂色OCR1（标准白色）：过滤掉非纯白色区域后再识别\n'
                '适用场景：关卡卡片文字为标准白色，背景较复杂干扰识别'
            ),
            '除杂色OCR2': (
                '除杂色OCR2（宽松白灰色）：同时保留白色与浅灰色区域后再识别\n'
                '适用场景：关卡卡片文字为白色或浅灰色，或普通OCR/除杂色OCR1均无法识别时'
            ),
        })

    def run(self):
        count = 0
        clicked = []
        last_fallback_name = None
        last_failed_name = None  # 用来保存上次进入 if not text 分支的关卡名
        last_failed_flag = False  # 标记上次循环是否进入过 if not text 分支
        map_ocr_box = self.box_of_screen(x=0, y=323 / 1080, to_x=1.0, to_y=727 / 1080)

        # 根据用户配置动态组合要使用的帧处理器，保持顺序：普通OCR → 除杂色OCR1 → 除杂色OCR2
        # 至少保留一个，若全部关闭则回退到全部开启
        processors = []
        if self.config.get('普通OCR', True):
            processors.append(None)  # None 表示不做预处理，直接识别
        if self.config.get('除杂色OCR1', True):
            processors.append(self.make_hsv_isolator(hR.WHITE))  # 标准白色过滤
        if self.config.get('除杂色OCR2', True):
            processors.append(self.make_hsv_isolator(hR.WHITE_GRAY))  # 宽松白灰色过滤
        if not processors:
            processors = [None, self.make_hsv_isolator(hR.WHITE), self.make_hsv_isolator(hR.WHITE_GRAY)]

        while True:
            last_clicked = None
            self.sleep(2)
            # 根据上次是否失败，选择 OCR 匹配规则
            self.next_frame()
            map_name_groups = []
            if last_failed_flag and last_failed_name:

                maps = []
                pattern = re.compile(re.escape(last_failed_name))

                for p in processors:
                    maps = self.ocr(box=map_ocr_box, match=pattern, log=True, frame_processor=p)
                    if maps:
                        break

                if maps:
                    maps=[maps[0]]  # 只保留第一个，避免重复点击
                    maps[0].name = "before_one_" + maps[0].name
                    maps[0].x = int(maps[0].x - 80 / 256 * self.width)  # 往左扩展一些识别区域，增加找到的概率
                    map_name_groups = [{maps[0].name}]
                else:
                    map_name_groups = []
                last_failed_flag = False
            else:

                maps = []
                for p in processors:
                    maps.extend(self.ocr(box=map_ocr_box, match=map_re, log=True, frame_processor=p))

                maps,map_name_groups  = merge_maps(maps, x_threshold=40/1920*self.width, y_threshold=40/1080*self.height)

            maps = sorted(maps, key=lambda obj: obj.x)
            self.log_debug('maps: {}'.format(maps))

            if len(maps) == 0:
                if count == 0:
                    raise Exception('未找到要推的图!')
                else:
                    self.log_info(f'推图完成, 共{count}个!', notify=True)
                    return

            checked = False
            current_map = None
            for i, current_map in enumerate(maps):
                # 找到对应的名字组
                name_group = map_name_groups[i]  # map_name_groups 和 maps 是一一对应的
                # 判断这个组的所有名字是否已经点击过
                if not any(name in clicked for name in name_group):
                    # 全部加入 clicked
                    clicked.extend(name_group)
                    checked = True
                    last_clicked = current_map
                    self.click(current_map, after_sleep=2)
                    break

            if not checked:
                # 当前兜底目标
                fallback = maps[-1]
                if last_fallback_name == fallback.name:
                    self.log_info(f'推图完成, 共{count}个!', notify=True)
                    return
                last_fallback_name = fallback.name
                self.click(fallback, after_sleep=2)
                self.back(after_sleep=2)
                continue

            self.sleep(1)
            if boxes := self.wait_ocr(box="right", match=["特殊奖励", '观看', '挑战'], time_out=3, log=True):
                if self.find_boxes(boxes, match=["特殊奖励"]):
                    text = self.find_boxes(boxes, match=['观看', '挑战'])
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
                    if text[0].name == '挑战':
                        self.auto_battle(end_match=map_re, has_dialog=True)
                    else:
                        self.skip_dialogs(end_match=map_re)

                    if last_clicked:
                        self.log_debug(f'重新点击上一次关卡: {last_clicked.name}')
                        if self.wait_click_ocr(match=last_clicked.name, time_out=3, log=True, after_sleep=1):
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
