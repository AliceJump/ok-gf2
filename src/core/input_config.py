"""
全局「输入」配置：鼠标是否走 Interception 会话鼠标（内核级真实输入）。

实录 2026-10-20：ok-gf2 和游戏跑在独立的 RDP 会话里时，PostMessage 过不了第 9 章「支援单位」的新手引导，
游戏被激活后点击还会落到真实光标处。开了这个开关后，只要能绑定到本会话的 RDP 鼠标，所有点击都走驱动；
绑不到（不在 RDP 会话、没装 Interception）自动退回原来的 PostMessage，不用手动切。
"""

from ok.util.config import ConfigOption

INPUT_OPTION_NAME = "输入"
KEY_SESSION_MOUSE = "会话鼠标驱动"

input_option = ConfigOption(
    INPUT_OPTION_NAME,
    {KEY_SESSION_MOUSE: True},
    description="鼠标输入方式，对所有任务生效",
    config_description={
        KEY_SESSION_MOUSE: "在 RDP 会话里用 Interception 驱动产生真实鼠标点击（能过新手引导、不受窗口激活影响）；"
        "绑定不到设备时自动退回 PostMessage。关掉则始终用 PostMessage",
    },
)
