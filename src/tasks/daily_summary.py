"""日常任务执行情况汇总文件的生成。

移植自 ok-end-field 的 ``src/tasks/daily/finally_file.py``，按 ok-gf2 现状裁剪：

- 移除 base64/XOR 解码（与汇总无关）。
- 移除按 account_id 分组的失败明细：ok-gf2 无多账户，``failure_details`` 是
  ``{任务名: 失败消息}`` 的扁平字典。
- 移除邮件发送：ok-gf2 的通知走 ok-script 的 ``log_info(notify=True)``，没有邮件通道。
- 文件名冲突后缀简化为 ``_1`` / ``_2``。

目录结构：``{base_dir}/{app_name}/{task_name}/{task_name}_YYYYmmdd_HHMMSS.txt``
"""

from __future__ import annotations

import os
import time
import webbrowser
from datetime import datetime
from pathlib import Path

DEFAULT_KEEP_DAYS = 7


def get_software_name() -> str:
    """从全局配置读取软件名（gui_title）。应用未启动时 og.config 为 None，需兜底。"""
    try:
        from ok import og  # type: ignore

        return og.config.get("gui_title", "ok-gf2")
    except Exception:
        return "ok-gf2"


def iter_summary_candidates(base_name: str):
    """生成报告文件名候选序列，用于避免同一秒内重复创建导致覆盖。"""
    base_path = Path(base_name)
    stem = base_path.stem or base_path.name
    suffix = base_path.suffix if base_path.suffix else ".txt"

    yield f"{stem}{suffix}"

    index = 1
    while True:
        yield f"{stem}_{index}{suffix}"
        index += 1


def _build_account_id_to_user(per_round) -> dict[str, str]:
    """从 per_round 构建 account_id -> account_user 的映射，用于报告中显示账号名。"""
    id_to_user: dict[str, str] = {}
    if not isinstance(per_round, list):
        return id_to_user
    for item in per_round:
        account_id = str(item.get("account_id", "") or "").strip()
        account_user = str(item.get("account_user", "") or "").strip()
        if account_id:
            id_to_user[account_id] = account_user
    return id_to_user


def format_failure_details_by_account(per_round, failure_details: dict, translate=None) -> list[str]:
    """格式化按账号分组的失败明细。

    ``failure_details`` 结构为 ``{account_id: {任务名: 失败消息}}``；
    单账户模式下 ``account_id`` 为空字符串，此时不显示账号分组标题。
    """
    if not isinstance(failure_details, dict) or not failure_details:
        return []

    _tr = translate or (lambda s: s)
    id_to_user = _build_account_id_to_user(per_round)

    lines = [_tr("失败消息:")]
    for account_id, tasks_map in failure_details.items():
        if not isinstance(tasks_map, dict) or not tasks_map:
            continue
        if account_id:
            account_user = id_to_user.get(str(account_id), "")
            account_display = account_user or f"id:{account_id}"
            lines.append(f"  === {_tr('账号')}: {account_display} ===")
        for task_name, message in tasks_map.items():
            message_text = str(message).strip() if message is not None else ""
            lines.append(f"  - {_tr(task_name)} : {_tr(message_text) or _tr('未设置失败消息')}")
    lines.append("")
    return lines


