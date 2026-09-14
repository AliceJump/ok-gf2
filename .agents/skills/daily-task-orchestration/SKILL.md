---
name: daily-task-orchestration
description: Orchestrate multi-step daily (每日) task plans in ok-gf2 with DailyTaskRunner. Use when adding, removing, reordering, or gating sub-tasks in DailyTask.build_task_plan(), changing pass/fail semantics, adding failure screenshots or summaries, or porting orchestration patterns from ok-end-field.
---

# Daily Task Orchestration (ok-gf2)

## Overview

`DailyTask`（一键日常）由 15 个任务项串联而成，编排骨架在 `src/tasks/DailyTaskRunner.py`，
任务清单在 `src/tasks/DailyTask.py` 的 `build_task_plan()`。

`DailyTask` 本身只剩 214 行，职责是「注册配置 + 声明清单 + 驱动编排器」；
具体执行逻辑按领域拆在 `src/tasks/daily/` 下：

| 文件 | 类 | 负责 |
|---|---|---|
| `daily_common_mixin.py` | `DailyCommonMixin` | OCR 轮询、弹窗兜底、候选框筛选、`confirm_auto_battle_up` |
| `daily_reward_mixin.py` | `DailyRewardMixin` | 邮件、委托、巡录、探索、闪耀星愿、社区每日 |
| `daily_activity_mixin.py` | `DailyActivityMixin` | 活动自律、活动层（喝水/吃饭/领奖）、活动列表识别 |
| `daily_public_mixin.py` | `DailyPublicMixin` | 公共区委托、自主循环、免费礼包与心愿单 |
| `daily_battle_mixin.py` | `DailyBattleMixin` | 体力本、竞技场、兵棋推演、班组尘烟 |

MRO：`DailyTask(AccountMixin, DailyCommonMixin, DailyRewardMixin, DailyActivityMixin, DailyPublicMixin, DailyBattleMixin, CommunityMixin, BaseGfTask)`。

各 mixin 之间**没有重复方法名**，所以 MRO 顺序目前不影响行为；新增方法前先确认没有同名冲突。
跨 mixin 调用是允许的（例如 `arena` 调 `wait_click_ocr_with_pop_up`），因为运行时是同一个 `self`。

```python
def build_task_plan(self):
    return [
        ("社区每日", self.community_daily),
        ("ensure_main", lambda: self.ensure_main(recheck_time=2, time_out=90)),
        ("邮件", self.mail),
        ...
    ]

def run(self):
    if not self.config.get('已确认启用游戏内全局自动功能'):
        self.confirm_auto_battle_up()
    self.daily_runner = DailyTaskRunner(self, self.build_task_plan())
    self.daily_runner.run()
```

## Task item shape

- `(任务名, 执行函数)` —— 任务名同时是 `configs/DailyTask.json` 里的开关键名，默认判定 `config.get(任务名)`。
- `(任务名, 执行函数, 开关谓词)` —— 需要 OR 组合或额外条件时提供谓词，提供后**替代**默认的 `config.get` 判定。
- 任务名在 `DailyTaskRunner.ALWAYS_RUN_KEYS` 中（目前只有 `ensure_main`）时不做开关判定，恒执行。

## Execution semantics（改动前必须清楚）

1. 每个任务项执行前都会调用 `ensure_main(recheck_time=2, time_out=90)`。
2. 执行函数返回 `False` → 记入 `failed`，**继续**执行后续任务，并对该任务名截一张失败截图
   （`DailyTask_FailTask_<任务名>`）。
3. 执行函数抛异常 → 记录现场、截 `DailyTask_Exception`、写 `final_summary`，然后**向外传播**，
   后续任务不再执行。这与改造前 `run()` 的行为一致，不要改成「吞掉异常继续跑」。
4. 开关关闭 → 记入 `skipped`，不执行。
5. 全部跑完后：有 failed 则记「部分失败」，否则「完成」，并 `notify=True` 推送日志。
6. `publish_info` 默认 `False`——默认不往 UI info 写「已完成/已失败/已跳过/未处理的任务列表」四项，
   以完全保持旧逻辑的面板表现。需要这些字段时显式传 `publish_info=True`。

