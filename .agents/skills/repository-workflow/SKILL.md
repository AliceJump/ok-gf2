---
name: repository-workflow
description: "Apply ok-gf2 repository-wide engineering rules. Use when committing or opening/editing a PR, handling Markdown through PowerShell, checking secrets, choosing commit style, running tests, reading runtime logs, changing dependency files, or performing broad automated source edits that need structural verification."
---

# Repository Workflow

## Scope

Use this skill for repository-wide rules that do not belong to a narrower domain skill. If a task also matches a specialized skill, load both; the specialized workflow controls its domain details.

## Project facts

- App: ok-gf2（少女前线 2 追放自动化），基于 PyPI `ok-script==2.0.5`。
- 任务注册入口：`src/config.py` 的 `onetime_tasks` 列表，形如 `["src.tasks.DailyTask", "DailyTask"]`。
  新增/重命名任务类必须同步改这里，否则 GUI 里不会出现。
- 任务源码扁平放在 `src/tasks/`（`BaseGfTask.py` / `DailyTask.py` / `WeeklyTask.py` / `ClearMapTask.py` ...），
  通用能力集中在 `src/tasks/BaseGfTask.py`。
- 运行时配置：仓库根 `configs/*.json`（用户数据，勿手改），`src/configs/*.json`（随包默认配置）。
- 运行时日志：`logs/ok-script.log`；另有 `src/logs/ok-script.log`（包内路径，排查时注意区分）。
- Python 环境与测试入口归 `use-local-venv` 技能管辖。

## Commit and PR checklist

1. 先 `git status --short --branch`，再看工作区 diff 与已暂存 diff。绝不要夹带无关改动。
2. 先跑针对性验证，影响面大的再跑全量测试。
3. **不要提交令牌、密码、私钥、PEM、凭据导出或含密钥的配置**。提交前检查 PowerShell 脚本与 workflow 里是否硬编码了带凭据的 URL。
4. 沿用仓库近期提交语言与 conventional 前缀：`fix:`、`feat:`、`docs:`、`refactor:`、`ci:`。
   ok-gf2 的习惯是前缀后跟中文简述并附 PR 号，例如 `fix(xunlu): 修复「领取巡录免费档」必然失败 (#69)`。
5. 变更持久化配置键名时必须同时加载 `ok-config-migration`。
6. 一个 PR 只承载一个功能或一项职责；混合职责的改动先拆开再推。
7. 分支基于远端 `master`：先 `git fetch origin`，从 `origin/master` 切出，落后时先 rebase。
8. `master` 的合入走 PR：历史提交均带 `(#nn)` 后缀，说明主分支改动经 PR 落地。不要从陈旧的本地 `master` 开 PR。

## 已知仓库内的凭据问题（勿扩散）

`local_build.ps1` 内硬编码了带用户名密码的 coding.net 推送地址（`https://<user>:<token>@e.coding.net/...`）。
这是既有问题，**不要复制到任何新脚本、日志、PR 描述或 issue 中**；清理它应作为独立 PR 处理，并同步轮换该凭据（凭据已进过版本库即视为泄露）。

## PowerShell Markdown safety

PowerShell 反引号在双引号字符串里是转义符。含代码反引号的 Markdown 经 `"..."` 传递会丢失反引号或引入 BEL（`^G`）之类的控制字符。

- Markdown 正文存进单引号字符串或单引号 here-string（`@' ... '@`）。
- 用 `gh pr create/edit --body $body` 传变量，不要把含反引号的 Markdown 直接写进双引号的 `--body`。
- 创建或编辑 PR 后拉取远端 body 与本地预期做逐字节比对；只搜反引号是否存在的子串检查不充分。