def build_summary_lines(task, summary_info: dict) -> list[str]:
    """把 runner 的 final_summary 渲染成汇总文本行。"""
    task_name = getattr(task, "name", "未知任务")
    _tr = getattr(task, "tr", None) or (lambda s: s)

    status = summary_info.get("status", "")
    exception_text = summary_info.get("exception", "")
    current_task = summary_info.get("current_task", "")
    all_fail_tasks = summary_info.get("all_fail_tasks", [])
    per_round = summary_info.get("per_round") or []
    failure_details = summary_info.get("failure_details") or {}

    lines = [
        f"{_tr(task_name)}{_tr('执行情况汇总')} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 50,
        _tr("执行状态: {status}").format(status=_tr(status) if status else _tr("未知")),
        "",
    ]

    if exception_text:
        lines.extend([_tr("异常信息:"), f"  {exception_text}", ""])

    if current_task:
        lines.extend([_tr("当前正在执行的任务:"), f"  {_tr(current_task)}", ""])

    lines.extend(format_failure_details_by_account(per_round, failure_details, translate=_tr))

    # 总体结论：per_round 在正常结束时必然非空，因此不能放在 else 分支里，否则永远不显示
    if all_fail_tasks:
        lines.append("❌ " + _tr("失败任务统计:"))
        for entry in all_fail_tasks:
            # 多轮时元素为 (轮次, [任务名])，兼容旧的纯列表形式
            round_no, failed_tasks = entry if isinstance(entry, tuple) else (None, entry)
            prefix = f"  第{round_no}轮: " if round_no is not None else "  "
            lines.append(prefix + ", ".join(_tr(t) for t in failed_tasks))
        lines.append("")
    elif status == "完成":
        lines.append("✅ " + _tr("所有任务执行成功！"))
        lines.append("")

    for round_item in per_round:
        success = round_item.get("success", [])
        failed = round_item.get("failed", [])
        skipped = round_item.get("skipped", [])
        uncertain = round_item.get("uncertain", [])
        # 注意：per_round 里的 all 是「未处理」的剩余项，任务执行过程中会被逐个移除，
        # 因此总数必须由成功、失败、跳过、待核查四项统计相加，不能直接用 len(all)。
        total = len(success) + len(failed) + len(skipped) + len(uncertain)

        # 多轮或存在账号上下文时才打印轮次表头，单账户单轮保持简洁
        if len(per_round) > 1 or round_item.get("account_user") or round_item.get("account_id"):
            account_display = round_item.get("account_user") or (
                f"id:{round_item.get('account_id')}" if round_item.get("account_id") else _tr("无")
            )
            lines.append(
                _tr("--- 第 {round} 轮 (账号: {account}) ---").format(
                    round=round_item.get("round", ""), account=account_display
                )
            )

        lines.append(
            _tr("总任务数: {total} | 成功: {success} | 失败: {failed} | 跳过: {skipped}").format(
                total=total, success=len(success), failed=len(failed), skipped=len(skipped)
            )
        )
        lines.append("")
        if uncertain:
            lines.append(_tr("待核查任务:"))
            lines.append("  " + ", ".join(_tr(t) for t in uncertain))
            lines.append("")
        lines.append(_tr("成功任务:"))
        lines.append(f"  {', '.join(_tr(t) for t in success) if success else _tr('无')}")
        lines.append("")
        lines.append(_tr("失败任务:"))
        lines.append(f"  {', '.join(_tr(t) for t in failed) if failed else _tr('无')}")
        lines.append("")
        lines.append(_tr("跳过任务:"))
        lines.append(f"  {', '.join(_tr(t) for t in skipped) if skipped else _tr('无')}")
        lines.append("")

    return lines


def create_task_summary_report(
    task,
    base_dir: Path,
    summary_info: dict,
    keep_days: int = DEFAULT_KEEP_DAYS,
) -> Path:
    """把执行汇总写成 txt 并返回文件路径。

    Args:
        task: 任务实例（需要 ``.name``，可选 ``.tr``）。
        base_dir: 基础目录，通常是 ``tempfile.gettempdir()``。
        summary_info: ``DailyTaskRunner.final_summary``。
        keep_days: 保留历史文件的天数。

    Returns:
        创建的文件路径。

    Raises:
        RuntimeError: 候选文件名全部冲突，无法创建文件。
    """
    task_name = getattr(task, "name", "未知任务")
    app_name = get_software_name()

    target_dir = Path(base_dir) / app_name / task_name
    target_dir.mkdir(parents=True, exist_ok=True)

    # 清理超过保留天数的旧文件
    cutoff_time = time.time() - (keep_days * 24 * 3600)
    for old_file in target_dir.glob("*.txt"):
        try:
            if old_file.stat().st_mtime < cutoff_time:
                old_file.unlink()
        except Exception:
            pass

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{task_name}_{timestamp}.txt"
    content = "\n".join(build_summary_lines(task, summary_info))

    for candidate_name in iter_summary_candidates(base_name):
        candidate_path = target_dir / candidate_name
        try:
            with candidate_path.open("x", encoding="utf-8", newline="\n") as fp:
                fp.write(content)
            return candidate_path
        except FileExistsError:
            continue

    raise RuntimeError(f"无法创建{task_name}执行情况汇总文件")


def open_local_path_with_default_app(path: Path):
    """用系统默认程序打开本地文件，失败时回退到浏览器。"""
    normalized = Path(path).resolve()
    if os.name == "nt":
        try:
            os.startfile(str(normalized))  # noqa: S606
            return
        except OSError:
            pass
    webbrowser.open(normalized.as_uri())
