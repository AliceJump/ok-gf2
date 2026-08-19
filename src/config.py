import os

import numpy as np
from ok import Config

version = "dev"
# 不需要修改version, Github Action打包会自动修改

config = {
    "debug": False,  # Optional, default: False
    "use_gui": True,  # 目前只支持True
    "config_folder": "configs",  # 最好不要修改
    # "screenshot_processor": make_bottom_left_black,  # 在截图的时候对frame进行修改, 可选
    "gui_icon": "icon.png",  # 窗口图标, 最好不需要修改文件名
    "wait_until_before_delay": 0,
    "wait_until_check_delay": 0,
    "wait_until_settle_time": 0,  # 调用 wait_until时候, 在第一次满足条件的时候, 会等待再次检测, 以避免某些滑动动画没到预定位置就在动画路径中被检测到
    "ocr": {"lib": "onnxocr", "params": {"use_openvino": True}},  # 可选, 使用的OCR库
    "windows": {  # Windows游戏请填写此设置
        "exe": ["GF2_Exilium.exe"],  # 新版统一使用 list
        'hwnd_class': 'UnityWndClass',
        "interaction": "Genshin",  # 或 EfInteraction，根据项目
        "capture_method": ["WGC", "BitBlt_RenderFull"],
        # Windows版本支持的话, 优先使用WGC, 否则使用BitBlt_Full. 支持的capture有 BitBlt, WGC, BitBlt_RenderFull, DXGI
        "check_hdr": True,  # 当用户开启AutoHDR时候提示用户, 但不禁止使用
        "force_no_hdr": False,  # True=当用户开启AutoHDR时候禁止使用
        "require_bg": True,  # 要求使用后台截图
    },
    # 模板标签配置信息
    'template_tab': {
    # 是否生成标签枚举
        'generate_label_enum': True,
    # 标签枚举的相对路径
        'label_enum_relative_path': 'src/data/FeatureList',
    },
    "start_timeout": 60,  # default 60
    "window_size": {"width": 1200, "height": 800, "min_width": 600, "min_height": 450},  # ok-script窗口大小
    "supported_resolution": {
        # 'ratio': '16:9',  # 支持的游戏分辨率
        "min_size": (1280, 720),  # 支持的最低游戏分辨率
        # 'resize_to': [(2560, 1440), (1920, 1080), (1600, 900), (1280, 720)],  # 可选, 如果非16:9自动缩放为 resize_to
    },
    "links": {  # 关于里显示的链接, 可选
        "default": {
            "github": "https://github.com/alicejump/ok-gf2",
            "discord": "https://discord.gg/vVyCatEBgA",
            "sponsor": "https://www.paypal.com/ncp/payment/JWQBH7JZKNGCQ",
            "qq_group": "https://qm.qq.com/q/NcWHQU6q8k",
            "faq": "https://github.com/alicejump/ok-gf2",
        },
        "zh_CN": {
            "github": "https://github.com/alicejump/ok-gf2",
            "discord": "https://discord.gg/vVyCatEBgA",
            "sponsor": "https://afdian.com/a/ok-oldking",
        },
    },
    "screenshots_folder": "screenshots",  # 截图存放目录, 每次重新启动会清空目录
    "gui_title": "ok-gf2",  # 窗口名
    "template_matching": {  # 可选, 如使用OpenCV的模板匹配
        "coco_feature_json": os.path.join("assets", "coco_annotations.json"),
        # coco格式标记, 需要png图片, 在debug模式运行后, 会对进行切图仅保留被标记部分以减少图片大小
        "default_horizontal_variance": 0.002,  # 默认x偏移, 查找不传box的时候, 会根据coco坐标, match偏移box内的
        "default_vertical_variance": 0.002,  # 默认y偏移
        "default_threshold": 0.8,  # 默认threshold
    },
    "version": version,  # 版本
    "my_app": ["src.globals", "Globals"],  # 可选. 全局单例对象, 可以存放加载的模型, 使用og.my_app调用
    "onetime_tasks": [  # 用户点击触发的任务
        ["src.tasks.DailyTask", "DailyTask"],
        ["src.tasks.WeeklyTask", "WeeklyTask"],
        ["src.tasks.ClearMapTask", "ClearMapTask"],
        ["src.tasks.TestStartGame", "TestStartGame"],
        ["src.tasks.TestTask", "TestTask"],
        ["ok", "DiagnosisTask"],
    ],
}

# Imported down here rather than at the top so this stays a single append-at-EOF hunk, which keeps merges
# from upstream clean. apply_region swaps onetime_tasks to match the selected game client.
from src.region import apply_region

apply_region(config)
