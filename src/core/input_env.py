"""
「输入」设置里的运行环境 → 该用哪种鼠标设备。纯函数，不依赖 ok，单测直接跑。

同一台机器上 ok-gf2 有时跑在 RDP 会话里（远程桌面），有时跑在本机桌面（控制台）。两边能用的 Interception 鼠标
设备不同：远程桌面用本会话的 RDP 鼠标（TS_INPT\\TS_MOU），本机桌面用插在机器上的真实鼠标（HID\\...）。
实录 2026-10-21：在本机桌面跑一键日常，会话鼠标绑不上、退回 PostMessage，活动层（3D 自由场景）不认 PostMessage 的
点击和 ESC，卡在喝水菜单出不来；所以本机桌面也要能选真实鼠标。
"""

KEY_SESSION_MOUSE = "会话鼠标驱动"
KEY_ENVIRONMENT = "运行环境"
KEY_RDP_DEVICE = "远程桌面鼠标设备"
KEY_CONSOLE_DEVICE = "本机桌面鼠标设备"

ENV_AUTO = "自动识别"
ENV_RDP = "远程桌面"
ENV_CONSOLE = "本机桌面"
ENVIRONMENTS = [ENV_AUTO, ENV_RDP, ENV_CONSOLE]

DEVICE_AUTO = "自动"
DEVICE_CHOICES = [DEVICE_AUTO] + [str(i) for i in range(10, 20)]  # Interception 鼠标设备号固定 10~19

KIND_RDP = "rdp"
KIND_CONSOLE = "console"
KIND_NAMES = {KIND_RDP: ENV_RDP, KIND_CONSOLE: ENV_CONSOLE}

INPUT_DEFAULTS = {
    KEY_SESSION_MOUSE: True,
    KEY_ENVIRONMENT: ENV_AUTO,
    KEY_RDP_DEVICE: DEVICE_AUTO,
    KEY_CONSOLE_DEVICE: DEVICE_AUTO,
}


def pinned_device(value):
    """设备设置 → 固定的设备号；「自动」或填错都按自动识别。"""
    text = str(value or "").strip()
    return int(text) if text.isdigit() and 10 <= int(text) <= 19 else None


def input_key(settings):
    """影响设备绑定的那几项；变了就要重新绑定。"""
    settings = settings or {}
    return tuple(settings.get(k, INPUT_DEFAULTS[k]) for k in INPUT_DEFAULTS)


def choose_input(settings, actual_kind):
    """(设置, 实际所在环境 rdp/console/None) → (要绑定的设备种类或 None, 固定设备号或 None, 说明)。

    返回 None 种类表示用 PostMessage。设置的环境和实际不符时不硬绑：往别的桌面点比点不动更糟。
    自动识别时本机桌面仍走 PostMessage——真实鼠标会接管人正在用的光标，要明确选「本机桌面」才用。
    """
    settings = settings or {}
    if not settings.get(KEY_SESSION_MOUSE, True):
        return None, None, "设置里关掉了会话鼠标驱动"
    env = settings.get(KEY_ENVIRONMENT) or ENV_AUTO
    if actual_kind not in KIND_NAMES:
        return None, None, "识别不出当前是远程桌面还是本机桌面"
    actual = KIND_NAMES[actual_kind]
    if env == ENV_AUTO:
        if actual_kind != KIND_RDP:
            return None, None, "自动识别到本机桌面，不接管你的鼠标；要真实点击请把运行环境设成「本机桌面」"
        kind = KIND_RDP
    elif env == ENV_RDP:
        if actual_kind != KIND_RDP:
            return None, None, f"运行环境设成「{env}」，但 ok-gf2 实际跑在「{actual}」"
        kind = KIND_RDP
    elif env == ENV_CONSOLE:
        if actual_kind != KIND_CONSOLE:
            return None, None, f"运行环境设成「{env}」，但 ok-gf2 实际跑在「{actual}」"
        kind = KIND_CONSOLE
    else:
        return None, None, f"不认识的运行环境「{env}」"
    device = pinned_device(settings.get(KEY_RDP_DEVICE if kind == KIND_RDP else KEY_CONSOLE_DEVICE))
    return kind, device, f"{KIND_NAMES[kind]}（运行环境：{env}）"