## 改动清单的注意事项

- **顺序即依赖**：前后任务共享同一个游戏界面状态，很多子任务隐含「上一个任务结束时停在某个界面」的前提。
  调顺序前先确认该子任务是否自带导航（多数以 `ensure_main` 兜底，但不绝对）。
- **开关键名会持久化**：新增任务项时，同名开关必须同时进 `default_config`，否则 GUI 上不会出现开关，
  用户也无法关闭它。
- **失败判定用返回值，不用异常**表示「今天这项做不了」；只有真正的异常（卡死、找不到界面）才抛。
- `self.daily_runner` 保存了实例引用，`final_summary` / `task_status` / `failure_details` 可供外部读取汇总。

## 与 ok-end-field 的差异（移植代码时注意）

ok-gf2 的 `DailyTaskRunner` 从 ok-end-field 的 `src/tasks/daily/daily_task_runner.py` 移植，已裁掉以下部分，
**不要把它们加回来**，否则会引用不存在的依赖：

| ok-end-field 的能力 | ok-gf2 现状 |
|---|---|
| `iter_multi_account_context` 多账户轮次 | **已移植**，见 `src/tasks/AccountMixin.py` |
| 按 `account_id` 分组的 `failure_details` | **已移植**（`{account_id: {任务名: 消息}}`） |
| `多账户独立配置` / `AccountOverrideMixin` | 无（依赖 ok-end-field 的 `account_scope_store` + 配置页，ok-gf2 无对应设施） |
| `resolve_account_id` 账号 ID 持久化 | 退化为「账号名即 ID」，需要稳定 ID 时重写 `AccountMixin.resolve_account_id` |
| `login_flow` 游戏内切号 | **需 ok-gf2 自行实现**，见下 |
| `shared_state_task_keys` / 帝江号状态 | 无 |
| 执行前 `send_key('shift')` | 无（那是终末地的奔跑切换键，加上会改变 ok-gf2 行为） |
| `仅退出游戏` / `发生异常时终止游戏` / `kill_game` | 无对应配置 |
| `register_config_groups` 下拉分组 | 无（ok-gf2 用 `default_config_group` + `sub_configs`） |

另外两边 `ok-script` 版本不同（ok-gf2 `2.0.5`，ok-end-field `2.0.7b1`），API 不一定互通。

## 多账户

多账户轮次、账号级配置覆盖、账号配置页的完整说明见 **`ok-script-multi-account` 技能**。
这里只记与编排器相关的部分：

- 编排器通过 `AccountMixin.iter_multi_account_context()` 拿轮次；任务类没接该 mixin 时退化为单轮。
- 每一轮：`set_current_account` → 记日志 → `login_flow(username)` → yield 给编排器跑任务。
- 切号失败（`login_flow` 抛异常）时**该轮不会归档**到 `per_round`——因为此时 `task_status` 还是上一轮的
  残留，补记会产生假数据。编排器用 `_round_entered` 标记区分「任务执行中异常」和「切号阶段异常」。
- 账号列表为空：一轮都不跑，最终状态置为「未开始」而不是留在「运行中」。
- `failure_details` 与 `per_round` 按 **`account_id`（`acc_xxxxxxxxxxxx`）** 分组，不是用户名；
  用户名在 `account_user` 字段里。

## alt 点击

ok-script 2.0.5 的 click 系列**都没有 `alt` 参数**，ok-gf2 在 `BaseGfTask` 上补齐：

| 方法 | 说明 |
|---|---|
| `click(x, y, ..., alt=True)` | 按住 alt 再点击，x 支持 Box / Box 列表 / 比例坐标 / 绝对坐标 |
| `click_with_alt(...)` | alt 点击本体：`send_key_down('alt')` → 等待 → `click` → `send_key_up('alt')` |
| `wait_click_ocr(..., alt=True)` | OCR 命中后走 alt 点击 |
| `wait_click_feature(..., alt=True)` | 特征命中后走 alt 点击 |

