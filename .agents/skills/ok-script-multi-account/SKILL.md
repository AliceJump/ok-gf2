---
name: ok-script-multi-account
description: Multi-account execution and per-account configuration overrides in ok-gf2 — account list, stable account IDs, per-account task config overrides, and the 账号配置 GUI page. Use when adding a task that should support multi-account, changing the account list format, debugging why a per-account override is not taking effect, or touching account_scope_store / AccountOverrideMixin / AccountConfigTab.
---

# 多账户与账号级配置覆盖（ok-gf2）

## 组成

| 文件 | 职责 |
|---|---|
| `src/tasks/AccountMixin.py` | 多账户轮次（`iter_multi_account_context`）、账号列表解析、`login_flow` 切号 |
| `src/tasks/account_scope_store.py` | 持久化：账号注册表（账号名 → 稳定 ID）、每账号任务覆盖、map 内容 |
| `src/core/base_mixin/account_override_mixin.py` | 运行时把 `config.get` 接到账号覆盖层 |
| `src/gui/AccountConfigTab.py` | 「账号配置」页：账号列表、按账号覆盖任务配置 |
| `src/config.py` | `custom_tabs` 注册配置页 |

存储文件：`configs/account_scoped_overrides.json`。

## 数据流

```
任务配置的「账号列表」(唯一真源)
        │  get_account_list()
        ▼
account_scope_store 注册表 ──► 稳定 account_id (acc_xxxxxxxxxxxx)
        │
        │  iter_multi_account_context()
        ▼
set_current_account(username, account_id)
        │  _bind_account_aware_config_get()
        ▼
config.get(key) ──► 有该账号的覆盖值？→ 用覆盖值 : 用基值
```

**与 ok-end-field 的关键差异**：那边「账号页的账号列表」和「任务配置里的账号列表」是两套独立数据，
容易混淆。ok-gf2 只保留**任务配置里的 `账号列表`** 作为唯一真源，store 只负责维护稳定 ID 和覆盖值。
`get_account_list()` 用 `create_if_missing=True`，即使用户从没打开过配置页，ID 也是稳定的。

## 任务侧接入

三步：

```python
class MyTask(BaseGfTask):
    support_multi_account = True                     # ① 声明支持（配置页据此列出任务）
    account_config_blacklist = {"某个全局开关"}        # ② 声明不可按账号覆盖的键

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_account_config()                  # ③ 注册 多账户模式/多账户独立配置/账号列表
```

`BaseGfTask.__init__` 用 `getattr` 读类属性，所以**类体里声明即可**，不必在 `__init__` 里赋值。

可选属性（都已在 `BaseGfTask` 里给默认值）：

| 属性 | 默认 | 说明 |
|---|---|---|
| `support_multi_account` | `False` | 配置页是否列出该任务 |
| `account_config_blacklist` | `set()` | 不可覆盖的键；会与 `ALWAYS_HIDDEN_CONFIG_KEYS` 合并 |
| `account_config_whitelist` | `set()` | 只允许这些键可覆盖（非空时生效） |
| `account_config_defaults` | `{}` | 覆盖编辑器里的建议默认值 |

`ALWAYS_HIDDEN_CONFIG_KEYS = {"多账户模式", "多账户独立配置", "账号列表"}` 三项永远不可覆盖。

## 覆盖生效的四个前提（缺一不可）

1. `多账户独立配置` 开关打开
2. `self.running` 为 True —— **任务未运行时（GUI 读配置渲染）不应用覆盖**，否则界面会显示错的值
3. 有账号上下文（`current_account_id` 或 `current_user` 非空）
4. 该账号该任务下确实存在这个键的覆盖值

排查「覆盖没生效」时按这四条顺序查。测试见 `tests/TestAccountOverride.py`。

## 类型转换

覆盖值从 JSON 读出来是字符串/原生类型，写入前会按**基值类型**转换（`_coerce_override_value`）：

- 基值 `bool`：`"true"/"1"/"yes"/"on"/"是"/"开启"` → True，`"false"/"0"/"no"/"off"/"否"/"关闭"` → False，其余保持基值
- 基值 `int`/`float`：能解析就转，失败保持基值
- 基值 `list`：只接受 list，否则保持基值
- 基值 `str`：转成字符串

## 测试注意

- 账号 ID 会写进**真实的** `configs/account_scoped_overrides.json`，测试必须快照/还原
  （见 `tests/TestMultiAccount.py` 的 `StoreSnapshotMixin`）。
- 配置页**不能无头实例化**（继承 Qt 的 `CustomTab`，没有 QApplication 会直接崩进程，且没有 traceback）。
  要测它的逻辑用 `AccountConfigTab.__new__(AccountConfigTab)` 绕过 `__init__`，再手工塞 `executor`。
- `ok.util.clazz.init_class_by_name` 会**实例化**类，不要拿它做无头检查；改用
  `importlib.import_module(...)` + `getattr(mod, 'ClassName')`。

## 移植来源与未迁移部分

来自 ok-end-field，已剥离终末地专有内容：

- `GlobalZipLineConfigProxy` / `GlobalKeyConfigProxy`（滑索配置、全局键位）依赖 ok-end-field 的
  `src.core.global_config_store`，ok-gf2 没有对应的全局配置存储。若将来需要「全局配置也可按账号覆盖」，
  照这两个代理类的形状补一个即可。
- `from src.icons import Icons` 改用 qfluentwidgets 的 `FluentIcon`。
