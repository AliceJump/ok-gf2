"""一键日常任务。

职责只有三件事：注册配置、声明任务清单（``build_task_plan``）、驱动编排器（``run``）。
具体的执行逻辑按领域拆在 ``src/tasks/daily/`` 下的各个 mixin 里。
"""

import tempfile
from pathlib import Path

from src.core.BaseGfTask import BaseGfTask
from src.tasks.AccountMixin import AccountMixin
from src.tasks.CommunityClient import CommunityMixin
from src.tasks.daily.daily_activity_mixin import DRINK_ROUTE, EAT_ROUTE, DailyActivityMixin
from src.tasks.daily.daily_battle_mixin import DailyBattleMixin
from src.tasks.daily.daily_common_mixin import DailyCommonMixin
from src.tasks.daily.daily_public_mixin import DailyPublicMixin
from src.tasks.daily.daily_record import DailyRecord
from src.tasks.daily.daily_reward_mixin import DailyRewardMixin
from src.tasks.daily_summary import create_task_summary_report, open_local_path_with_default_app
from src.tasks.DailyTaskRunner import DailyTaskRunner


class DailyTask(
    AccountMixin,
    DailyCommonMixin,
    DailyRewardMixin,
    DailyActivityMixin,
    DailyPublicMixin,
    DailyBattleMixin,
    CommunityMixin,
    BaseGfTask,
):
    # 允许「多账户独立配置」按账号覆盖本任务的参数
    support_multi_account = True
    # 这些是全账号共用的开关，按账号覆盖没有意义
    account_config_blacklist = {
        "已确认启用游戏内全局自动功能",
        "生成汇总文件",
        "自动打开汇总文件",
        "Exit After Task",
    }

    def __init__(self, *args, **kwargs):
        """
        该模块总启动配置
        """
        super().__init__(*args, **kwargs)
        self.name = "一键日常"
        self.description = "收菜"
        self.support_schedule_task = True
        self.daily_runner = None  # DailyTaskRunner 实例，见 run()
        self._init_account_config()  # 多账户：多账户模式 / 多账户独立配置 / 账号列表
        self._init_default_config()
        self._init_stamina_options()
        self._init_default_config_group()
        self.add_exit_after_config()

    def _init_default_config(self):
        """

        输入框和选择框配置

        """
        auto_loop_skip_list = ["体力本", "自动刷体力", "刷钱本", "竞技场"]
        auto_loop_skip_dict = dict.fromkeys(auto_loop_skip_list, "开启自主循环后会跳过该项")
        self.config_description.update(
            auto_loop_skip_dict
            | {
                "已确认启用游戏内全局自动功能": (
                    "运行前必须先在游戏内开启全局自动战斗\n（设置 → 其他 → 自动战斗设置），开启后勾选本项"
                ),
                "当前物资关卡名称": (
                    '活动自律中当前大活动的名称\n例：铸碑者的黎明\n章节"上篇/下篇"与"初篇/转篇"等价，填活动名即可'
                ),
                "用户名": "使用账户密码方式登录网页社区时(不是直接的手机号或邮箱)\n account 请求负载中的 account_name 的值",
                "密码": "使用账户密码方式登录网页社区时(不是直接的密码)\n account 请求负载中的 passwd 的值",
                "喝水": (
                    "活动层喝水动作的按键时长，格式：a键时长-w键时长-d键时长（三个键连续按，中间不停）\n"
                    f"例：{DRINK_ROUTE}；如果角色走不到茶歇一刻，请微调各键时长"
                ),
                "吃饭": f"活动层吃饭动作按 s 键的时长（秒）\n例：{EAT_ROUTE}",
                "社区每日": "自动完成社区每日任务（需填写用户名和密码）",
                "邮件": "自动领取邮件中的所有奖励",
                "情报/战前补给": "自动领取活动页面中的情报补给奖励",
                "战前补给": "自动领取活动页面中的战前补给奖励",
                "闪耀星愿": "自动完成活动页面中的闪耀星愿关卡",
                "活动自律": ('自动进入限时开启活动并挑战物资关卡\n关卡名称在"当前物资关卡名称"中配置'),
                "活动层": "自动完成活动层中的喝水、吃饭和奖励领取流程",
                "活动层浇花": "在喝水和吃饭后浇灌栽培植物；已浇灌则跳过，不施肥",
                "公共区/调度室": "自动完成公共区委托的派遣与领取",
                "自主循环": ("开启后公共区将启动游戏内自主循环模式\n同时跳过：体力本、自动刷体力、刷钱本、竞技场"),
                "购买免费礼包": "自动购买商城中的免费礼包",
                "商店心愿单购买": ("自动在各商店（家具/班组/调度/讯段/心智/人形堆栈）中\n一键购买心愿单商品"),
                "尘烟": "需开启班组项",
                "尘烟买第3次": "尘烟前线两次免费次数用完后，花 50 坍塌晶条买 1 次参战机会再打一场（每天限 1 次）",
                "领任务": "自动领取委托中的每日任务奖励",
                "大月卡": "自动领取巡录（大月卡）的每日沿途行动奖励",
                "拂晓之光补给包奖励": "远航巡录领取时自动选择的补给包奖励，默认数据链路",
                "探索领取": "自动领取边界推进探索区域的采集与派遣奖励",
                "生成汇总文件": ("任务结束后把执行情况写成 txt 汇总\n目录：系统临时目录/ok-gf2/一键日常/"),
                "自动打开汇总文件": "生成汇总后自动用系统默认程序打开它",
            }
        )
        self.default_config.update(
            {
                "已确认启用游戏内全局自动功能": False,
                "当前物资关卡名称": "铸碑者的黎明",
                "体力本": "军备解析",
                "用户名": "",
                "密码": "",
                "喝水": DRINK_ROUTE,
                "吃饭": EAT_ROUTE,
                "社区每日": False,
                "邮件": True,
                "情报和战前补给": True,
                "闪耀星愿": False,
                "活动自律": True,
                "活动层": True,
                "活动层浇花": True,
                "公共区/调度室": True,
                "自主循环": False,
                "购买免费礼包": True,
                "商店心愿单购买": True,
                "自动刷体力": True,
                "刷钱本": False,
                "竞技场": True,
                "班组": True,
                "尘烟": True,
                "尘烟买第3次": False,
                "领任务": True,
                "大月卡": True,
                "拂晓之光补给包奖励": "数据链路",
                "探索领取": True,
                "生成汇总文件": True,
                "自动打开汇总文件": False,
            }
        )

    def _init_stamina_options(self):
        """

        下拉框配置

        """
        self.config_type["拂晓之光补给包奖励"] = {
            "type": "drop_down",
            "options": ["数据链路", "坍塌晶条", "增域存量条T2", "大容量内存条", "转录导体·序三", "萨狄斯金"],
        }
        self.stamina_options = ["军备解析", "深度搜索", "决策构象", "定向"]
        self.config_type["体力本"] = {"type": "drop_down", "options": self.stamina_options}

    def _init_default_config_group(self):
        """
        配置组，开启自主循环后会跳过的项目

        """
        self.default_config_group.update(
            {
                "社区每日": ["用户名", "密码"],
                "大月卡": ["拂晓之光补给包奖励"],
                "活动自律": ["当前物资关卡名称"],
                "活动层": ["喝水", "吃饭", "活动层浇花"],
                "公共区/调度室": ["自主循环"],
                "自主循环跳过项": ["自动刷体力", "刷钱本", "竞技场"],
                "购买免费礼包": ["商店心愿单购买"],
                "自动刷体力": ["体力本"],
                "班组": ["尘烟", "尘烟买第3次"],
            }
        )
        for group, keys in self.default_config_group.items():
            if group not in self.default_config:
                # 「自主循环跳过项」这种只用来分组、不是真实开关的名字，不能写成 sub_configs：
                # 框架会把它当成父开关去读值（读到 None），子项全部判成隐藏，Web 接口里就看不到「自动刷体力」「竞技场」了
                continue
            self.config_type.update({group: {"sub_configs": {True: keys}}})

    def build_task_plan(self):
        """
        日常任务执行清单

        元素为 (任务名, 执行函数)，任务名同时是配置开关的键名。
        需要自定义开关判定时追加第三个元素「开关谓词」，提供后替代默认的 config.get(任务名)。

        顺序与开关语义与改造前的 run() 完全一致，改动清单前请确认不会破坏前后任务的界面前提。
        """
        return [
            ("社区每日", self.community_daily),
            # 内置项，不做开关判定，恒执行
            ("ensure_main", lambda: self.ensure_main(recheck_time=2, time_out=90)),
            ("邮件", self.mail),
            ("情报和战前补给", self.activities),
            ("活动自律", self.activity),
            ("活动层", self.free_time_layer),
            ("公共区/调度室", self.gongongqu),
            ("购买免费礼包", self.shopping),
            ("自动刷体力", self.battle),
            ("竞技场", self.arena),
            ("班组", self.guild),
            ("领任务", self.claim_quest),
            ("大月卡", self.xunlu),
            ("探索领取", self.explore_claim),
            ("闪耀星愿", self.star_wish),
        ]

    def run(self):
        if not self.config.get("已确认启用游戏内全局自动功能"):
            self.confirm_auto_battle_up()
        self._zilv_locked = False
        self.reset_lineup(None)
        self.start_watchdog()
        try:
            record = None
            try:
                record = DailyRecord()
                done = record.done_tasks(str(getattr(self, "current_account_id", "") or ""))
                if done:
                    self.log_info(f"今天已经完成过的任务（直接跳过）: {done}", notify=True)
                failed = record.failed_tasks(str(getattr(self, "current_account_id", "") or ""))
                if failed:
                    self.log_info(f"今天失败过、这次重试的任务: {failed}", notify=True)
            except Exception as e:
                self.log_info(f"读日常记录失败，这次不跳过任何任务: {e}")
            self.daily_runner = DailyTaskRunner(self, self.build_task_plan(), record=record)
            self.daily_runner.run()
        finally:
            self.stop_watchdog()
            # 无论正常结束还是异常中断，都尝试落地汇总，便于事后排查
            self.run_daily_finally()

    def run_daily_finally(self):
        """生成执行情况汇总 txt。整个过程失败只记日志，不影响任务本身的结果。"""
        try:
            if not self.config.get("生成汇总文件", True):
                return True
            if not (self.daily_runner and self.daily_runner.has_summary_data()):
                self.log_info("无可用汇总信息，跳过生成汇总文件")
                return True

            summary_path = create_task_summary_report(
                self, Path(tempfile.gettempdir()), self.daily_runner.final_summary
            )
            if self.config.get("自动打开汇总文件", False):
                open_local_path_with_default_app(summary_path)
                self.log_info(f"日常执行情况汇总已创建并打开: {summary_path}")
            else:
                self.log_info(f"日常执行情况汇总已创建（未打开）: {summary_path}")
            return True
        except Exception as e:
            self.log_info(f"创建日常任务汇总文件失败: {e}", notify=True)
            return False
