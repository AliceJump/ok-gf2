version = "v5.0.11"

config = {
    'debug': False,  # Optional, default: False
    'use_gui': True,
    'config_folder': 'configs',
    'gui_icon': 'icon.png',
    'wait_until_before_delay': 0,  # default 1 , for wait_until() function
    'wait_until_check_delay': 0,
    'wait_until_settle_time': 0,
    'ocr': {
        'lib': 'onnxocr',
        'params': {
            'use_openvino': True,
        }
    },
    'windows': {  # required  when supporting windows game
        'exe': 'GF2_Exilium.exe',
        # 'calculate_pc_exe_path': calculate_pc_exe_path,
        # 'hwnd_class': 'UnrealWindow',
        'interaction': 'Genshin',
        'can_bit_blt': True,  # default false, opengl games does not support bit_blt
        'bit_blt_render_full': True,
        'check_hdr': True,
        'force_no_hdr': False,
        # 'check_night_light': True,
        'force_no_night_light': False,
        'require_bg': True
    },
    'start_timeout': 120,  # default 60
    'window_size': {
        'width': 1200,
        'height': 800,
        'min_width': 600,
        'min_height': 450,
    },
    'supported_resolution': {
        'ratio': '16:9',
        'min_size': (1280, 720),
        'resize_to': [(2560, 1440), (1920, 1080), (1600, 900), (1280, 720)],
    },
    'analytics': {
        'report_url': 'http://report.ok-script.cn:8080/report',
    },
    'links': {
        'default': {
            'github': 'https://github.com/ok-oldking/ok-gf2',
            'discord': 'https://discord.gg/vVyCatEBgA',
            'qq_group': 'https://qm.qq.com/q/oKHdK7P8lO',
            'sponsor': 'https://afdian.com/a/ok-oldking',
            'share': 'OK-GF2 夸克网盘下载：https://pan.quark.cn/s/75b55ef72a34 GitHub下载: https://github.com/ok-oldking/ok-gf2/releases/latest',
            'faq': 'https://cnb.cool/ok-oldking/ok-gf2/-/blob/main/README.md',
        },
    },
    'git_update': {'sources': [
        {
            'name': 'Global',
            'git_url': 'https://cnb.cool/ok-oldking/ok-gf2.git',
            'pip_url': 'https://pypi.org/simple/'
        },
        {
            'name': 'China',
            'git_url': 'https://cnb.cool/ok-oldking/ok-gf2.git',
            'pip_url': 'https://mirrors.aliyun.com/pypi/simple'
        },
    ]},
    'screenshots_folder': "screenshots",
    'gui_title': 'ok-gf2',  # Optional
    # 'coco_feature_folder': get_path(__file__, 'assets/coco_feature'),  # required if using feature detection
    'log_file': 'logs/ok-ww.log',  # Optional, auto rotating every day
    'error_log_file': 'logs/ok-ww_error.log',
    'version': version,
    'my_app': ['src.globals', 'Globals'],
    'onetime_tasks': [  # tasks to execute
        ["src.tasks.DailyTask", "DailyTask"],
        ["src.tasks.ClearMapTask", "ClearMapTask"],
        ["ok", "DiagnosisTask"],
    ]
}
