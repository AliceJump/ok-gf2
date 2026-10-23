"""
Interception 会话鼠标：在 RDP 会话里产生「内核级真实鼠标输入」，游戏分不出它和人手。

背景（实录 2026-10-20）：ok-gf2 和游戏一起跑在一个独立的 RDP 会话里。原来的 PostMessage 输入
过不了新手引导（引导高亮的目标只认真实输入，第 9 章「支援单位」引导把推图卡死），游戏被激活后还会把
PostMessage 的点击落到真实光标处。做法是借用户自己装好的 Interception 驱动
（System32\\drivers\\keyboard.sys / mouse.sys），往「本会话自己的 RDP 鼠标设备」写绝对坐标报告，
RDP 窗口最小化也能点，而且只动本会话的光标，控制台鼠标不受影响。

协议：https://github.com/oblitum/Interception/blob/master/library/interception.c
只有硬件 ID 为 TS_INPT\\TS_MOU 的设备（RDP 鼠标）会被用到；用一条无位移无按键的 RAWINPUT 标记找出
「哪台设备属于本会话」，设备号不写死、识别不到就明确报错，绝不往别的桌面乱点。

实录 2026-10-21：本机桌面（控制台）跑也要真实点击（活动层不认 PostMessage），于是按「运行环境」分两种设备：
远程桌面 = 本会话的 RDP 鼠标；本机桌面 = 机器上的真实鼠标（硬件 ID 以 HID\\ 开头）。同样用标记确认设备的输入
真的进了本桌面；设置里可以固定设备号，固定了也要标记验证通过才用。
"""

import ctypes
import logging
import os
import secrets
import struct
import sys
import time

from src.core.input_env import KIND_CONSOLE, KIND_NAMES, KIND_RDP

try:  # ok 框架的 logger；单测环境没有 ok 时退回标准 logging
    from ok.util.logger import Logger

    logger = Logger.get_logger(__name__)
except ImportError:  # pragma: no cover
    logger = logging.getLogger(__name__)

IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:  # pragma: no cover - 只在 Windows 上有这些模块
    from ctypes import wintypes

    import pywintypes
    import win32api
    import win32gui
    import win32ts

    _kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    _user = ctypes.WinDLL("user32", use_last_error=True)
    _kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _kernel.CreateFileW.restype = wintypes.HANDLE
    _kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel.CreateEventW.restype = wintypes.HANDLE
    _kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel.DeviceIoControl.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    _kernel.DeviceIoControl.restype = wintypes.BOOL
    _user.GetRawInputData.argtypes = [
        wintypes.HANDLE,
        wintypes.UINT,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.UINT),
        wintypes.UINT,
    ]
    _user.GetRawInputData.restype = wintypes.UINT

    class MousePacket(ctypes.Structure):
        _fields_ = [
            ("unit", wintypes.WORD),
            ("flags", wintypes.WORD),
            ("buttons", wintypes.WORD),
            ("wheel", wintypes.WORD),
            ("raw", wintypes.DWORD),
            ("x", wintypes.LONG),
            ("y", wintypes.LONG),
            ("extra", wintypes.DWORD),
        ]

    class RawInputDevice(ctypes.Structure):
        _fields_ = [
            ("page", wintypes.WORD),
            ("usage", wintypes.WORD),
            ("flags", wintypes.DWORD),
            ("hwnd", wintypes.HWND),
        ]

    _user.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RawInputDevice), wintypes.UINT, wintypes.UINT]
    _user.RegisterRawInputDevices.restype = wintypes.BOOL
else:  # 非 Windows（mac 上跑单测）只保留纯函数和可注入假通道的设备逻辑
    pywintypes = win32api = win32gui = win32ts = None
    _kernel = _user = None

    class MousePacket:  # 和 Windows 版字段一致，便于单测检查报文
        def __init__(self, unit=0, flags=0, buttons=0, wheel=0, raw=0, x=0, y=0, extra=0):
            self.unit, self.flags, self.buttons, self.wheel = unit, flags, buttons, wheel
            self.raw, self.x, self.y, self.extra = raw, x, y, extra


RDP_MOUSE_ID = "TS_INPT\\TS_MOU"
PHYSICAL_PREFIX = "HID\\"
IOCTL_EVENT = 0x222040
IOCTL_WRITE = 0x222080
IOCTL_HARDWARE_ID = 0x222200
MOUSE_CHANNELS = range(10, 20)  # Interception 的鼠标设备编号固定是 10~19
FLAG_ABSOLUTE = 3  # INTERCEPTION_MOUSE_MOVE_ABSOLUTE | ..._ATTRIBUTES_CHANGED 以外的位不用
FLAG_WHEEL = 0x400

