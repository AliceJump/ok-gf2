---
name: ok-script-tasks
description: Create and modify automation task classes for the ok-script Python library in ok-gf2, including BaseTask one-time tasks, TriggerTask background tasks, task config UI metadata, registration in src/config.py, and bilingual English/Chinese task behavior. Use when creating, refactoring, reviewing, or explaining ok-gf2 tasks.
---

# OK Script Tasks (ok-gf2)

## Overview

在 ok-gf2 中创建或修改基于 PyPI `ok-script==2.0.5` 的任务类。先看本仓库的既有约定，再套用通用 `ok-script` 知识。

更深入的内容读：

- `references/task-api.md` —— 任务生命周期、配置、执行器语义、GUI、双语规则（通用 ok-script）。
- `references/templates.md` —— 一次性任务、触发任务、feature/OCR、注册的可复用模板。
- `$daily-task-orchestration` —— 日常（每日任务）这种「多子任务串联」场景的编排器用法。
- 需要新增/同步 gettext 译文时用 `$ok-script-i18n`。

## ok-gf2 的本地约定

- **项目基类**：`src/tasks/BaseGfTask.py` 的 `BaseGfTask`。新任务优先继承它，不要直接继承 `BaseTask`。
  它提供 `ensure_main`、`skip_dialogs`、`auto_battle`、`wait_pop_up`、`fast_combat`、`loop_click_ocr` 等本游戏专用能力。
- **目录**：任务类扁平放在 `src/tasks/`，不分子目录。
- **注册**：`src/config.py` 的 `onetime_tasks` 列表，形如 `["src.tasks.DailyTask", "DailyTask"]`。
  新增/重命名/移动任务类必须同步修改，否则 GUI 不显示。
- **配置键是中文**：ok-gf2 的 `default_config` 键名就是中文（如 `"自动刷体力"`、`"当前物资关卡名称"`），
  与 `configs/*.json` 中持久化的字段一一对应。改键名属于高风险操作，见 `$ok-config-migration`。
- **配置分组**：用 `self.default_config_group`（父键 → 子键列表）+ `self.config_type[父键] = {'sub_configs': {True: 子键}}`
  实现折叠展开，`DailyTask._init_default_config_group()` 是范式。
- **没有 assets/lang**：ok-gf2 不使用 `assets/lang/*.json` 与 `self.lang` OCR 语言资源，
  OCR 匹配文本直接写在代码里（`pop_ups`、`stamina_re` 等常量从 `BaseGfTask` 导入）。

## Workflow

1. 先看 `src/tasks/` 下既有任务与 `src/config.py` 注册方式，优先复用项目基类与既有 helper。
2. 决定任务类型：
   - 用户手动触发、跑完即停 → `BaseTask`（实际用 `BaseGfTask`）。
   - 后台反复检查 → `TriggerTask`。ok-gf2 目前只注册 `onetime_tasks`，新增 trigger 任务需同时加 `trigger_tasks` 配置项。
3. 在 `__init__` 里设置元数据：`name`、`description`、`default_config`、`config_description`、`config_type`、
   `supported_languages`、图标、分组、调度开关（如 `support_schedule_task`）。
4. 实现 `run()`，拆成小步且可观测。优先用 `self.log_info`、`self.log_warning`、`self.info_set`、
   `self.wait_until`、`self.next_frame`、`self.sleep`、`self.click_relative`、`self.find_one`、
   `self.wait_click_feature`、`self.ocr`、`self.wait_ocr`、`self.wait_click_ocr`。
5. 在 `src/config.py` 注册。
6. 若任务有用户可见文案，用 `$ok-script-i18n` 同步 `i18n/*/LC_MESSAGES/ok.po` 并编译 `.mo`。
7. 验证：至少 `& ".\.venv\Scripts\python.exe" -c "from src.tasks.XxxTask import XxxTask"` 能导入；
   能脱离设备执行的逻辑要补桩测试。

## Bilingual Output

- 用中文回答；代码注释与日志以中文为主，关键处可附简短英文。
- `default_config` 键名是中文且会持久化成 JSON 字段，保持稳定；把中文帮助放在 `config_description`。
- OCR 匹配文本按项目当前活跃语言给：ok-gf2 的 i18n 目录实际只有 `en_US` 与 `zh_CN`。
- `supported_languages` 只在需要按语言隐藏任务时使用；为空表示所有语言可见。

## Config UI: conditional visibility and numeric ranges

`self.config_type[key]` 支持额外元数据，由 `ok/core/config_schema.py` 与 Qt 卡片共同解析。

- **`sub_configs`** —— 按父项取值显示子项（ok-gf2 的主力用法）：

  ```python
  self.default_config_group.update({"购买免费礼包": ["商店心愿单购买"]})
  self.config_type.update({"购买免费礼包": {'sub_configs': {True: ["商店心愿单购买"]}}})
  ```

  规则是「父值 → 子键列表」。子项只在父项当前值命中映射的键时可见；没有对应条目（如 `False`）则全部隐藏。
  子项自身也可以是父项，形成嵌套折叠。父项必须是会发出变更信号的控件：bool → `SwitchButton`、`drop_down` 或多选。

- **`min` / `max`** —— Qt 上只对 **int** 默认值生效（bounded `SpinBox`）；`float` 默认值会变成 `DoubleSpinBox` 并忽略这两个键。
  headless/web schema 仍会输出 `minimum` / `maximum`。需要 Qt 侧强制边界时就用 int 默认值，内部再转 float。

- 显式 `config_type[key]["type"]` 优先；缺省时按**默认值类型**推断控件：
  `bool` → switch，`int` → SpinBox，`float` → DoubleSpinBox，`list` → 列表编辑器。
  因此默认值的类型要刻意选。

- `drop_down` 要配 `options`，例如 `self.config_type["体力本"] = {'type': "drop_down", 'options': self.stamina_options}`。

- 配置键与 `config_description` 是用户可见文案，要走 gettext（见 `$ok-script-i18n`）。

## Essential Rules

- 先 `super().__init__(*args, **kwargs)`，再改任务字段。
- 不要绕过 `Config`：默认值放 `self.default_config`，取值一律 `self.config.get(...)`，且要在配置加载完成后再读。
- `TriggerTask` 要显式设置 `default_config['_enabled']`，并用 `trigger_interval` 避免高频轮询。
- 触发任务只有真正处理了事情才返回真值；返回假值让执行器继续扫描其他触发任务。
- 一次性任务正常跑完即可，执行器会在 `run()` 返回后禁用它。
- 少用固定 `sleep`，状态相关的等待用 `wait_until` / `wait_ocr` / `wait_click_feature`。
- 改 `run()` 里的子任务顺序或开关语义属于行为变更，必须与用户确认；前后任务往往存在界面前提依赖。
