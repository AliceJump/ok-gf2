---
name: ok-config-migration
description: Rename persisted config keys in ok-gf2 tasks without losing user data. Use when modifying default_config key names, config group keys, or option value strings in a task class — configs/*.json holds user runtime data and ok-script 2.0.5 has no built-in key migration, so a rename needs a manual, ordered procedure.
---

# OK Script Config Key Migration (ok-gf2)

## Why this skill exists

`configs/` 下的 JSON 是用户运行时数据（例如 `configs/DailyTask.json` 存着账号、体力本选择、各项开关）。
`default_config` 的键名一旦改动，旧键对应的用户值会被静默丢弃——用户表现为「设置莫名其妙被重置」。

**ok-gf2 依赖的 ok-script 2.0.5 没有内建的配置键迁移机制**（ok-end-field 那套
`config_key_migrations` + `migrate_config_file_keys` 在 ok-gf2 里不存在）。因此改名必须按下面的顺序手工完成。

## Workflow（严格顺序）

1. **先备份**：把要改的 `configs/<任务名>.json` 复制一份到 `tmp/`，改名失败时可回滚。
2. **确认影响面**：搜索代码里该键名的所有引用——`default_config`、`config_description`、
   `default_config_group`（父键与子键列表）、`config_type` 的 `sub_configs`、以及 `run()` 里的 `config.get(...)`。
3. **同一次提交里完成三件事**，不要分步部署：
   - 在任务类里把旧键改名；
   - 同步 `default_config_group` 与 `config_type` 里对旧键的引用；
   - 若旧键是某个 `sub_configs` 的父键，子键列表要跟着搬过去。
4. **迁移用户数据**：用脚本把 `configs/<任务名>.json` 里的旧键改名为新键并保留取值；
   旧键若仍留在文件里，ok-script 会因为不在 `default_config` 中而忽略它。
5. **同步 i18n**：`i18n/*/LC_MESSAGES/ok.po` 的 `msgid` 必须与代码里的键名完全一致，改键名就要改 msgid：

   ```powershell
   & ".\.venv\Scripts\python.exe" .agents\skills\ok-script-i18n\scripts\task_i18n_helper.py check --i18n i18n
   & ".\.venv\Scripts\python.exe" .agents\skills\ok-script-i18n\scripts\task_i18n_helper.py compile --i18n i18n
   ```

6. **同步文档**：搜索 `docs/`（`日常任务.md`、`周常任务.md` 等）里的旧键名并更新。
7. **验证**：导入模块确认无语法/引用错误，再检查 GUI 里新键能正常读写。

```powershell
& ".\.venv\Scripts\python.exe" -c "from src.tasks.DailyTask import DailyTask; print('ok')"
```

## 数据已丢失时的恢复

- `logs/ok-script.log` 在 DEBUG 级别会记录每次运行的完整配置（形如 `Config:init self.config = {...}`）。
- 从仍包含旧键名的最后一条日志里取回用户值，手动写回 `configs/<任务名>.json`。
- 下一次运行的日志里确认恢复生效。

## Guardrails

- 不要为了「命名更好看」改键名。键名是持久化契约，能不改就不改。
- 不要在未备份的情况下改 `configs/` 下的用户数据文件。
- 不要把 `configs/` 的用户数据提交进仓库（注意 `.gitignore` 的覆盖情况）。
- 改名涉及的任务若被定时任务（`src/scheduler/`）引用，一并检查缓存文件（如 `configs/schedule_tasks_cache.json`）。