BTN_LEFT, BTN_RIGHT, BTN_MIDDLE = 1, 2, 4
BUTTON_OF_KEY = {"left": BTN_LEFT, "right": BTN_RIGHT, "middle": BTN_MIDDLE}


class SessionMouseError(OSError):
    pass


def button_edges(previous, current):
    """两次按键状态之间的变化 → Interception 的 down/up 标志位（左 1/2、右 4/8、中 16/32）。"""
    flags = 0
    for mask, down, up in ((BTN_LEFT, 1, 2), (BTN_RIGHT, 4, 8), (BTN_MIDDLE, 16, 32)):
        if bool(previous & mask) != bool(current & mask):
            flags |= down if current & mask else up
    return flags


def absolute_point(x, y, bounds):
    """桌面像素坐标 → 0~65535 的绝对坐标；落在虚拟桌面之外直接报错，不发报文。"""
    left, top, width, height = bounds
    if width <= 0 or height <= 0 or not left <= x < left + width or not top <= y < top + height:
        raise SessionMouseError(f"坐标 {(x, y)} 不在会话桌面 {bounds} 内")
    return round((x - left) * 65535 / width), round((y - top) * 65535 / height)


def is_candidate(hardware_id, kind):
    """远程桌面只认 RDP 鼠标；本机桌面只认插在机器上的 HID 鼠标（不碰任何 RDP 设备）。"""
    if kind == KIND_RDP:
        return hardware_id == RDP_MOUSE_ID
    return kind == KIND_CONSOLE and str(hardware_id).upper().startswith(PHYSICAL_PREFIX)


def select_session_device(received, candidates, kind=KIND_RDP):
    """RAWINPUT 标记在本桌面收到才算识别成功。

    远程桌面：每个会话只有一台 RDP 鼠标，0 台或多台都拒绝。本机桌面：所有真实鼠标都进控制台，收到几台都行，取设备号最小的。
    """
    matches = set(received).intersection(candidates)
    if kind == KIND_CONSOLE and matches:
        return min(matches)
    if len(matches) != 1:
        name = "RDP 鼠标" if kind == KIND_RDP else "真实鼠标"
        raise SessionMouseError(f"本桌面应收到一台{name}的标记，实际收到 {sorted(matches)}")
    return matches.pop()


def session_identity():
    """(rdp/console, 会话 id)：当前进程在远程桌面还是本机桌面。识别不出来就报错，不猜。"""
    value = wintypes.DWORD()
    if not _kernel.ProcessIdToSessionId(os.getpid(), ctypes.byref(value)):
        raise ctypes.WinError(ctypes.get_last_error())
    if _user.GetSystemMetrics(0x1000):  # SM_REMOTESESSION
        return KIND_RDP, value.value
    if value.value == _kernel.WTSGetActiveConsoleSessionId():
        return KIND_CONSOLE, value.value
    try:
        protocol = win32ts.WTSQuerySessionInformation(0, value.value, win32ts.WTSClientProtocolType)
    except pywintypes.error as exc:
        raise SessionMouseError("识别不出当前输入会话") from exc
    if protocol != 2:
        raise SessionMouseError("需要在控制台或经确认的 RDP 会话里运行")
    return KIND_RDP, value.value


def current_kind():
    """rdp / console；不是 Windows 或识别不出返回 None。"""
    if not IS_WINDOWS:
        return None
    try:
        return session_identity()[0]
    except (OSError, SessionMouseError) as exc:
        logger.warning(f"识别运行环境失败：{exc}")
        return None


def desktop_bounds():
    # SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN
    return tuple(_user.GetSystemMetrics(index) for index in (76, 77, 78, 79))


