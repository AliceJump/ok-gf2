# Test case
"""按账号覆盖任务配置（多账户独立配置）的运行时行为测试。

用可挂属性的假 Config 模拟 ok-script 的 Config 对象，验证覆盖开关、账号上下文、
类型转换与「未运行时不生效」这几条规则。
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.account_override_mixin import AccountOverrideMixin  # noqa: E402
from src.tasks import account_scope_store  # noqa: E402


class FakeConfig:
    """够用的 Config 替身：支持 get / 属性挂载（ok-script 的 Config 也是对象而非 dict）。"""

    def __init__(self, data):
        self._data = dict(data)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __contains__(self, key):
        return key in self._data


class FakeTask(AccountOverrideMixin):
    def __init__(self, config, running=True):
        self.config = config
        self.running = running
        self.current_user = ""
        self.current_account_id = ""


class TestAccountOverride(unittest.TestCase):
    def setUp(self):
        self._backup = account_scope_store.load_overrides(force=True)

    def tearDown(self):
        account_scope_store.save_overrides(self._backup)

    def make_task(self, data, running=True):
        config = FakeConfig(data)
        task = FakeTask(config, running=running)
        task._bind_account_aware_config_get()
        return task

    def test_no_override_returns_base_value(self):
        task = self.make_task({"邮件": True, "多账户独立配置": True})
        task.current_account_id = account_scope_store.resolve_account_id("u1", create_if_missing=True)
        self.assertTrue(task.config.get("邮件"))

    def test_override_takes_effect(self):
        account_id = account_scope_store.resolve_account_id("u1", create_if_missing=True)
        account_scope_store.set_account_task_overrides(account_id, "FakeTask", {"邮件": False})

        task = self.make_task({"邮件": True, "多账户独立配置": True})
        task.current_account_id = account_id
        self.assertFalse(task.config.get("邮件"))

    def test_override_ignored_when_switch_off(self):
        account_id = account_scope_store.resolve_account_id("u1", create_if_missing=True)
        account_scope_store.set_account_task_overrides(account_id, "FakeTask", {"邮件": False})

        task = self.make_task({"邮件": True, "多账户独立配置": False})
        task.current_account_id = account_id
        self.assertTrue(task.config.get("邮件"), "开关关闭时不应应用账号覆盖")

    def test_override_ignored_when_not_running(self):
        """任务未运行时（例如 GUI 读取配置渲染）不应用覆盖，否则界面会显示错的值。"""
        account_id = account_scope_store.resolve_account_id("u1", create_if_missing=True)
        account_scope_store.set_account_task_overrides(account_id, "FakeTask", {"邮件": False})

        task = self.make_task({"邮件": True, "多账户独立配置": True}, running=False)
        task.current_account_id = account_id
        self.assertTrue(task.config.get("邮件"))

    def test_override_ignored_without_account_context(self):
        account_id = account_scope_store.resolve_account_id("u1", create_if_missing=True)
        account_scope_store.set_account_task_overrides(account_id, "FakeTask", {"邮件": False})

        task = self.make_task({"邮件": True, "多账户独立配置": True})
        # 不设置 current_account_id / current_user
        self.assertTrue(task.config.get("邮件"))

    def test_overrides_are_per_account(self):
        a1 = account_scope_store.resolve_account_id("u1", create_if_missing=True)
        a2 = account_scope_store.resolve_account_id("u2", create_if_missing=True)
        account_scope_store.set_account_task_overrides(a1, "FakeTask", {"体力本": "定向"})
        account_scope_store.set_account_task_overrides(a2, "FakeTask", {"体力本": "深度搜索"})

        task = self.make_task({"体力本": "军备解析", "多账户独立配置": True})

        task.current_account_id = a1
        self.assertEqual(task.config.get("体力本"), "定向")

        task.current_account_id = a2
        self.assertEqual(task.config.get("体力本"), "深度搜索")

    def test_type_coercion(self):
        account_id = account_scope_store.resolve_account_id("u1", create_if_missing=True)
        account_scope_store.set_account_task_overrides(
            account_id, "FakeTask", {"开关": "false", "数量": "7", "比例": "1.5", "文本": 42}
        )
        task = self.make_task(
            {"开关": True, "数量": 3, "比例": 0.5, "文本": "x", "多账户独立配置": True}
        )
        task.current_account_id = account_id

        self.assertIs(task.config.get("开关"), False, "字符串 false 应转成布尔")
        self.assertEqual(task.config.get("数量"), 7)
        self.assertIsInstance(task.config.get("数量"), int)
        self.assertEqual(task.config.get("比例"), 1.5)
        self.assertIsInstance(task.config.get("比例"), float)
        self.assertEqual(task.config.get("文本"), "42")

    def test_unrelated_keys_keep_base_value(self):
        account_id = account_scope_store.resolve_account_id("u1", create_if_missing=True)
        account_scope_store.set_account_task_overrides(account_id, "FakeTask", {"邮件": False})

        task = self.make_task({"邮件": True, "竞技场": True, "多账户独立配置": True})
        task.current_account_id = account_id
        self.assertTrue(task.config.get("竞技场"), "未覆盖的键应保持基值")

    def test_removed_override_falls_back_to_base(self):
        account_id = account_scope_store.resolve_account_id("u1", create_if_missing=True)
        account_scope_store.set_account_task_overrides(account_id, "FakeTask", {"邮件": False})
        task = self.make_task({"邮件": True, "多账户独立配置": True})
        task.current_account_id = account_id
        self.assertFalse(task.config.get("邮件"))

        account_scope_store.remove_account_task_overrides(account_id, "FakeTask")
        self.assertTrue(task.config.get("邮件"), "清空覆盖后应回落到基值")

    def test_binding_is_idempotent(self):
        task = self.make_task({"邮件": True, "多账户独立配置": True})
        first_get = task.config.get
        task._bind_account_aware_config_get()
        self.assertIs(task.config.get, first_get, "重复绑定不应叠加包装")

    def test_binding_skipped_for_plain_dict_config(self):
        """config 是普通 dict 时无法挂属性，应静默跳过而不是抛异常。"""

        class DictTask(AccountOverrideMixin):
            def __init__(self):
                self.config = {"邮件": True}
                self.running = True
                self.current_user = ""
                self.current_account_id = ""

        task = DictTask()
        task._bind_account_aware_config_get()  # 不应抛异常
        self.assertTrue(task.config.get("邮件"))


if __name__ == '__main__':
    unittest.main()
