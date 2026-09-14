---
name: github-workflows
description: Configure and troubleshoot GitHub Actions workflow files in ok-gf2 — YAML syntax traps (single-line run with :word:), diagnosing "Invalid workflow file" / jobs:0 runs that never start, and validating YAML before push. Use when editing .github/workflows/*.yml or fixing a workflow that fails at parse time.
---

# GitHub Workflows (ok-gf2)

## Current workflows

| 文件 | 触发 | 说明 |
|---|---|---|
| `build.yml` | `push: tags: v*` | Windows runner，Cython 打包。打 tag 即触发发布构建 |
| `download_stats.yml` | `workflow_dispatch` + 每日 cron | 更新下载统计并回写仓库 |
| `mirrorchyan_release_note.yml` | `workflow_dispatch` + `release: edited` | 同步 release note 到 MirrorChyan |
| `mirrorchyan_uploading.yml` | `workflow_dispatch`（带 `tag` 入参） | 上传产物到 MirrorChyan |

改动 `build.yml` 等于改动发布链路，谨慎对待（`deploy` 技能依赖它）。

## 1. YAML traps

### `--only-binary :all:` 写在单行 `run:` 里会破坏解析

```yaml
# BAD — `:all:` 被解析成 mapping → "Invalid workflow file ... error in your yaml syntax on line 52"，jobs: 0
run: pip install --only-binary :all: -r requirements-docs.txt
# GOOD — 整体加引号
run: 'pip install --only-binary :all: -r requirements-docs.txt'
```

- 单行 `run: <value>` 里出现 `:word:`（冒号后紧跟内容）会被 GitHub workflow 解析器当成 mapping，
  结果是 workflow 根本不启动。这是 GitHub 解析器的行为；给整个单行 `run` 值加引号即可。
- 块标量（`run: |` 多行）里 `:all:` 是纯文本，安全。

### 推送前必须做两步校验

PowerShell 不会可靠地展开原生命令的通配符，所以显式枚举两种扩展名再传路径：

```powershell
$workflowFiles = @(
    Get-ChildItem -LiteralPath ".github/workflows" -File |
        Where-Object { $_.Extension -in ".yml", ".yaml" }
)
if ($workflowFiles.Count -eq 0) {
    throw "No workflow YAML files found"
}
$workflowPaths = @($workflowFiles.FullName)

# 1) 通用 YAML 语法
& ".\.venv\Scripts\python.exe" -c 'import pathlib, sys, yaml; [yaml.safe_load(pathlib.Path(p).read_text(encoding="utf-8-sig")) for p in sys.argv[1:]]; print(f"parsed {len(sys.argv) - 1} file(s)")' @workflowPaths
if ($LASTEXITCODE -ne 0) { throw "Workflow YAML parsing failed" }

# 2) GitHub Actions 结构、表达式与上下文
$actionlint = Get-Command actionlint -ErrorAction SilentlyContinue
if (-not $actionlint) { throw "actionlint is required; install it before validating workflows" }
& $actionlint.Source @workflowPaths
if ($LASTEXITCODE -ne 0) { throw "actionlint failed" }
```

通用 `yaml.safe_load` 抓不到 `matrix.os` 这类未定义上下文；`actionlint` 不可用要当作校验失败报告，不能跳过。

## 2. 诊断 "workflow file issue" / jobs: 0

- `gh run view <id>` 显示 `This run likely failed because of a workflow file issue` 且 run 的 **jobs 为 0**
  → workflow 从未启动，是文件解析问题，不是某个 step 失败。
- 查 job 数：`gh api repos/AliceJump/ok-gf2/actions/runs/<id>/jobs` → 若 `jobs: []` 即确认。
- 从 GitHub 报错里定位行号（如 "error in your yaml syntax on line 52"），修好后推送重新触发。

## 3. 权限与凭据

- 创建 PR 的 workflow 需要 `pull-requests: write`（还要推送分支时再加 `contents: write`）。
- `actions/checkout` 上 `persist-credentials: false` 可避免持久化的 `github.token` 覆盖后续 `git push` 的凭据。
- 本仓库的 workflow 用到 `MirrorChyan` 等第三方服务的 token，只放在 Secrets，不要出现在 YAML 明文或日志里。