class _Channel:
    def __init__(self, index):
        self.index, self.handle, self.event = index, None, None
        handle = _kernel.CreateFileW(f"\\\\.\\interception{index:02d}", 0x80000000, 0, None, 3, 0, None)
        if handle == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        self.handle = handle

    def ioctl(self, code, data=None, result=None):
        size = wintypes.DWORD()
        ok = _kernel.DeviceIoControl(
            self.handle,
            code,
            ctypes.byref(data) if data is not None else None,
            ctypes.sizeof(data) if data is not None else 0,
            ctypes.byref(result) if result is not None else None,
            ctypes.sizeof(result) if result is not None else 0,
            ctypes.byref(size),
            None,
        )
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        return size.value

    def hardware_id(self):
        value = ctypes.create_unicode_buffer(1024)
        self.ioctl(IOCTL_HARDWARE_ID, result=value)
        return value.value

    def prepare(self):
        self.event = _kernel.CreateEventW(None, True, False, None)
        if not self.event:
            raise ctypes.WinError(ctypes.get_last_error())
        self.ioctl(IOCTL_EVENT, (wintypes.HANDLE * 2)(self.event, None))

    def write(self, packet):
        if self.ioctl(IOCTL_WRITE, packet) != ctypes.sizeof(packet):
            raise SessionMouseError("RDP 鼠标报文没有被完整接受")

    def close(self):
        if self.handle is not None:
            _kernel.CloseHandle(self.handle)
            self.handle = None
        if self.event is not None:
            _kernel.CloseHandle(self.event)
            self.event = None


def _identify_session(channels, kind=KIND_RDP):
    """往每台候选设备写一条带标记的空报文，看本会话的 RAWINPUT 收到哪一台的：设备号由桌面自己说了算。"""
    received, callback_errors = set(), []
    marker = secrets.randbits(24) << 8
    header_size = 8 + 2 * ctypes.sizeof(ctypes.c_void_p)

    def procedure(hwnd, message, wparam, lparam):
        if message == 0xFF:  # WM_INPUT
            try:
                size = wintypes.UINT()
                _user.GetRawInputData(lparam, 0x10000003, None, ctypes.byref(size), header_size)
                if header_size + 24 <= size.value <= 4096:
                    buffer = ctypes.create_string_buffer(size.value)
                    count = _user.GetRawInputData(lparam, 0x10000003, buffer, ctypes.byref(size), header_size)
                    if count == size.value and struct.unpack_from("<I", buffer.raw)[0] == 0:  # RIM_TYPEMOUSE
                        extra = struct.unpack_from("<I", buffer.raw, header_size + 20)[0]
                        if extra & 0xFFFFFF00 == marker:
                            received.add(extra & 0xFF)
            except (OSError, pywintypes.error, ValueError, struct.error) as exc:
                callback_errors.append(str(exc))
        return win32gui.DefWindowProc(hwnd, message, wparam, lparam)

    cls = win32gui.WNDCLASS()
    cls.lpszClassName = f"OkGf2_SessionMouse_{os.getpid()}_{marker:x}"
    cls.lpfnWndProc = procedure
    cls.hInstance = win32api.GetModuleHandle(None)
    win32gui.RegisterClass(cls)
    hwnd = None
    try:
        hwnd = win32gui.CreateWindow(cls.lpszClassName, "", 0, 0, 0, 0, 0, -3, 0, cls.hInstance, None)
        registration = RawInputDevice(1, 2, 0x100, hwnd)  # 通用桌面 / 鼠标 / RIDEV_INPUTSINK
        if not _user.RegisterRawInputDevices(ctypes.byref(registration), 1, ctypes.sizeof(registration)):
            raise ctypes.WinError(ctypes.get_last_error())
        for index, channel in channels.items():
            channel.write(MousePacket(extra=marker | index))
        deadline = time.monotonic() + 0.7
        while time.monotonic() < deadline:
            win32gui.PumpWaitingMessages()
            time.sleep(0.01)
        if callback_errors:
            raise SessionMouseError("; ".join(callback_errors))
        return select_session_device(received, channels, kind)
    finally:
        if hwnd is not None:
            removal = RawInputDevice(1, 2, 1, None)  # RIDEV_REMOVE
            _user.RegisterRawInputDevices(ctypes.byref(removal), 1, ctypes.sizeof(removal))
            win32gui.DestroyWindow(hwnd)
        win32gui.UnregisterClass(cls.lpszClassName, cls.hInstance)