- `alt=False`（默认）时这些方法**直接透传父类实现**，不加任何改动，行为与之前完全一致。
- `click_with_alt` 的 `alt_hold_delay` 默认 0.5s（让游戏识别到修饰键）。
  `free_layer_click` 复用它但传 `alt_hold_delay=0`，以保持改造前「按下即点击」的时序。
- 松开 alt 放在 `finally` 里：点击抛异常时若不松开，后续所有按键都会被 alt 污染。
- 测试见 `tests/TestClickAlt.py`，用桩子类验证按键时序与 alt 分派，不需要设备。

## 汇总 txt

`src/tasks/daily_summary.py` 负责把 `final_summary` 落盘成 txt，由 `DailyTask.run_daily_finally()` 调用，
挂在 `run()` 的 `finally` 上——**异常中断也会写**，便于事后排查。

- 路径：`{tempfile.gettempdir()}/ok-gf2/一键日常/一键日常_YYYYmmdd_HHMMSS.txt`，同名冲突加 `_1` `_2` 后缀。
- 超过 7 天的旧文件自动清理（见 `DEFAULT_KEEP_DAYS`）。
- 开关：`生成汇总文件`（默认 True）、`自动打开汇总文件`（默认 False，避免每次跑完弹记事本）。
- 整个过程包在 try/except 里，写文件失败只记日志，不影响任务结果。

移植自 ok-end-field 的 `src/tasks/daily/finally_file.py`，差异：
移除 base64/XOR 解码、按 account_id 分组的失败明细（ok-gf2 是扁平字典）、邮件发送
（ok-gf2 通知走 `log_info(notify=True)`，无邮件通道）；文件名冲突后缀简化为 `_1`/`_2`。

两个容易踩的坑（已在代码里注释）：
- `per_round` 在正常结束时必然非空，所以「✅ 所有任务执行成功！」这类总体结论
  **不能**放在 `if not per_round:` 的 else 分支里，否则永远不显示。
- `per_round[].all` 是「未处理」剩余项，任务执行中会被逐个移除，
  总数必须用 `len(success) + len(failed) + len(skipped)` 算，不能用 `len(all)`。

## 验证

编排器与汇总模块都不依赖 ok-script 运行时，可以用桩对象做等价性验证：

```powershell
& ".\.venv\Scripts\python.exe" -m unittest tests.TestDailyTaskRunner -v
& ".\.venv\Scripts\python.exe" -m unittest tests.TestDailySummary -v
& ".\.venv\Scripts\python.exe" -m unittest tests.TestMultiAccount -v
```

`TestDailyTaskRunner` 覆盖：全成功顺序、`ensure_main` 参数、开关跳过、返回 False 记失败并继续、
异常中断并传播、谓词覆盖开关、`publish_info` 开关。

`TestDailySummary` 覆盖：成功/失败/异常/跳过四种报告的字段内容、旧文件清理、同秒冲突后缀、
缺 `tr` 时的兜底。

`TestMultiAccount` 覆盖：账号列表解析（含 `账号,密码` 旧格式与空行）、每个账号跑完所有任务、
失败按账号分组、账号列表为空直接结束、关闭多账户时单轮、`per_round` 记录账号信息、
`login_flow` 未实现时抛 `NotImplementedError`。

## 拆分与搬运

`src/tasks/daily/` 下的 mixin 是从单个 `DailyTask.py` 机械拆出来的。再做这类搬运时，
不要手抄方法体——用 AST 按方法名抽取源码片段再落盘，然后跑三项校验（见
`repository-workflow` 技能的「AST 机械拆分」小节）。手抄一定会漏掉模块级常量
（本项目就漏过 `activity_time_re`）或静默改掉缩进。

改动 `DailyTaskRunner`、`build_task_plan()` 或 `daily_summary.py` 后必须跑通它们。
`run_tests.ps1` 会遍历 `tests/*.py`，这两个测试无需设备即可运行。