```powershell
$body = @'
Markdown containing `code`.
'@
gh pr create --base master --head $branch --title $title --body $body
$remoteBase64 = gh pr view $branch --json body --jq '.body | @base64'
$normalizedBody = $body.Replace("`r`n", "`n")
$localBase64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($normalizedBody))
if ($remoteBase64 -cne $localBase64) {
    throw "Remote PR body differs from the intended body"
}
```

## Windows PowerShell 5.1 encoding

- 含非 ASCII 文本且需兼容 Windows PowerShell 5.1 的 `.ps1` 必须存为 **UTF-8 with BOM**，否则 5.1 会按活动 ANSI 代码页解码源文件。
- `[Console]::OutputEncoding` 只管子进程/输出编码，不能修复源文件解码，不能替代 BOM。
- 纯 ASCII 的脚本保持无 BOM 的 UTF-8，除非仓库另有约定。
- 本仓库 `auto_release.ps1` 已按 UTF-8 BOM 处理，修改时保持 BOM 不被去掉（它同时设置了 `i18n.commitEncoding`/`logOutputEncoding`，用于避免 GitHub tag 中文乱码）。

## Broad automated edits

批量文本工具可能保留 Python 语法却删掉或复制了可执行语句。做批量 docstring、注解、格式化或源码重写时：

1. 先建立干净基线，或先记录改动前已存在的用户修改。
2. 对每个被改的 Python 文件做语法解析。
3. 按限定名（`Class.method`，不是裸方法名）与基线逐函数比对，标出非 docstring 可执行语句的减少。
4. 逐条复核被标记项；只有能被本次需求解释的删除才允许。
5. 跑针对性测试，提交前检查 `git diff --check` 与完整 diff。

`ast.parse` 对解码后带 BOM 的文本会报错；做结构比对时用 `utf-8-sig` 读取源文本。

## AST 机械拆分（把一个模块拆成多个 mixin）

把大文件按领域拆成多个 mixin 时，**不要手抄方法体**——手抄会漏掉模块级常量、静默改掉缩进或重排语句。
用 AST 抽取源码片段再落盘：

1. 用 `ast.parse` 拿到每个 `FunctionDef` 的 `lineno`/`end_lineno`，按原文件行切片复制（保持原缩进）。
   有装饰器时起点要取 `min(d.lineno for d in node.decorator_list)`，否则会丢掉装饰器。
2. **别忘了模块级赋值**（正则常量等）与模块级函数。只处理 `Import`/`FunctionDef` 会漏掉它们，
   而且漏掉后通常只在运行时才炸。
3. `ast.unparse(ast.Import(...))` 已自带 `import ` 前缀，不要再拼一次（会得到 `import import x`）。
4. 新文件的 import 可按「名字是否出现在搬运后的源码里」筛选，但**类声明里用到的基类 import 扫不到**
   （它们不在任何方法体里），必须强制保留。
5. 拆分前先把原文件备份到 `tmp/`，脚本写坏时能从备份重跑。

拆完必须跑三项校验，缺一不可：

```powershell
& ".\.venv\Scripts\python.exe" -c @'
import ast, builtins, symtable
from pathlib import Path

def collect(p):
    t = ast.parse(Path(p).read_text(encoding="utf-8"))
    return {n.name: (ast.unparse(n.args), ast.unparse(n).split(":", 1)[1].strip())
            for n in ast.walk(t) if isinstance(n, ast.FunctionDef)}

old = collect("tmp/backup/DailyTask.py.bak")
files = ["src/tasks/DailyTask.py"] + [str(p) for p in sorted(Path("src/tasks/daily").glob("*.py"))]
new, dupes = {}, []
for f in files:
    for k, v in collect(f).items():
        if k in new:
            dupes.append(k)
        new[k] = v

print("[1] 方法等价:", old == new, "| 原", len(old), "新", len(new))
print("    重复定义:", dupes or "无")
print("    丢失:", sorted(set(old) - set(new)) or "无")
print("    签名不一致:", [k for k in old if k in new and old[k][0] != new[k][0]] or "无")
print("    函数体不一致:", [k for k in old if k in new and old[k][1] != new[k][1]] or "无")

# [2] 未定义全局名：抓「常量没跟着搬走」这类只在运行时才炸的问题
bi = set(dir(builtins))
bad = 0
for f in files:
    st = symtable.symtable(Path(f).read_text(encoding="utf-8"), f, "exec")
    top = {s.get_name() for s in st.get_symbols()}
    for c in st.get_children():
        for sc in list(c.get_children()) + [c]:
            for s in sc.get_symbols():
                if s.is_global() and s.get_name() not in top and s.get_name() not in bi:
                    print("   [未定义]", f, sc.get_name(), "->", s.get_name())
                    bad += 1
print("[2] 未定义名:", bad)
'@

# [3] 真实导入 + 测试
& ".\.venv\Scripts\python.exe" -c "from src.tasks.DailyTask import DailyTask; print('import ok')"
& ".\.venv\Scripts\python.exe" -m unittest tests.TestDailyTaskRunner tests.TestMultiAccount -v
```

第 [2] 项是关键：`old == new` 只能证明「搬过去的没变」，证明不了「该搬的都搬了」。
本项目拆 `DailyTask` 时正是靠它抓出漏搬的模块级正则 `activity_time_re`。

## Completion report

报告改动范围、执行过的验证、既有的已知失败，以及是否真的执行了 commit/PR/push。命令没有成功结束，就不得描述成测试通过或推送成功。
