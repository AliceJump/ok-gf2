"""推图专用的关卡编号识别，不改动框架共用的 OCR 引擎。"""

import re
import unicodedata

import cv2
from ok import Box

from src.image.frame_processs import isolate_by_hsv_ranges
from src.image.hsv_config import HSVRange

_DASHES = str.maketrans("－—–−", "----")
_MAP_TOKEN = re.compile(r"(?<![A-Z0-9-])(?:[A-Z]{1,2}\s*-?\s*)?\d{1,2}\s*-\s*\d{1,2}(?![A-Z0-9-])")


def extract_map_name(text):
    """剥离星级等装饰；保留普通章节、单字母难度与活动双字母前缀。"""
    text = unicodedata.normalize("NFKC", text or "").upper().translate(_DASHES)
    text = re.sub(r"\s*-\s*", "-", text)
    matches = _MAP_TOKEN.findall(text)
    if len(matches) != 1:
        return None
    name = re.sub(r"\s+", "", matches[0])
    # OCR 偶尔漏掉前缀后的连字符，统一成相同身份，避免重复点击。
    return re.sub(r"^([A-Z]{1,2})(\d)", r"\1-\2", name)


def same_map_location(first, second, tolerance=12):
    """包含星级的大框与仅包含编号的小框也应合并到同一关卡。"""
    if abs(first.y + first.height / 2 - second.y - second.height / 2) > tolerance:
        return False
    overlap = min(first.x + first.width, second.x + second.width) - max(first.x, second.x)
    return overlap > min(first.width, second.width) / 2


def stable_map_names(previous, current, tolerance):
    """两个画面的编号和位置需一一对应，才允许使用当前坐标。"""
    if len(previous) != len(current):
        return False
    unmatched = list(previous)
    for box in current:
        index = next(
            (
                i
                for i, old in enumerate(unmatched)
                if old.name == box.name
                and abs(old.x + old.width / 2 - box.x - box.width / 2) <= tolerance
                and abs(old.y + old.height / 2 - box.y - box.height / 2) <= tolerance
            ),
            None,
        )
        if index is None:
            return False
        del unmatched[index]
    return True


class MapRecognizer:
    def __init__(self, engine=None):
        self._engine = engine

    def prepare(self):
        """提前加载识别模型，使初始化耗时不占用页面稳定等待时间。"""
        return self.engine

    @property
    def engine(self):
        if self._engine is None:
            from onnxocr.onnx_paddleocr import ONNXPaddleOcr

            # 独立 CPU 引擎，避免 NPU 静态输入再次把小字压缩到 640。
            self._engine = ONNXPaddleOcr(use_angle_cls=False, use_openvino=True, use_npu=False, det_limit_side_len=1920)
        return self._engine

    def recognize(self, frame):
        if frame is None or frame.size == 0:
            return []
        height, width = frame.shape[:2]
        top, bottom = round(height * 100 / 1080), round(height * 980 / 1080)
        image = frame[top:bottom]
        # 720p 放大、2K/4K 缩小到同一文字尺度，返回前再换回真实屏幕坐标。
        scale = 1920 / width
        if width != 1920:
            image = cv2.resize(image, (1920, round(image.shape[0] * scale)), interpolation=cv2.INTER_CUBIC)

        raw = self.engine.ocr(image, cls=False)[0] or []
        candidates = self._boxes(raw, scale, top, threshold=0.7)
        # 低分辨率放大后可能整块漏检，不能只用已识别文字的置信度决定是否补识别。
        needs_fallback = (
            width < 1920
            or not candidates
            or any(
                (extract_map_name(text) is not None and confidence < 0.9)
                or (extract_map_name(text) is None and re.search(r"\d\s*[-－—–−]\s*\d", text))
                for _, (text, confidence) in raw
            )
        )
        if needs_fallback:
            filtered = isolate_by_hsv_ranges(image, HSVRange.WHITE_GRAY)
            fallback = self.engine.ocr(filtered, cls=False)[0] or []
            for box in self._boxes(fallback, scale, top, threshold=0.9):
                # 原图读到的完整编号优先，避免过滤后 SA-1-12 变成 SA-1-1。
                if not any(same_map_location(box, primary, 12 / scale) for primary in candidates):
                    candidates.append(box)

        merged = []
        for box in candidates:
            if not any(same_map_location(box, existing, 12 / scale) for existing in merged):
                merged.append(box)
        return sorted(merged, key=lambda box: (box.x, box.y))

    @staticmethod
    def _boxes(results, scale, top, threshold):
        boxes = []
        for polygon, (text, confidence) in results:
            name = extract_map_name(text)
            if name is None or confidence < threshold:
                continue
            xs, ys = zip(*polygon, strict=True)
            left, right = min(xs) / scale, max(xs) / scale
            upper, lower = min(ys) / scale + top, max(ys) / scale + top
            if right > left and lower > upper:
                boxes.append(Box(left, upper, to_x=right, to_y=lower, confidence=confidence, name=name))
        return boxes
