"""ok-gf2-specific exception types used across task layers."""


class SessionStopException(RuntimeError):
    """请求结束当前执行会话，同时保留外层运行时失败通知。"""
