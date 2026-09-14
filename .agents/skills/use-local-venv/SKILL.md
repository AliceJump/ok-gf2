---
name: use-local-venv
description: Prefer the repository-local Python virtual environment for coding-agent work in ok-gf2. Use when running Python scripts, tests, py_compile, package installs, dependency checks, or any Python command; keep requirements.txt authoritative and avoid global Python drift.
---

# Use Local Venv

## Overview

ok-gf2 使用仓库内的 `.venv`，**没有** `pyproject.toml` / `uv.lock`，也不使用 `uv`。
依赖来源是仓库根的 `requirements.txt`（可由 `requirements.in` 生成）与 `requirements-dml.txt`（DirectML 变体）。

用 `.venv` 的解释器跑命令，保证与仓库依赖一致，而不是用全局 Python。

## Rule

- 除非脚本明确支持别的目录，否则一律在仓库根目录执行。
- 日常命令直接用 `.venv` 解释器，这是本仓库的标准入口：

  ```powershell
  & ".\.venv\Scripts\python.exe" -m unittest tests.TestOcr -v
  & ".\.venv\Scripts\python.exe" -m py_compile src/tasks/DailyTask.py
  & ".\.venv\Scripts\python.exe" -c "from src.tasks.DailyTask import DailyTask; print('ok')"
  ```

- 不要回退到全局 `python`。若 `.venv` 缺失，先按 `local_build.ps1` 的前两步重建：

  ```powershell
  & ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
  & ".\.venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
  ```

  若连 `.venv` 都没有，先 `python -m venv .venv` 再执行上面两步。
- `requirements.txt` 是依赖真源，安装依赖后若内容有变应同步提交它。不要手改由 `requirements.in` 生成的注释块。
- DirectML 相关改动要同时看 `requirements-dml.in` / `requirements-dml.txt`，不要只改主依赖文件。

## Tests

- 全量入口：`run_tests.ps1`（遍历 `tests/*.py`，逐个 `python -m unittest <path>`）。
  注意该脚本调用的是 `python`，执行前请确认 PATH 中的 `python` 就是 `.venv` 解释器，否则等价于用全局环境跑测试。
- 针对性 unittest：`& ".\.venv\Scripts\python.exe" -m unittest tests.TestOcr -v`。
- 编排器/纯逻辑改动可以写不依赖 ok-script 运行时的桩测试，见 `daily-task-orchestration` 技能。
- 保留并如实报告既有的独立失败，不要靠换解释器或换依赖把它藏掉。

## Packaging note

打包走 `local_build.ps1`：它会把 `src` 下 `.py` 临时改名为 `.pyx` 做 Cython 编译，再删掉中间产物。
因此**不要在 `src/` 放不能被 Cython 编译的语法**，也不要把只用于开发的脚本长期留在 `src/` 下。
