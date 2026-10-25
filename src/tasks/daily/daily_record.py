"""
每天一份的日常任务记录（configs/daily_record.json）。

- 以游戏日为准（国服每天北京时间 05:00 重置），跨天自动清空。
- 成功的任务记下来，再跑一键日常时直接跳过，不重复执行。
- 失败/待核查的任务记下失败原因，下次只重试这些；重试成功就把失败记录删掉。
- 多账户按 account_id 分开记。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

RESET_HOUR = 5  # 国服日常每天 05:00 重置（北京时间）
RESET_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")  # 北京时间没有夏令时，固定 +8 即可，不依赖 tzdata
DEFAULT_PATH = os.path.join("configs", "daily_record.json")


def game_day(now: datetime | None = None) -> str:
    """游戏日：北京时间凌晨 5 点前算前一天。naive 的 now 按本机时区理解，再换算到北京时间。"""
    now = now or datetime.now()
    if now.tzinfo is None:
        now = now.astimezone()
    now = now.astimezone(RESET_TZ)
    return (now - timedelta(hours=RESET_HOUR)).strftime("%Y-%m-%d")


def _empty(account_data=None):
    return {"success": [], "failed": {}, "uncertain": []}


class DailyRecord:
    def __init__(self, path: str = DEFAULT_PATH, now: datetime | None = None):
        self.path = path
        self.day = game_day(now)
        self.data = {"day": self.day, "accounts": {}}
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        if isinstance(data, dict) and data.get("day") == self.day and isinstance(data.get("accounts"), dict):
            self.data = data

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def _acc(self, account: str = ""):
        return self.data["accounts"].setdefault(account or "", _empty())

    def is_done(self, key: str, account: str = "") -> bool:
        return key in self._acc(account)["success"]

    def done_tasks(self, account: str = "") -> list[str]:
        return list(self._acc(account)["success"])

    def failed_tasks(self, account: str = "") -> dict[str, str]:
        return dict(self._acc(account)["failed"])

    def mark_success(self, key: str, account: str = ""):
        acc = self._acc(account)
        if key not in acc["success"]:
            acc["success"].append(key)
        acc["failed"].pop(key, None)
        if key in acc["uncertain"]:
            acc["uncertain"].remove(key)

    def mark_failed(self, key: str, message: str, account: str = ""):
        acc = self._acc(account)
        acc["failed"][key] = str(message)
        if key in acc["success"]:
            acc["success"].remove(key)

    def mark_uncertain(self, key: str, account: str = ""):
        acc = self._acc(account)
        if key not in acc["uncertain"]:
            acc["uncertain"].append(key)
        if key in acc["success"]:
            acc["success"].remove(key)
