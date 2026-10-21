"""
调试工具：给 okctl 远程调试用的小动作，点一个 OCR 文字、按几次 ESC / 按键、或抓一张带 OCR 框的截图。
不做任何游戏逻辑判断，只按配置执行一次。
"""

import re

from src.core.BaseGfTask import BaseGfTask


class DebugTask(BaseGfTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "调试工具"
        self.description = "按配置点一个文字 / 按 ESC / 截图，供远程调试用"
        self.default_config.update(
            {
                "先回主页": False,
                "点击文字": "",
                "点击坐标": "",
                "按ESC次数": 0,
                "按键": "",
                "截图并OCR": False,
            }
        )
        self.config_description.update(
            {
                "先回主页": "先执行 ensure_main 回到游戏主页再做后面的动作",
                "点击文字": "非空时用 OCR 找到这个文字并点击（支持正则），找不到就报错",
                "点击坐标": "非空时点击这个相对坐标，格式 x,y（0~1），如 0.3,0.5",
                "按ESC次数": "点击之后再按几次 ESC",
                "按键": "最后按这些键，逗号分隔，键:秒 表示按住多久，如 f2 或 w:1.5,e",
                "截图并OCR": "把当前画面全部 OCR 一遍，文字写进日志，截图存到 screenshots/调试工具/",
            }
        )

    def run(self):
        if self.config.get("先回主页"):
            self.ensure_main()
        text = (self.config.get("点击文字") or "").strip()
        if text:
            box = self.wait_ocr(match=re.compile(text), time_out=5, raise_if_not_found=False)
            if not box:
                raise Exception(f"没找到文字: {text}")
            self.log_info(f"点击 {box[0].name} at {box[0].center()}", notify=True)
            self.click(box, after_sleep=1.5)
        coord = (self.config.get("点击坐标") or "").strip()
        if coord:
            x, y = (float(v) for v in coord.split(","))
            self.log_info(f"点击相对坐标 ({x}, {y})", notify=True)
            self.click_relative(x, y, after_sleep=1.5)
        for _ in range(int(self.config.get("按ESC次数") or 0)):
            self.back(after_sleep=1.5)
        for item in (self.config.get("按键") or "").split(","):
            key, _, hold = item.strip().partition(":")
            if key:
                self.log_info(f"按键 {key} {hold or 0.1}s", notify=True)
                self.send_key(key, down_time=float(hold or 0.1), after_sleep=1.5)
        if self.config.get("截图并OCR"):
            self.next_frame()
            boxes = self.ocr()
            self.log_info(f"OCR: {[(b.name, int(b.x), int(b.y)) for b in boxes]}", notify=False)
            self.debug_shot("ocr", boxes)
