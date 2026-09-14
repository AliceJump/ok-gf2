# Test case
"""汇总 txt 生成模块的测试。

不依赖设备与 ok-script 运行时，用桩任务 + DailyTaskRunner 驱动，落到临时目录验证文件内容。
"""

import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tasks.DailyTaskRunner import DailyTaskRunner  # noqa: E402
from src.tasks.daily_summary import (  # noqa: E402
    build_summary_lines,
    create_task_summary_report,
    iter_summary_candidates,
)


class StubTask:
    def __init__(self, config, name="一键日常"):
        self.config = config
        self.name = name
        self.calls = []
        self.logs = []
        self.screenshots = []

    def tr(self, message):
        return message

    def log_info(self, message, notify=False, **kwargs):
        self.logs.append((message, notify))

    def info_set(self, key, value):
        pass

    def screenshot(self, name=None, **kwargs):
        self.screenshots.append(name)

    def ensure_main(self, **kwargs):
        pass


def build_plan(stub, results):
    def make_func(key):
        def func():
            stub.calls.append(key)
            value = results.get(key)
            if isinstance(value, BaseException):
                raise value
            return value

        return func

    return [
        ("邮件", make_func("邮件")),
        ("自动刷体力", make_func("自动刷体力")),
        ("竞技场", make_func("竞技场")),
    ]


ALL_ON = {"邮件": True, "自动刷体力": True, "竞技场": True}


class TestSummaryCandidates(unittest.TestCase):
    def test_first_candidate_is_plain_name(self):
        it = iter_summary_candidates("一键日常_20260101_000000.txt")
        self.assertEqual(next(it), "一键日常_20260101_000000.txt")

    def test_collision_suffixes_increment(self):
        it = iter_summary_candidates("a.txt")
        names = [next(it) for _ in range(4)]
        self.assertEqual(names, ["a.txt", "a_1.txt", "a_2.txt", "a_3.txt"])


class TestSummaryReport(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="okgf2_summary_test_"))

    def read_report(self, path):
        return path.read_text(encoding="utf-8")

    def test_success_report(self):
        stub = StubTask(dict(ALL_ON))
        runner = DailyTaskRunner(stub, build_plan(stub, {}))
        runner.run()
        path = create_task_summary_report(stub, self.tmp, runner.final_summary)

        self.assertTrue(path.exists())
        content = self.read_report(path)
        self.assertIn("执行状态: 完成", content)
        self.assertIn("成功任务:", content)
        self.assertIn("邮件", content)
        self.assertIn("所有任务执行成功！", content)
        self.assertNotIn("异常信息:", content)

    def test_failure_report_contains_details(self):
        stub = StubTask(dict(ALL_ON))
        runner = DailyTaskRunner(stub, build_plan(stub, {"邮件": False}))
        runner.run()
        path = create_task_summary_report(stub, self.tmp, runner.final_summary)

        content = self.read_report(path)
        self.assertIn("执行状态: 部分失败", content)
        self.assertIn("失败任务:", content)
        self.assertIn("失败消息:", content)
        self.assertIn("任务返回 False", content)

    def test_exception_report(self):
        stub = StubTask(dict(ALL_ON))
        runner = DailyTaskRunner(stub, build_plan(stub, {"自动刷体力": RuntimeError("卡在加载界面")}))
        with self.assertRaises(RuntimeError):
            runner.run()
        path = create_task_summary_report(stub, self.tmp, runner.final_summary)

        content = self.read_report(path)
        self.assertIn("执行状态: 异常结束", content)
        self.assertIn("异常信息:", content)
        self.assertIn("卡在加载界面", content)
        # 异常发生时已执行的成功任务仍应被记录
        self.assertIn("邮件", content)

    def test_skipped_tasks_are_recorded(self):
        stub = StubTask({"邮件": True, "自动刷体力": False, "竞技场": False})
        runner = DailyTaskRunner(stub, build_plan(stub, {}))
        runner.run()
        path = create_task_summary_report(stub, self.tmp, runner.final_summary)

        content = self.read_report(path)
        self.assertIn("跳过任务:", content)
        self.assertIn("自动刷体力", content)

    def test_old_files_are_cleaned_up(self):
        stub = StubTask(dict(ALL_ON))
        runner = DailyTaskRunner(stub, build_plan(stub, {}))
        runner.run()

        target_dir = self.tmp / "ok-gf2" / stub.name
        target_dir.mkdir(parents=True, exist_ok=True)
        stale = target_dir / "stale.txt"
        stale.write_text("old", encoding="utf-8")
        old_mtime = time.time() - (10 * 24 * 3600)
        os_utime_applied = False
        try:
            import os

            os.utime(stale, (old_mtime, old_mtime))
            os_utime_applied = True
        except Exception:
            pass

        create_task_summary_report(stub, self.tmp, runner.final_summary)
        if os_utime_applied:
            self.assertFalse(stale.exists(), "超过保留天数的旧汇总应被清理")

    def test_same_second_creates_suffixed_file(self):
        stub = StubTask(dict(ALL_ON))
        runner = DailyTaskRunner(stub, build_plan(stub, {}))
        runner.run()

        first = create_task_summary_report(stub, self.tmp, runner.final_summary)
        # 手工抢占同名文件，模拟同一秒内重复创建
        first.write_text("placeholder", encoding="utf-8")
        second = create_task_summary_report(stub, self.tmp, runner.final_summary)

        self.assertNotEqual(first, second)
        self.assertTrue(second.exists())
        self.assertTrue(second.stem.endswith("_1"))

    def test_build_summary_lines_without_task_tr(self):
        """task 缺少 tr 时不应抛异常。"""

        class Bare:
            name = "裸任务"

        lines = build_summary_lines(Bare(), {"status": "完成"})
        self.assertTrue(lines)
        self.assertIn("裸任务执行情况汇总", lines[0])


if __name__ == '__main__':
    unittest.main()
