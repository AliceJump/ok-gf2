# Skills

本文件仅负责技能发现与路由，不重复定义技能中的具体流程、规则或实现细节。当任务命中下列任一场景时，先读取对应的 `SKILL.md`，再按技能文件中的流程执行。一个任务可以同时适用多个 Skill；应读取所有相关 Skill，并综合遵循其约束。

| Skill | 适用场景 | 路径 |
|---|---|---|
| `repository-workflow` | 提交/PR、安全检查、PowerShell Markdown 引号与 BOM、测试与日志入口、批量改码验证 | `.agents/skills/repository-workflow/SKILL.md` |
| `use-local-venv` | 运行 Python、测试、py_compile、依赖检查或安装，统一使用仓库 `.venv`（本项目无 uv） | `.agents/skills/use-local-venv/SKILL.md` |
| `ok-script-tasks` | 创建、修改、注册或审阅 ok-script 任务类（继承 `BaseGfTask`、配置 UI、注册到 `src/config.py`） | `.agents/skills/ok-script-tasks/SKILL.md` |
| `daily-task-orchestration` | 日常任务的编排：增删改 `build_task_plan()` 的任务项、顺序与开关、失败判定与汇总 | `.agents/skills/daily-task-orchestration/SKILL.md` |
| `ok-script-i18n` | gettext UI 文案、`i18n/*/LC_MESSAGES/` 的 ok.po / ocr.po 同步与编译、收集池防污染 | `.agents/skills/ok-script-i18n/SKILL.md` |
| `ok-config-migration` | 修改持久化配置键名并安全迁移用户数据（ok-script 2.0.5 无内建迁移机制） | `.agents/skills/ok-config-migration/SKILL.md` |
| `deploy` | 提交完成改动、计算并创建 stable/beta/alpha tag、推送发布远端 | `.agents/skills/deploy/SKILL.md` |
| `github-workflows` | 编辑或排查 GitHub Actions YAML、权限、actionlint 与解析期失败 | `.agents/skills/github-workflows/SKILL.md` |

## 项目速览

- ok-gf2：少女前线 2 追放自动化，基于 PyPI `ok-script==2.0.5`，依赖在 `requirements.txt`。
- 任务源码：`src/tasks/`，通用基类 `src/tasks/BaseGfTask.py`。
- 任务注册：`src/config.py` 的 `onetime_tasks`。
- 日常任务编排：`src/tasks/DailyTaskRunner.py`（编排器）+ `src/tasks/DailyTask.py` 的 `build_task_plan()`（清单）。
- 日常任务执行逻辑：按领域拆在 `src/tasks/daily/` 下的 5 个 mixin。
- 多账户：`src/tasks/AccountMixin.py`（轮次与账号列表；`login_flow()` 待实现）。
- 执行汇总：`src/tasks/daily_summary.py`。
- alt 点击：`BaseGfTask` 上覆写的 `click` / `click_with_alt` / `wait_click_ocr` / `wait_click_feature`。
- 译文：`i18n/en_US`、`i18n/zh_CN` 两个 locale。
- 发布：推送 `v*` tag 触发 `.github/workflows/build.yml`。

## 刻意未迁移的 ok-end-field 技能

同源仓库 `ok-end-field` 的 `.agents/skills/` 里还有若干技能，本次**未**迁移，原因如下，需要时再针对性引入：

- `ok-script-ocr-lang` —— ok-gf2 没有 `assets/lang/*.json` 与 `self.lang`，不适用。
- `ok-script-pr-review` —— ok-gf2 未接入 CodeRabbit，无对应配置。
- `github-rulesets` / `github-actions-performance` —— 尚未确认本仓库启用了 ruleset 或存在 Actions 性能问题。
- `wiki-skill-sync` —— 终末地干员技能数据同步，与少女前线 2 无关。
- `ok-script-codegen` —— 需要针对 ok-gf2 的基类与特征集校准后才可复用。
- `log-watcher-ops` —— 属对方私有运维，不随仓库发布。