class SessionMouseDevice:
    """绑定本桌面（远程桌面 / 本机桌面）的 Interception 鼠标设备，提供 move / press / release / click / wheel。

    kind 是 rdp 或 console，device 是设置里固定的设备号（None = 自动识别）。
    所有坐标都是会话桌面的像素坐标。open() 失败只记日志并返回 False，由调用方决定退回别的输入方式。
    """

    def __init__(self, kind=KIND_RDP, device=None, identity_fn=None, bounds_fn=None, cursor_fn=None):
        self.kind = kind
        self.device = device
        self.channel = None
        self.session_id = None
        self.buttons = 0
        self.position = None
        self._identity_fn = identity_fn or session_identity
        self._bounds_fn = bounds_fn or desktop_bounds
        self._cursor_fn = cursor_fn or (win32api.GetCursorPos if win32api else None)

    @property
    def bound(self):
        return self.channel is not None

    @property
    def device_path(self):
        if not self.channel:
            return None
        return f"{KIND_NAMES.get(self.kind, self.kind)}会话 {self.session_id}，Interception 设备 {self.channel.index}"

    def open(self):
        if self.channel is not None:
            return True
        if not IS_WINDOWS:
            logger.warning("会话鼠标只支持 Windows")
            return False
        channels = {}
        try:
            kind, self.session_id = self._identity_fn()
            if kind != self.kind:
                raise SessionMouseError(f"要绑定{KIND_NAMES.get(self.kind)}的鼠标，但当前在{KIND_NAMES.get(kind, kind)}")
            for index in [self.device] if self.device else MOUSE_CHANNELS:
                candidate = None
                try:
                    candidate = _Channel(index)
                    if is_candidate(candidate.hardware_id(), self.kind):
                        candidate.prepare()
                        channels[index] = candidate
                        candidate = None
                except OSError:
                    pass
                finally:
                    if candidate is not None:
                        candidate.close()
            if not channels:
                which = f"设备 {self.device}" if self.device else "设备"
                raise SessionMouseError(f"没找到可用的 Interception {KIND_NAMES.get(self.kind)}鼠标{which}（驱动没装或设备号不对）")
            index = _identify_session(channels, self.kind)
            self.channel = channels.pop(index)
            logger.info(f"会话鼠标已绑定（光标没动过）：{self.device_path}")
            return True
        except (OSError, pywintypes.error) as exc:
            logger.warning(f"会话鼠标绑定失败：{exc}")
            return False
        finally:
            for channel in channels.values():
                channel.close()

    def close(self):
        if self.channel is not None:
            try:
                if self.buttons:
                    self._write(*(self.position or (0, 0)), 0)
            finally:
                self.channel.close()
                self.channel = None
                self.buttons, self.position = 0, None

    def _write(self, x, y, buttons, wheel=0):
        if self.channel is None and not self.open():
            return False
        try:
            if self._identity_fn() != (self.kind, self.session_id):
                raise SessionMouseError("输入会话变了，不再使用之前绑定的设备")
            px, py = absolute_point(int(x), int(y), self._bounds_fn())
            flags = button_edges(self.buttons, buttons)
            if wheel:
                flags |= FLAG_WHEEL
            packet = MousePacket(flags=FLAG_ABSOLUTE, buttons=flags, wheel=(int(wheel) * 120) & 0xFFFF, x=px, y=py)
            self.channel.write(packet)
            self.buttons, self.position = buttons, (int(x), int(y))
            return True
        except OSError as exc:
            logger.error(f"会话鼠标报文失败：{exc}")
            return False

    def cursor(self):
        return tuple(self._cursor_fn()) if self._cursor_fn else None

    def move(self, x, y, settle=0.1, tolerance=2):
        """绝对定位到 (x, y)，然后等光标真的到了；没到只记警告，不影响后续按键。"""
        if not self._write(x, y, self.buttons):
            return False
        deadline = time.monotonic() + settle
        while self._cursor_fn and time.monotonic() < deadline:
            actual = self.cursor()
            if actual and abs(actual[0] - x) <= tolerance and abs(actual[1] - y) <= tolerance:
                return True
            time.sleep(0.005)
        if self._cursor_fn:
            logger.warning(f"会话鼠标移动后光标在 {self.cursor()}，目标 {(x, y)}")
        return True

    def press(self, buttons=BTN_LEFT):
        x, y = self.position if self.position is not None else self.cursor()
        return self._write(x, y, buttons)

    def release(self):
        x, y = self.position if self.position is not None else self.cursor()
        return self._write(x, y, 0)

    def click(self, x, y, buttons=BTN_LEFT, down_time=0.02):
        if not self.move(x, y):
            return False
        time.sleep(0.01)
        if not self.press(buttons):
            return False
        time.sleep(max(down_time, 0.01))
        return self.release()

    def wheel(self, x, y, notches):
        if not self.move(x, y):
            return False
        step = 1 if notches > 0 else -1
        for _ in range(abs(int(notches))):
            if not self._write(x, y, self.buttons, wheel=step):
                return False
            time.sleep(0.01)
        return True
