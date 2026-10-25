"""每日任务记录（北京时间 05:00 切日）的测试。"""

import os
import sys
import tempfile
import unittest
from datetime import UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestDailyRecord(unittest.TestCase):
    def test_game_day_resets_at_5am_beijing(self):
        from datetime import datetime

        from src.tasks.daily.daily_record import RESET_TZ, game_day

        self.assertEqual(game_day(datetime(2026, 10, 19, 4, 59, tzinfo=RESET_TZ)), "2026-10-18")
        self.assertEqual(game_day(datetime(2026, 10, 19, 5, 0, tzinfo=RESET_TZ)), "2026-10-19")
        # 其它时区的时间先换算到北京时间：UTC 20:59 = 北京次日 04:59，仍算前一天
        utc = UTC
        self.assertEqual(game_day(datetime(2026, 10, 18, 20, 59, tzinfo=utc)), "2026-10-18")
        self.assertEqual(game_day(datetime(2026, 10, 18, 21, 0, tzinfo=utc)), "2026-10-19")
        # naive 时间按本机时区理解，结果和显式标本机时区一致
        local = datetime(2026, 10, 19, 12, 0)
        self.assertEqual(game_day(local), game_day(local.astimezone()))

    def test_record_roundtrip_and_reset(self):
        from datetime import datetime

        from src.tasks.daily.daily_record import RESET_TZ, DailyRecord

        def bj(*args):
            return datetime(*args, tzinfo=RESET_TZ)

        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "daily_record.json")
            rec = DailyRecord(path, now=bj(2026, 10, 19, 20, 0))
            rec.mark_success("邮件")
            rec.mark_failed("活动层", "异常: 请从游戏主页进入")
            rec.mark_uncertain("情报和战前补给")
            rec.save()
            # 同一天再读：成功的跳过，失败的待重试
            again = DailyRecord(path, now=bj(2026, 10, 19, 23, 0))
            self.assertTrue(again.is_done("邮件"))
            self.assertFalse(again.is_done("活动层"))
            self.assertEqual(again.failed_tasks(), {"活动层": "异常: 请从游戏主页进入"})
            # 重试成功后失败记录被删掉
            again.mark_success("活动层")
            self.assertEqual(again.failed_tasks(), {})
            self.assertTrue(again.is_done("活动层"))
            again.save()
            # 北京时间 04:59 还是同一个游戏日
            same = DailyRecord(path, now=bj(2026, 10, 20, 4, 59))
            self.assertTrue(same.is_done("邮件"))
            # 第二天（北京时间 05:00 之后）全部清空
            tomorrow = DailyRecord(path, now=bj(2026, 10, 20, 5, 1))
            self.assertFalse(tomorrow.is_done("邮件"))
            self.assertEqual(tomorrow.failed_tasks(), {})
            # 多账户分开记
            rec2 = DailyRecord(path, now=bj(2026, 10, 20, 6, 0))
            rec2.mark_success("邮件", account="A")
            self.assertTrue(rec2.is_done("邮件", "A"))
            self.assertFalse(rec2.is_done("邮件", "B"))
