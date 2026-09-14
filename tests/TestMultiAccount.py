# Test case
"""多账户执行上下文的测试。

用桩任务验证：账号轮次切换、login_flow 被调用、失败按账号分组、
账号列表为空时直接结束、login_flow 未实现时抛 NotImplementedError。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.tasks import account_scope_store  # noqa: E402
from src.tasks.AccountMixin import AccountMixin  # noqa: E402
from src.tasks.DailyTaskRunner import DailyTaskRunner  # noqa: E402


class StoreSnapshotMixin:
    """账号 ID 会写进真实的 configs/account_scoped_overrides.json，测试前后要还原。"""

    def setUp(self):
        self._store_backup = account_scope_store.load_overrides(force=True)

    def tearDown(self):
        account_scope_store.save_overrides(self._store_backup)


class StubTask(AccountMixin):
    """带多账户能力的桩任务。"""

    def __init__(self, config, login_results=None):
        self.config = dict(config)
        self.default_config = {}
        self.config_type = {}
        self.config_description = {}
        self.name = "一键日常"
        self._init_account_config()

        self.calls = []
        self.logs = []
        self.infos = {}
        self.screenshots = []
        self.logged_in_accounts = []
        self.login_results = login_results or {}

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

    def login_flow(self, username, password=None):
        """模拟切号：记录被切换的账号，可按配置抛异常模拟登录失败。"""
        self.logged_in_accounts.append(username)
        result = self.login_results.get(username)
        if isinstance(result, BaseException):
            raise result
        self._logged_in = True
        return result


def build_plan(stub, results):
    def make_func(key):
        def func():
            stub.calls.append(("run", (stub.current_user, key)))
            value = results.get(key)
            if isinstance(value, BaseException):
                raise value
            return value

        return func

    return [
        ("邮件", make_func("邮件")),
        ("自动刷体力", make_func("自动刷体力")),
    ]


BASE_CONFIG = {"多账户模式": True, "邮件": True, "自动刷体力": True}


class TestAccountList(StoreSnapshotMixin, unittest.TestCase):
    def test_parse_one_account_per_line(self):
        task = StubTask({"账号列表": "13800001111\n13800002222"})
        accounts = task.get_account_list()
        self.assertEqual([a["username"] for a in accounts], ["13800001111", "13800002222"])

    def test_ignore_password_and_blank_lines(self):
        task = StubTask({"账号列表": "13800001111,pwd123\n\n13800002222"})
        accounts = task.get_account_list()
        self.assertEqual([a["username"] for a in accounts], ["13800001111", "13800002222"])

    def test_empty_list_returns_empty(self):
        task = StubTask({"账号列表": ""})
        self.assertEqual(task.get_account_list(), [])

    def test_account_id_comes_from_store_registry(self):
        """账号 ID 由 account_scope_store 的注册表生成，形如 acc_<12位>，且同一账号稳定不变。"""
        task = StubTask({"账号列表": "abc"})
        account_id = task.get_account_list()[0]["account_id"]
        self.assertTrue(account_id.startswith("acc_"), account_id)

        # 再解析一次应拿到同一个 ID（跨会话稳定）
        again = StubTask({"账号列表": "abc"}).get_account_list()[0]["account_id"]
        self.assertEqual(account_id, again)


class TestMultiAccountRunner(StoreSnapshotMixin, unittest.TestCase):
    def test_each_account_runs_all_tasks(self):
        stub = StubTask({**BASE_CONFIG, "账号列表": "acc001\nacc002"})
        runner = DailyTaskRunner(stub, build_plan(stub, {}))
        runner.run()

        executed = [call for kind, call in stub.calls if kind == "run"]
        self.assertEqual(
            executed,
            [
                ("acc001", "邮件"),
                ("acc001", "自动刷体力"),
                ("acc002", "邮件"),
                ("acc002", "自动刷体力"),
            ],
        )
        self.assertEqual(stub.logged_in_accounts, ["acc001", "acc002"])
        self.assertEqual(runner.final_summary["actual_repeat_total"], 2)
        self.assertEqual(runner.final_summary["status"], "完成")

    def test_failures_grouped_by_account(self):
        """acc001 有任务失败、acc002 登录就失败：失败应归在 acc001 名下，异常向外传播。"""
        stub = StubTask(
            {**BASE_CONFIG, "账号列表": "acc001\nacc002"},
            login_results={"acc002": RuntimeError("登录超时")},
        )
        plan = build_plan(stub, {})
        plan[0] = (
            "邮件",
            lambda: (stub.calls.append(("run", (stub.current_user, "邮件"))), False)[1],
        )

        runner = DailyTaskRunner(stub, plan)
        with self.assertRaises(RuntimeError):
            runner.run()

        # 失败明细按 account_id 分组（不是用户名）
        first_id = account_scope_store.resolve_account_id("acc001", create_if_missing=True)
        self.assertEqual(sorted(runner.failure_details.keys()), [first_id])
        self.assertEqual(runner.failure_details[first_id].get("邮件"), "任务返回 False")
        # acc001 这轮已归档，acc002 因登录失败没进入任务
        self.assertEqual(len(runner.final_summary["per_round"]), 1)
        self.assertEqual(runner.final_summary["per_round"][0]["account_user"], "acc001")
        self.assertEqual(runner.final_summary["per_round"][0]["account_id"], first_id)

    def test_failure_recorded_under_current_account(self):
        """邮件任务返回 False，失败应记在 acc002 名下而不是 acc001。"""
        stub = StubTask({**BASE_CONFIG, "账号列表": "acc001\nacc002"})

        def mail_task():
            stub.calls.append(("run", (stub.current_user, "邮件")))
            return False if stub.current_user == "acc002" else True

        plan = build_plan(stub, {})
        plan[0] = ("邮件", mail_task)

        runner = DailyTaskRunner(stub, plan)
        runner.run()

        second_id = account_scope_store.resolve_account_id("acc002", create_if_missing=True)
        first_id = account_scope_store.resolve_account_id("acc001", create_if_missing=True)
        self.assertIn(second_id, runner.failure_details)
        self.assertEqual(runner.failure_details[second_id].get("邮件"), "任务返回 False")
        self.assertNotIn(first_id, runner.failure_details)
        self.assertEqual(runner.final_summary["status"], "部分失败")

    def test_empty_account_list_ends_without_running(self):
        stub = StubTask({**BASE_CONFIG, "账号列表": ""})
        runner = DailyTaskRunner(stub, build_plan(stub, {}))
        runner.run()

        executed = [call for kind, call in stub.calls if kind == "run"]
        self.assertEqual(executed, [])
        self.assertTrue(
            any("账号列表为空" in msg for msg, _ in stub.logs),
            "账号列表为空时应给出提示",
        )
        self.assertEqual(runner.final_summary["status"], "未开始")  # 未进入任何轮次

    def test_multi_account_disabled_runs_single_round(self):
        stub = StubTask({"多账户模式": False, "账号列表": "acc001\nacc002", "邮件": True, "自动刷体力": True})
        runner = DailyTaskRunner(stub, build_plan(stub, {}))
        runner.run()

        executed = [call for kind, call in stub.calls if kind == "run"]
        self.assertEqual(executed, [("", "邮件"), ("", "自动刷体力")])
        self.assertEqual(stub.logged_in_accounts, [])
        self.assertEqual(runner.final_summary["actual_repeat_total"], 1)

    def test_per_round_records_account_info(self):
        stub = StubTask({**BASE_CONFIG, "账号列表": "acc001\nacc002"})
        runner = DailyTaskRunner(stub, build_plan(stub, {}))
        runner.run()

        rounds = runner.final_summary["per_round"]
        self.assertEqual(len(rounds), 2)
        self.assertEqual(rounds[0]["account_user"], "acc001")
        self.assertEqual(rounds[1]["account_user"], "acc002")


class TestLoginFlow(unittest.TestCase):
    def test_login_flow_is_implemented(self):
        """ok-gf2 已实现游戏内切号：login_flow 不应再抛 NotImplementedError。

        真机上它依赖界面元素，这里只验证「不再被占位实现拦住」。
        """
        import inspect

        source = inspect.getsource(AccountMixin.login_flow)
        self.assertNotIn("NotImplementedError", source)
        self.assertIn("wait_click_feature", source)


if __name__ == '__main__':
    unittest.main()
