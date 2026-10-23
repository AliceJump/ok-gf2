"""
全局「输入」配置：鼠标是否走 Interception 驱动（内核级真实输入），以及在哪个环境里跑、用哪台设备。

实录 2026-10-20：ok-gf2 和游戏跑在独立的 RDP 会话里时，PostMessage 过不了第 9 章「支援单位」的新手引导，
游戏被激活后点击还会落到真实光标处。开了这个开关后，只要能绑定到本会话的 RDP 鼠标，所有点击都走驱动；
绑不到（不在 RDP 会话、没装 Interception）自动退回原来的 PostMessage，不用手动切。
实录 2026-10-21：本机桌面跑活动层也需要真实点击，加了「运行环境」，见 src/core/input_env.py。
"""

from ok.util.config import ConfigOption

from src.core.input_env import (
    DEVICE_CHOICES,
    ENVIRONMENTS,
    INPUT_DEFAULTS,
    KEY_CONSOLE_DEVICE,
    KEY_ENVIRONMENT,
    KEY_RDP_DEVICE,
    KEY_SESSION_MOUSE,
)

INPUT_OPTION_NAME = "输入"

input_option = ConfigOption(
    INPUT_OPTION_NAME,
    dict(INPUT_DEFAULTS),
    description="鼠标输入方式，对所有任务生效",
    config_description={
        KEY_SESSION_MOUSE: "用 Interception 驱动产生真实鼠标点击（能过新手引导、活动层等只认真实输入的界面）；"
        "绑定不到设备时自动退回 PostMessage。关掉则始终用 PostMessage",
        KEY_ENVIRONMENT: "自动识别：远程桌面用会话鼠标，本机桌面用 PostMessage（不动你的光标）；\n"
        "远程桌面：只在 RDP 会话里用该会话的 RDP 鼠标；\n"
        "本机桌面：用机器上的真实鼠标点击，跑的时候会接管光标，别同时用鼠标。\n"
        "设的环境和实际不符时退回 PostMessage，不往别的桌面点。改了下一次点击就生效",
        KEY_RDP_DEVICE: "远程桌面用哪台 Interception 鼠标（10~19），自动 = 按本会话实际收到的标记识别",
        KEY_CONSOLE_DEVICE: "本机桌面用哪台 Interception 鼠标（10~19），自动 = 本机桌面收到标记的第一台",
    },
    config_type={
        KEY_ENVIRONMENT: {"type": "drop_down", "options": ENVIRONMENTS},
        KEY_RDP_DEVICE: {"type": "drop_down", "options": DEVICE_CHOICES},
        KEY_CONSOLE_DEVICE: {"type": "drop_down", "options": DEVICE_CHOICES},
    },
)
