# Test case
"""DailyTaskRunner 编排器的等价性测试。

不依赖设备与 ok-script 运行时，用桩对象验证执行顺序、开关跳过、失败标记与异常传播。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tasks.DailyTaskRunner import DailyTaskRunner


class StubTask:
    """最小可用的 task 桩，只实现编排器会调用的方法。"""

    def __init__(self, config):
        self.config = config
        self.calls = []
        self.logs = []
        self.infos = {}
        self.screenshots = []

    def tr(self, message):
        return message

    def log_info(self, message, notify=False, **kwargs):
        self.logs.append((message, notify))

    def info_set(self, key, value):
        self.infos[key] = value

    def screenshot(self, name=None, **kwargs):
        self.screenshots.append(name)

    def ensure_main(self, **kwargs):
        self.calls.append(("ensure_main", kwargs))


class UnrecoverableStub(StubTask):
    """任务抛异常之后 ensure_main 也失败（画面卡死）。"""

    def ensure_main(self, **kwargs):
        if any(name == "run" and self.config.get("_raised") for name, _ in self.calls):
            raise RuntimeError("回不到主页")
        super().ensure_main(**kwargs)


def build_plan(stub, results):
    """构造任务清单，results 为 {任务名: 返回值} 或 {任务名: 抛出的异常实例}。"""

    def make_func(key):
        def func():
            stub.calls.append(("run", key))
            value = results.get(key)
            if isinstance(value, BaseException):
                stub.config["_raised"] = True
                raise value
            return value

        return func

    return [
        ("社区每日", make_func("社区每日")),
        ("ensure_main", make_func("ensure_main")),
        ("邮件", make_func("邮件")),
        ("自动刷体力", make_func("自动刷体力")),
        ("竞技场", make_func("竞技场")),
    ]


ALL_ON = {"社区每日": True, "邮件": True, "自动刷体力": True, "竞技场": True}


class TestDailyTaskRunner(unittest.TestCase):
    def executed(self, stub):
        return [name for kind, name in stub.calls if kind == "run"]

    def test_all_success_keeps_order(self):
        stub = StubTask(dict(ALL_ON))
        runner = DailyTaskRunner(stub, build_plan(stub, {}))
        runner.run()
        self.assertEqual(
            self.executed(stub),
            ["社区每日", "ensure_main", "邮件", "自动刷体力", "竞技场"],
        )
        self.assertEqual(runner.task_status["success"], ["社区每日", "ensure_main", "邮件", "自动刷体力", "竞技场"])
        self.assertEqual(runner.task_status["failed"], [])
        self.assertEqual(runner.task_status["skipped"], [])
        self.assertEqual(runner.final_summary["status"], "完成")
        self.assertIn(("日常完成!", True), stub.logs)

    def test_ensure_main_uses_project_defaults(self):
        stub = StubTask(dict(ALL_ON))
        runner = DailyTaskRunner(stub, build_plan(stub, {}))
        runner.run()
        kwargs_list = [kwargs for kind, kwargs in stub.calls if kind == "ensure_main"]
        self.assertTrue(kwargs_list)
        for kwargs in kwargs_list:
            self.assertEqual(kwargs, {"recheck_time": 2, "time_out": 90})

    def test_disabled_tasks_are_skipped(self):
        stub = StubTask({"社区每日": False, "邮件": True, "自动刷体力": False, "竞技场": True})
        runner = DailyTaskRunner(stub, build_plan(stub, {}))
        runner.run()
        # ensure_main 是内置项，不受开关影响
        self.assertEqual(self.executed(stub), ["ensure_main", "邮件", "竞技场"])
        self.assertEqual(runner.task_status["skipped"], ["社区每日", "自动刷体力"])
        self.assertEqual(runner.final_summary["status"], "完成")

    def test_false_result_marks_failure_and_continues(self):
        stub = StubTask(dict(ALL_ON))
        runner = DailyTaskRunner(stub, build_plan(stub, {"邮件": False}))
        runner.run()
        self.assertEqual(self.executed(stub), ["社区每日", "ensure_main", "邮件", "自动刷体力", "竞技场"])
        self.assertEqual(runner.task_status["failed"], ["邮件"])
        # 单账户模式下 account_id 为空字符串
        self.assertEqual(runner.failure_details[""].get("邮件"), "任务返回 False")
        self.assertIn("DailyTask_FailTask_邮件", stub.screenshots)
        self.assertEqual(runner.final_summary["status"], "部分失败")
        self.assertTrue(any(msg.startswith("以下任务未完成或失败:") for msg, _ in stub.logs))

    def test_exception_marks_failure_and_continues(self):
        """一项任务抛异常：记失败、截图、回主页，后面的任务照跑。"""
        stub = StubTask(dict(ALL_ON))
        runner = DailyTaskRunner(stub, build_plan(stub, {"邮件": RuntimeError("boom")}))
        runner.run()
        self.assertEqual(self.executed(stub), ["社区每日", "ensure_main", "邮件", "自动刷体力", "竞技场"])
        self.assertGreaterEqual(sum(1 for kind, _ in stub.calls if kind == "ensure_main"), 2)  # 异常后回过主页
        self.assertEqual(runner.task_status["failed"], ["邮件"])
        self.assertIn("DailyTask_Exception_邮件", stub.screenshots)
        self.assertIn("boom", runner.failure_details[""]["邮件"])
        self.assertEqual(runner.final_summary["status"], "部分失败")

    def test_exception_stops_run_when_main_page_unreachable(self):
        """异常后连主页都回不去，后面的任务没法跑：整轮停下，异常往外抛。"""
        stub = UnrecoverableStub(dict(ALL_ON))
        runner = DailyTaskRunner(stub, build_plan(stub, {"邮件": RuntimeError("boom")}))
        with self.assertRaises(RuntimeError):
            runner.run()
        self.assertNotIn("自动刷体力", self.executed(stub))
        self.assertEqual(runner.final_summary["status"], "异常结束")
        self.assertIn("DailyTask_Exception_邮件", stub.screenshots)
        self.assertIn("邮件", runner.failure_details.get("", {}))

    def test_predicate_overrides_default_switch(self):
        stub = StubTask({"社区每日": False, "邮件": False, "自动刷体力": False, "竞技场": False})
        plan = build_plan(stub, {})
        plan[2] = ("邮件", plan[2][1], lambda: True)
        runner = DailyTaskRunner(stub, plan)
        runner.run()
        self.assertEqual(self.executed(stub), ["ensure_main", "邮件"])

    def test_retry_success_clears_pending_retry_info(self):
        """实录 2026-10-22：活动层重跑成功后，旧版 App 信息面板的「今日待重试」还显示活动层。"""
        import tempfile

        from src.tasks.daily.daily_record import DailyRecord

        with tempfile.TemporaryDirectory() as d:
            record = DailyRecord(str(Path(d) / "daily_record.json"))
            record.mark_failed("邮件", "任务返回 False")
            stub = StubTask(dict(ALL_ON))
            DailyTaskRunner(stub, build_plan(stub, {"社区每日": True, "ensure_main": True, "邮件": True,
                                                    "自动刷体力": True, "竞技场": True}), record=record).run()
            self.assertEqual("无", stub.infos["今日待重试"])
            self.assertIn("邮件", stub.infos["今日已完成(含之前几次)"])

    def test_publish_info_enabled(self):
        stub = StubTask(dict(ALL_ON))
        runner = DailyTaskRunner(stub, build_plan(stub, {}), publish_info=True)
        runner.run()
        self.assertIn("已完成的任务列表", stub.infos)

    def test_publish_info_disabled_by_default(self):
        """默认不写 UI info，保持旧逻辑的面板表现。"""
        stub = StubTask(dict(ALL_ON))
        runner = DailyTaskRunner(stub, build_plan(stub, {}))
        runner.run()
        self.assertEqual(stub.infos, {})


if __name__ == "__main__":
    unittest.main()
