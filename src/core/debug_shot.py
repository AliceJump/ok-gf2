"""调试截图：按任务名/日期分目录保存 JPEG，带框标注，自动轮转，不影响 ok-script 自带的 screenshots 清理。

目录结构：screenshots/<任务名>/<YYYY-MM-DD>/<HH-MM-SS.mmm>_<标签>.jpg
每个任务目录最多保留 ``max_files`` 张（默认 400），超出按时间删除最旧的。
"""

from __future__ import annotations

import contextlib
import os
import re
import threading
from datetime import datetime

import cv2
from PIL import Image, ImageDraw, ImageFont

_lock = threading.Lock()
_font = None
_FILENAME_BAD_CHARS = re.compile(r'[\\/*?:"<>|]')
DEFAULT_ROOT = "screenshots"
DEFAULT_MAX_FILES = 400
DEFAULT_QUALITY = 80


def sanitize(name: str) -> str:
    return _FILENAME_BAD_CHARS.sub("_", str(name)).strip() or "unnamed"


def _get_font():
    global _font
    if _font is not None:
        return _font
    fonts_dir = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
    for candidate in ("msyh.ttc", "msyh.ttf", "simhei.ttf", "simsun.ttc", "arial.ttf"):
        path = os.path.join(fonts_dir, candidate)
        if os.path.exists(path):
            try:
                _font = ImageFont.truetype(path, 22)
                return _font
            except Exception:
                continue
    try:
        _font = ImageFont.load_default(22)
    except Exception:
        _font = ImageFont.load_default()
    return _font


def _draw_boxes(pil_image, boxes, color=(255, 60, 60)):
    draw = ImageDraw.Draw(pil_image)
    font = _get_font()
    for box in boxes or []:
        try:
            x, y, w, h = int(box.x), int(box.y), int(box.width), int(box.height)
        except Exception:
            continue
        if w <= 0 or h <= 0:
            continue
        draw.rectangle([x, y, x + w, y + h], outline=color, width=2)
        text = str(getattr(box, "name", "") or "")
        confidence = getattr(box, "confidence", 0) or 0
        if 0 < confidence < 1:
            text += f"_{round(confidence * 100)}"
        if text:
            draw.text((x, y + h + 2), text, fill=color, font=font, stroke_width=1, stroke_fill="black")


def _rotate(task_dir: str, max_files: int):
    files = []
    for dirpath, _, filenames in os.walk(task_dir):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                files.append((os.path.getmtime(fp), fp))
            except OSError:
                continue
    if len(files) <= max_files:
        return
    files.sort()
    for _, fp in files[: len(files) - max_files]:
        with contextlib.suppress(OSError):
            os.remove(fp)
    # 清理空的日期目录
    for dirpath, dirnames, filenames in os.walk(task_dir, topdown=False):
        if dirpath != task_dir and not dirnames and not filenames:
            with contextlib.suppress(OSError):
                os.rmdir(dirpath)


def save_debug_shot(
    frame,
    task_name: str,
    tag: str,
    boxes=None,
    root: str = DEFAULT_ROOT,
    max_files: int = DEFAULT_MAX_FILES,
    quality: int = DEFAULT_QUALITY,
):
    """保存一张调试截图，返回文件路径；frame 为 None 时返回 None。任何异常由调用方兜底。"""
    if frame is None:
        return None
    now = datetime.now()
    task_dir = os.path.join(root, sanitize(task_name))
    day_dir = os.path.join(task_dir, now.strftime("%Y-%m-%d"))
    filename = f"{now.strftime('%H-%M-%S')}.{now.microsecond // 1000:03d}_{sanitize(tag)}.jpg"
    path = os.path.join(day_dir, filename)

    image = frame
    if len(image.shape) == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    pil_image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    if boxes:
        _draw_boxes(pil_image, boxes)

    with _lock:
        os.makedirs(day_dir, exist_ok=True)
        pil_image.save(path, format="JPEG", quality=quality)
        _rotate(task_dir, max_files)
    return path
