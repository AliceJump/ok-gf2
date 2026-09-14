---
name: ok-script-i18n
description: Add, sync, repair, and compile gettext translations for ok-gf2 task classes and task metadata. Use when translating task names, descriptions, default_config keys or values, config_description help text, config_type options, or debugging i18n catalog pollution.
---

# OK Script i18n (ok-gf2)

## Overview

ok-gf2 的译文目录是 `i18n/<locale>/LC_MESSAGES/`，每个 locale 下有两个域：

- `ok.po` / `ok.mo` —— GUI 与任务元数据（任务名、`default_config` 键名与字符串值、`config_description`、下拉选项）。
- `ocr.po` / `ocr.mo` —— OCR 匹配文本（`match` 参数用到的字符串）。

当前 locale 只有 **`en_US` 与 `zh_CN`** 两个。不要假设存在 `zh_TW`。

本技能配合 `$ok-script-tasks`：先用任务技能实现行为并识别用户可见文案，再用本技能同步并编译目录。

## Workflow

1. 读目标任务文件，收集用户可见元数据：
   - `self.name`、`self.description`
   - `self.default_config` 的键名与字符串值（ok-gf2 的键名是中文，也要进目录）
   - `self.config_description` 的字符串值
   - `self.config_type` 里 `drop_down` / `multi_selection` / `button` 的选项字符串
2. 用 `ls i18n/*/LC_MESSAGES/ok.po` 发现 locale，不要硬编码语言列表。
3. 检查每个源串是否已存在于**每个** locale 的目录。
4. 缺失的补 `msgid`，保留已有 `msgstr`，除非用户要求改译文。
5. 编译所有改动过的 `.po` 为 `.mo`。
6. 校验目录语法与重复 `msgid`。

## Helper Script

脚本依赖 `polib`，已在 `requirements-dev.txt` 中声明。若 `.venv` 里没装，先补：

```powershell
& ".\.venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
```

```powershell
& ".\.venv\Scripts\python.exe" .agents\skills\ok-script-i18n\scripts\task_i18n_helper.py scan --task src\tasks\DailyTask.py
& ".\.venv\Scripts\python.exe" .agents\skills\ok-script-i18n\scripts\task_i18n_helper.py check --i18n i18n
& ".\.venv\Scripts\python.exe" .agents\skills\ok-script-i18n\scripts\task_i18n_helper.py compile --i18n i18n
```

扫描器覆盖字面量赋值与 `.update(...)` 调用，包括 `self.config_type["key"] = {...}` 这种形式。
它只是辅助：经常量、导入、f-string、推导式、helper 函数构造出来的值仍要人工核对。

`check` 校验重复键、空译文、占位符一致性与跨 locale 键集合一致性；`compile` 之前先跑它。

### 合并冲突的目录（git merge / stash pop）

同一个 `ok.po` 两边都改时，文本 `.po` 可能合并成功但二进制 `.mo` 冲突。
先合并两侧 `.po` 再重新编译。`scripts/merge_po.py` 按 `(msgctxt, msgid, msgid_plural)` 归并、保留条目元数据、
拒绝重复键；真实 git 冲突必须显式传 `--prefer ours` 或 `--prefer theirs`（git 导出的文件 mtime 不可信，
默认的 `newer` 策略不适用）。

```powershell
# git show :2:path (ours), git show :3:path (theirs)
# PowerShell 5.1 的 > 重定向会写 UTF-16LE，polib 按 UTF-8 解码会失败，必须显式 utf8
git show :2:i18n/zh_CN/LC_MESSAGES/ok.po | Out-File -Encoding utf8 "$env:TEMP\ours.po"
git show :3:i18n/zh_CN/LC_MESSAGES/ok.po | Out-File -Encoding utf8 "$env:TEMP\theirs.po"
& ".\.venv\Scripts\python.exe" .agents\skills\ok-script-i18n\scripts\merge_po.py "$env:TEMP\ours.po" "$env:TEMP\theirs.po" --output i18n/zh_CN/LC_MESSAGES/ok.po --prefer ours --compile
```

合并完所有 locale 后跑 `check` 确认没有重复 `msgid`。

## Catalog Rules

- `msgid` 必须与代码里用的源串**完全一致**，包括全角标点与 `{占位符}`。
- 目录没排序时，新条目追加到末尾附近。
- 除非用户明确要求，否则不要加纯日志字符串；重点是 GUI 可见的任务元数据、配置标签、选项与帮助文本。
- `msgstr` 为空只允许在该 locale 有意回退到源语言时。
- 尽量保留译者注释、标记、历史 msgid 与条目顺序。
- 改完 `.po` **必须**编译 `.mo`。

### 行尾

Windows 上 `polib.POFile.save()` 与 `Path.write_text()` 默认 `newline=None`，会把 `\n` 转成 CRLF，
可能让整个文件在 diff 里显示为全量变更。程序化写入后按需归一化回仓库既有行尾，并用
`git diff --stat` 确认没有产生整文件改写。

## Translation Guidance

- UI 文本求简洁，不要逐字硬译。
- 占位符、代码依赖的标点、热键名保持不变。
- 配置键会持久化为 JSON 字段，保持稳定；翻译的是目录里的显示条目，不是 Python 里的键名。
- 选项列表要逐个翻译。

## Collection-Pool Safety

Debug 模式会把 `App.tr(key)` 的输入记进 `to_translate`；把运行时数据喂给 `tr()` 会污染生成的 PO 目录。

- 翻译输入必须是稳定模板：`self.tr("固定文本")` 或 `self.tr("模板 {value}").format(...)`。
  禁止 `tr(f"...{运行时值}...")`，也禁止先拼接运行时值再 `tr()`。
- 用户输入的动态下拉值不可翻译，不要把它们送进 `tr()`。
- 带变化值的消息先翻译外层稳定模板再 `.format(...)`；只翻译已知的枚举/配置标签，
  不翻译 OCR 输出、账号名等未知运行时文本。

## 与其它技能的边界

- ok-gf2 **没有** `assets/lang/*.json` 与 `self.lang`，OCR 匹配文本直接写在代码里，
  因此不涉及 ok-end-field 那套 lang JSON 体系。
- 任务编排（任务清单、失败判定）归 `$daily-task-orchestration`，与本技能无关。
