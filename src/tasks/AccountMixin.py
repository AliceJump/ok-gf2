"""多账户执行上下文。

移植自 ok-end-field 的 ``src/core/BaseEfTask.iter_multi_account_context`` 与
``src/tasks/account/account_mixin.py``，但**登录逻辑留空**——ok-gf2 没有游戏内切号能力，
``login_flow()`` 必须由本项目自行实现（ok-end-field 那套是终末地的登出/最近账号列表/登录流程，
界面完全不同，无法复用）。

相对 ok-end-field 未移植的部分：

- ``多账户独立配置`` 与 ``AccountOverrideMixin``：依赖 ``account_scope_store``（账号 ID 持久化）
  与 ok-end-field 的 ``AccountConfigTab`` 配置页，ok-gf2 无对应设施。
- ``resolve_account_id`` 账号 ID 持久化：退化为「账号名即 ID」，需要稳定 ID 时重写该方法。
"""

from __future__ import annotations

from src.data.FeatureList import FeatureList as fL


class AccountMixin:
    """为任务提供多账户轮次执行能力。

    使用方式：任务类继承本 mixin 并在 ``__init__`` 中调用 ``_init_account_config()``，
    然后实现 ``login_flow()``。
    """

    def _init_account_config(self):
        """注册多账户相关配置。必须在 ``super().__init__`` 之后调用。"""
        self.current_user = ""
        self.current_account_id = ""
        self._logged_in = False

        self.default_config.update(
            {
                "多账户模式": False,
                "账号列表": "\n",
            }
        )
        self.config_description.update(
            {
                "多账户模式": (
                    "开启后按账号列表逐个切换账号执行"
                ),
                "账号列表": (
                    "每行一个账号，切换顺序即执行顺序"
                ),
            }
        )
        if not hasattr(self, "config_type") or self.config_type is None:
            self.config_type = {}
        self.config_type["多账户模式"] = {
            "sub_configs": {True: ["账号列表"]},
        }

    def resolve_account_id(self, username: str) -> str:
        """返回账号的稳定唯一标识。

        默认以账号名本身作为 ID。若账号名会变化（例如昵称可改），或需要跨账号保存数据，
        应重写本方法返回稳定 ID。
        """
        return username

    def get_account_list(self):
        """解析配置里的账号列表，返回 ``[{"account_id": ..., "username": ...}, ...]``。"""
        account_str = self.config.get("账号列表", "")
        account_list = []
        if not account_str:
            return account_list

        for line in account_str.splitlines():
            line = line.strip()
            if not line:
                continue
            # 兼容 `账号, 密码` 旧格式，密码忽略
            username = line.split(",", 1)[0].strip() if "," in line else line
            if not username:
                self.log_info(self.tr("账号格式错误，已跳过: {line}").format(line=line))
                continue
            account_list.append(
                {
                    "account_id": self.resolve_account_id(username),
                    "username": username,
                }
            )
        return account_list

    def set_current_account(self, username: str, account_id: str):
        """设置当前账号上下文。编排器据此把失败记录与轮次日志按账号分组。"""
        self.current_user = username
        self.current_account_id = account_id

    def login_flow(self, username: str, password: str | None = None):
        """切换到指定账号。**必须由 ok-gf2 自行实现。**
        Args:
            username: 要切换到的账号标识。
            password: 兼容参数，ok-gf2 不存储也不使用密码。

        Raises:
            NotImplementedError: 始终抛出，直到本项目实现该方法。
        """
        self.ensure_main()
        self.back()
        self.wait_click_ocr(match="设置", box=self.box.top_right)
        self.wait_click_feature(fL.login_out, settle_time=0.5, raise_if_not_found=False) 
        self.wait_click_feature(fL.confirm, settle_time=0.5, raise_if_not_found=False)
        self.wait_click_feature(fL.login_switch, settle_time=0.5, raise_if_not_found=False)
        self.wait_click_feature(fL.login_down, settle_time=0.5, raise_if_not_found=False)
        self.wait_click_ocr(username, box=self.box_of_screen(0.272, 0.474, 0.414, 0.991), raise_if_not_found=False)
        self.wait_click_feature(fL.login_in, settle_time=0.5, raise_if_not_found=False)


    def iter_multi_account_context(
        self,
        repeat_times: int = 1,
        empty_accounts_message: str | None = None,
        account_log_suffix: str = "",
    ):
        """统一多账户执行上下文。

        开启多账户模式时读取账号列表逐个切换；否则按 ``repeat_times`` 重复执行。

        Args:
            repeat_times: 非多账户模式下的执行轮数。
            empty_accounts_message: 账号列表为空时的提示文案。
            account_log_suffix: 账号启动日志的后缀文本。

        Yields:
            tuple[int, int]: 当前轮次索引（从 0 开始）和总轮数。
        """
        multi = bool(self.config.get("多账户模式", False))
        if multi:
            accounts_list = self.get_account_list()
            if not accounts_list:
                if empty_accounts_message:
                    self.log_info(empty_accounts_message, notify=True)
                return
            repeat_times = len(accounts_list)
        else:
            accounts_list = []

        for repeat_idx in range(repeat_times):
            if multi:
                account = accounts_list[repeat_idx]
                username = str(account.get("username", "")).strip()
                account_id = str(account.get("account_id", "")).strip() or username
                if not username:
                    self.log_info(
                        self.tr("第 {idx}/{total} 个账号为空，已跳过").format(
                            idx=repeat_idx + 1, total=repeat_times
                        )
                    )
                    continue

                self.set_current_account(username, account_id)
                # 账号后缀是运行时用户数据，不过 tr（防污染收集池）；模板串过 tr
                self.log_info(
                    self.tr("开始第 {idx}/{total} 个账号({suffix}){log_suffix}").format(
                        idx=repeat_idx + 1,
                        total=repeat_times,
                        suffix=username[-4:],
                        log_suffix=account_log_suffix,
                    )
                )
                self.login_flow(username)
            else:
                self.set_current_account("", "")

            yield repeat_idx, repeat_times
