---
name: deploy
description: Commit completed ok-gf2 changes, create the next annotated version tag, and push the commit and tag to origin. Use when the user asks to deploy, release, publish a version, create or push a release tag, run `deploy` for a stable release, `deploy beta`, or `deploy alpha`.
---

# Deploy (ok-gf2)

## How release works here

- 发布远端是 `origin` = `https://github.com/AliceJump/ok-gf2.git`（另有 `Ranch007` / `peach322` 等协作者远端，**只推 `origin`**）。
- 默认分支 `master`，历史提交均带 `(#nn)` 后缀——主分支改动经 PR 落地。
- **`.github/workflows/build.yml` 只在推送 `v*` tag 时触发**（Windows runner + Cython 打包）。
  换句话说：打 tag 并推送 = 触发构建发布，这是本仓库的发布开关。
- 版本号形如 `v1.2.72`。`mirrorchyan_uploading.yml` / `mirrorchyan_release_note.yml` 分别由
  `workflow_dispatch` 与 release 事件驱动，不在 deploy 流程里手动触发。

## Variants

- `deploy` / `deploy release` → 稳定版 tag，如 `v1.2.73`。
- `deploy beta` → 如 `v1.2.73-beta.1`。
- `deploy alpha` / `release alpha` → 如 `v1.2.73-alpha.1`。

稳定版递增最新稳定 `vMAJOR.MINOR.PATCH` 的 patch。alpha / beta 各自独立编号：

- 已存在未发布的预发布线则递增后缀，如 `v1.2.73-beta.1` → `v1.2.73-beta.2`。
- 若最新稳定版之后还没有预发布，则从下一个 patch 的 `.1` 开始，如稳定 `v1.2.72` → `v1.2.73-beta.1`。
- 基版本已发布的预发布线视为关闭，从下一个 patch 重新开始。

用本技能 `scripts/next_tag.py` 计算（它会忽略不符合上述格式的 tag）：

```powershell
& ".\.venv\Scripts\python.exe" .agents\skills\deploy\scripts\next_tag.py release --remote origin
& ".\.venv\Scripts\python.exe" .agents\skills\deploy\scripts\next_tag.py beta --remote origin
& ".\.venv\Scripts\python.exe" .agents\skills\deploy\scripts\next_tag.py alpha --remote origin
```

## Workflow

1. `git status --short --branch`，并查看相关 diff。**不要夹带无关改动**；提交内容有歧义就先确认。
2. 确认改动可发布：跑针对性测试（见 `use-local-venv`）。验证失败就停在打 tag 之前，除非用户明确接受。
3. 看最近一条非 merge 提交的 subject，决定新提交的语言（中文就中文，英文就英文）：

   ```powershell
   git log --no-merges -1 --format=%s
   ```

4. **先算 tag 再提交**。`--remote origin` 会同时考虑本地与远端已有 tag，避免覆盖：

   ```powershell
   & ".\.venv\Scripts\python.exe" .agents\skills\deploy\scripts\next_tag.py release --remote origin
   ```

   远端 tag 查询失败就停手，不要凭陈旧的本地 tag 猜版本号。
5. 只暂存目标文件，检查后再提交：

   ```powershell
   git add -- <intended-files>
   git diff --cached --stat
   git diff --cached
   git commit -m "<message>"
   ```

   不要造空提交，除非用户明确要求。
6. 在新提交上打**带注释**的 tag：

   ```powershell
   git tag -a "<calculated-tag>" -m "<calculated-tag>"
   git show --no-patch --decorate HEAD
   ```

7. 推送（除非用户只要本地）：

   ```powershell
   # 在 master 上：只推 tag，不推分支
   git push origin "<calculated-tag>"
   # 在其它分支上：提交与 tag 一起推
   git push origin HEAD "<calculated-tag>"
   ```

   推送成功后再报告发布完成。推 `v*` tag 会触发 `build.yml`，到 GitHub Actions 页面确认构建结果。

8. 报告提交 subject、tag、远端，以及推送是否成功。

## Guardrails

- 绝不重写、移动或删除已有 tag。
- 选提交语言时忽略 merge 提交。
- 本地打了 tag 不等于发布成功；推送成功与 CI 构建结果要分开报告。
- 用户明确要求仅本地操作时不要推送。
- 不要绕过 PR 直接把发布提交推到 `master`；先经 PR 合入，再在合并结果上打 tag。
- `auto_release.ps1` 是仓库里既有的本地发版脚本（内含版本上限校验与 UTF-8 编码设置）。
  本技能用 `next_tag.py` 计算版本号；若用户明确要求走 `auto_release.ps1`，按其脚本执行，
  但注意它里面有硬编码的推送凭据，不要复制或打印出来（见 `repository-workflow`）。
