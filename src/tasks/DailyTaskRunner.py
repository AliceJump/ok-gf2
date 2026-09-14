"""DailyTask 的编排执行器。

移植自 ok-end-field 的 ``src/tasks/daily/daily_task_runner.py``，按 ok-gf2 的现状做了裁剪。
保留的是「编排骨架」：任务清单声明、四态统计、失败标记与截图、异常兜底与汇总、
按账号分组的轮次执行。

相对 ok-end-field 移除的部分（ok-gf2 不具备对应能力或会改变行为）：
- ``send_key('shift')``：终末地的奔跑切换键，ok-gf2 原有逻辑没有这一步，加上会改变行为。
- ``仅退出游戏`` / ``发生异常时终止游戏`` / ``kill_game``：ok-gf2 无此配置。
- ``register_config_groups`` 下拉分组：ok-gf2 用 ``default_config_group`` + ``sub_configs``。
- ``shared_state_task_keys`` 与帝江号状态：终末地专有。

沿用 ok-gf2 原有约定的部分：
- 每个任务项执行前调用 ``ensure_main(recheck_time=2, time_out=90)``。
- ``ensure_main`` 作为任务项时不做开关判定，恒执行。
- 任务函数返回 ``False`` 记为失败并继续后续任务；抛出异常则中断并向外传播。

多账户：``iter_multi_account_context`` 由 ``AccountMixin`` 提供（见 ``src/tasks/AccountMixin.py``），
登录切换逻辑 ``login_flow()`` 需由 ok-gf2 自行实现。任务类没接该 mixin 时，编排器退化为单轮执行。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

TaskItem = tuple[str, Callable[[], object]]
# 可选的第三元素：开关谓词。提供时替代默认的 config.get(key) 判断（例如多开关 OR 逻辑）。
TaskItemWithSwitch = tuple[str, Callable[[], object], Callable[[], bool]]

# 不做开关判定、恒执行的内置任务项。
ALWAYS_RUN_KEYS = ("ensure_main",)

# 四态到 UI info 键的映射，仅在 publish_info=True 时写入。
_STATUS_INFO_MAP = (
    ("failed", "已失败的任务列表"),
    ("success", "已完成的任务列表"),
    ("skipped", "已跳过的任务列表"),
    ("all", "未处理的任务列表"),
)


def _new_task_status(task_items: Iterable[TaskItem | TaskItemWithSwitch]) -> dict[str, list[str]]:
    return {"success": [], "failed": [], "skipped": [], "all": [item[0] for item in task_items]}


class DailyTaskRunner:
    """按任务清单顺序执行日常任务，并汇总每项的成败与跳过情况。"""

    def __init__(
        self,
        task,
        task_items: Iterable[TaskItem | TaskItemWithSwitch],
        ensure_main_kwargs: dict | None = None,
        publish_info: bool = False,
    ):
        """
        Args:
            task: DailyTask 实例，执行器通过它调用 log_info / info_set / ensure_main / screenshot。
            task_items: 任务清单，元素为 (任务名, 执行函数) 或 (任务名, 执行函数, 开关谓词)。
            ensure_main_kwargs: 传给 task.ensure_main 的参数，默认沿用 ok-gf2 原有的
                ``recheck_time=2, time_out=90``。
            publish_info: 是否把四态写入 UI info。默认关闭，以完全保持旧逻辑的 UI 表现；
                开启后会在面板上多出「已完成/已失败/已跳过/未处理的任务列表」四项。
        """
        self.task = task
        self.task_items = list(task_items)
        self.ensure_main_kwargs = dict(ensure_main_kwargs or {"recheck_time": 2, "time_out": 90})
        self.publish_info = publish_info
        self.task_status = _new_task_status(self.task_items)
        self.current_task_key: str | None = None
        # {account_id: {任务名: 失败消息}}；单账户模式下 account_id 为空字符串
        self.failure_details: dict[str, dict[str, str]] = {}
        self.failure_screenshot_tasks: set[str] = set()
        self.final_summary: dict = {
            "status": "未开始",
            "actual_repeat_total": 0,
            "all_fail_tasks": [],
            "per_round": [],
            "exception": "",
            "current_task": "",
            "failure_details": self.failure_details,
        }
        self._current_round_index: int | None = None
        self._current_repeat_total: int = 0
        self._rounds_executed: int = 0
        # 轮次是「切号成功后」才 yield 出来的，切号失败时并未真正进入该轮。
        # 用这个标记区分「任务执行中异常」和「切号阶段异常」，避免用上一轮的残留状态补记一条假的轮次。
        self._round_entered: bool = False

    def _tr(self, message: str) -> str:
        """翻译失败时退回原文，避免编排器把任务拖崩。"""
        try:
            return self.task.tr(message)
        except Exception:
            return message

    def _is_multi_account(self) -> bool:
        return bool(self.task.config.get("多账户模式", False)) and callable(
            getattr(self.task, "iter_multi_account_context", None)
        )

    def _current_account_info(self) -> dict[str, str]:
        return {
            "account_user": str(getattr(self.task, "current_user", "") or ""),
            "account_id": str(getattr(self.task, "current_account_id", "") or ""),
        }

    def get_current_task_name(self) -> str:
        return str(self.current_task_key or self.final_summary.get("current_task", "") or "")

    def set_task_failure(self, message: str, task_name: str = None, screenshot_taken: bool = False):
        """手动标记当前任务失败消息。

        Args:
            message: 失败消息文本。
            task_name: 任务名；为空时自动取当前正在执行的任务。
            screenshot_taken: 已自行截图时置 True，避免重复截图。
        """
        resolved_task_name = str(task_name or self.get_current_task_name() or "").strip()
        if not resolved_task_name:
            return
        resolved_message = str(message)
        if screenshot_taken:
            self.failure_screenshot_tasks.add(resolved_task_name)
        # 按 account_id 分组存储失败消息
        account_id = self._current_account_info().get("account_id", "")
        if account_id not in self.failure_details:
            self.failure_details[account_id] = {}
        self.failure_details[account_id].setdefault(resolved_task_name, resolved_message)
        try:
            self.task.log_info(
                self._tr("任务失败标记 | {name}: {message}").format(
                    name=self._tr(resolved_task_name), message=resolved_message
                )
            )
        except Exception:
            pass

    def clear_task_failure(self, task_name: str):
        """任务成功后移除当前账号下对应的失败记录。"""
        account_id = self._current_account_info().get("account_id", "")
        if account_id in self.failure_details:
            self.failure_details[account_id].pop(task_name, None)

    def _mark_round_context(self, round_index: int, repeat_total: int):
        self._current_round_index = round_index
        self._current_repeat_total = repeat_total
        self._round_entered = True
        self.final_summary["actual_repeat_total"] = repeat_total

    def _append_round_summary(self, round_index: int, repeat_total: int):
        if self._current_round_index is not None and any(
            item.get("round") == round_index
            and item.get("account_id") == self._current_account_info().get("account_id")
            for item in self.final_summary.get("per_round", [])
        ):
            # 同一轮已经归档过（异常路径下可能重复进入），不重复追加
            return None
        round_summary = {
            "round": round_index,
            "repeat_total": repeat_total,
            **self._current_account_info(),
            "success": list(self.task_status.get("success", [])),
            "failed": list(self.task_status.get("failed", [])),
            "skipped": list(self.task_status.get("skipped", [])),
            "all": list(self.task_status.get("all", [])),
        }
        self.final_summary.setdefault("per_round", []).append(round_summary)
        if round_summary["failed"]:
            self.final_summary.setdefault("all_fail_tasks", []).append(
                (round_index, list(round_summary["failed"]))
            )
        return round_summary

    def _reset_task_status(self):
        self.task_status = _new_task_status(self.task_items)

    def _sync_task_status_info(self):
        if not self.publish_info:
            return
        for status_key, info_key in _STATUS_INFO_MAP:
            values = self.task_status.get(status_key)
            if values:
                self.task.info_set(info_key, values)

    def has_summary_data(self) -> bool:
        return bool(
            self.final_summary.get("per_round")
            or self.final_summary.get("all_fail_tasks")
            or self.failure_details
            or self.final_summary.get("actual_repeat_total", 0) > 0
            or self.final_summary.get("current_task")
        )

    def _iter_rounds(self, repeat_times: int):
        """产出 (轮次索引, 总轮数)。任务支持多账户时走账号轮次，否则按 repeat_times 重复。"""
        context = getattr(self.task, "iter_multi_account_context", None)
        if callable(context):
            yield from context(
                repeat_times=repeat_times,
                empty_accounts_message=self._tr("多账户模式已开启，但账号列表为空，日常任务结束"),
                account_log_suffix=self._tr("任务执行"),
            )
            return
        for idx in range(repeat_times):
            yield idx, repeat_times

    def execute_task(self, key, func, predicate=None):
        """执行单个任务项，返回 True 表示可以继续，False 表示该项失败。"""
        self.task_status["all"].remove(key)
        if predicate is not None:
            enabled = bool(predicate())
        elif key in ALWAYS_RUN_KEYS:
            enabled = True
        else:
            keys = [key] if isinstance(key, str) else list(key)
            enabled = any(self.task.config.get(k, False) for k in keys)
        if not enabled:
            self.task_status["skipped"].append(key)
            return True

        self.current_task_key = key
        self.failure_screenshot_tasks.discard(key)
        self.final_summary["current_task"] = key
        self.task.log_info(self._tr("开始任务: {key}").format(key=self._tr(key)))
        self.task.ensure_main(**self.ensure_main_kwargs)
        result = func()

        if result is False:
            self.task_status["failed"].append(key)
            self.set_task_failure(self._tr("任务返回 False"), task_name=key)
            if key not in self.failure_screenshot_tasks:
                self.task.screenshot(f"DailyTask_FailTask_{key}")
            self.task.log_info(self._tr("任务 {key} 执行失败").format(key=self._tr(key)), notify=True)
            self.current_task_key = None
            self.final_summary["current_task"] = ""
            return False

        self.task_status["success"].append(key)
        self.clear_task_failure(key)
        self.current_task_key = None
        self.final_summary["current_task"] = ""
        return True

    def run(self, repeat_times: int = 1):
        """按清单顺序执行全部任务项，异常在记录与截图后继续向外传播。"""
        self.task.log_info(self._tr("开始执行日常任务..."), notify=True)
        self.final_summary["status"] = "运行中"
        try:
            for repeat_idx, repeat_total in self._iter_rounds(repeat_times):
                round_index = repeat_idx + 1
                self._rounds_executed += 1
                self._mark_round_context(round_index, repeat_total)
                self._reset_task_status()

                if self._is_multi_account():
                    # 切号后需要先回到主界面，登录流程可能较慢，给更长的超时
                    if getattr(self.task, "_logged_in", False):
                        self.task.ensure_main(**self.ensure_main_kwargs)
                    else:
                        self.task.ensure_main(recheck_time=2, time_out=600)

                self.task.log_info(
                    self._tr("开始第 {idx}/{total} 轮任务执行").format(idx=round_index, total=repeat_total)
                )

                for item in self.task_items:
                    key, func = item[0], item[1]
                    predicate = item[2] if len(item) > 2 else None
                    self.execute_task(key, func, predicate)

                # 单轮时保持改造前的原文案，多轮才加轮次前缀
                if self.task_status["failed"]:
                    if repeat_total > 1:
                        message = self._tr("第 {idx} 轮 | 失败任务: {failed}").format(
                            idx=round_index, failed=self.task_status["failed"]
                        )
                    else:
                        message = self._tr("以下任务未完成或失败: {failed}").format(
                            failed=self.task_status["failed"]
                        )
                    self.task.log_info(message, notify=True)
                else:
                    if repeat_total > 1:
                        message = self._tr("第 {idx} 轮 | 日常完成!").format(idx=round_index)
                    else:
                        message = self._tr("日常完成!")
                    self.task.log_info(message, notify=True)

                self._append_round_summary(round_index, repeat_total)
                self._sync_task_status_info()
                self._round_entered = False

            if not self._rounds_executed:
                # 多账户模式下账号列表为空：一轮都没跑，不能把状态留在「运行中」
                self.final_summary["status"] = "未开始"
            elif self.final_summary.get("all_fail_tasks"):
                self.final_summary["status"] = "部分失败"
            else:
                self.final_summary["status"] = "完成"
            if self.final_summary["actual_repeat_total"] > 1:
                if self.final_summary["all_fail_tasks"]:
                    self.task.log_info(
                        self._tr("执行完成，失败统计: {failed}").format(
                            failed=[
                                (idx, list(keys))
                                for idx, keys in self.final_summary["all_fail_tasks"]
                            ]
                        ),
                        notify=True,
                    )
                else:
                    self.task.log_info(self._tr("所有任务均成功完成!"), notify=True)
        except Exception as e:
            self.handle_exception(e)

    def handle_exception(self, e: Exception):
        """记录异常现场后重新抛出，保持「异常向外传播」的原有语义。"""
        self.final_summary["status"] = "异常结束"
        self.final_summary["exception"] = str(e)
        self.final_summary["current_task"] = self.current_task_key or self.final_summary.get("current_task", "")
        if self.current_task_key:
            self.set_task_failure(self._tr("异常: {err}").format(err=e), task_name=self.current_task_key)

        # 只有真正进入过轮次才归档；切号阶段失败时 task_status 还是上一轮的残留，补记会产生错误数据
        if self._round_entered and self._current_round_index is not None:
            self._append_round_summary(self._current_round_index, self._current_repeat_total)
        self._sync_task_status_info()

        try:
            self.task.info_set("当前失败的任务", self.get_current_task_name())
        except Exception:
            pass
        try:
            self.task.screenshot("DailyTask_Exception")
        except Exception:
            pass

        # 与旧逻辑一致：异常不吞，记录现场后继续向外传播，由上层决定后续动作。
        raise e
