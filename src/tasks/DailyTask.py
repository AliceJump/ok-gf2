"""一键日常任务。

职责只有三件事：注册配置、声明任务清单（``build_task_plan``）、驱动编排器（``run``）。
具体的执行逻辑按领域拆在 ``src/tasks/daily/`` 下的各个 mixin 里。
"""

import tempfile
from pathlib import Path
from src.tasks.AccountMixin import AccountMixin
from src.core.BaseGfTask import BaseGfTask, pop_ups, stamina_re, map_re, parse_time_option
from src.tasks.CommunityClient import CommunityMixin
from src.tasks.DailyTaskRunner import DailyTaskRunner
from src.tasks.daily_summary import create_task_summary_report, open_local_path_with_default_app

from src.tasks.daily.daily_common_mixin import DailyCommonMixin
from src.tasks.daily.daily_reward_mixin import DailyRewardMixin
from src.tasks.daily.daily_activity_mixin import DailyActivityMixin
from src.tasks.daily.daily_public_mixin import DailyPublicMixin
from src.tasks.daily.daily_battle_mixin import DailyBattleMixin


class DailyTask(AccountMixin, DailyCommonMixin, DailyRewardMixin, DailyActivityMixin, DailyPublicMixin, DailyBattleMixin, CommunityMixin, BaseGfTask):
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
        auto_loop_skip_list = ['体力本', '自动刷体力', '刷钱本', '竞技场']
        auto_loop_skip_dict = {i: "开启自主循环后会跳过该项" for i in auto_loop_skip_list}
        self.config_description.update(auto_loop_skip_dict | {
            '已确认启用游戏内全局自动功能': (
                '运行前必须先在游戏内开启全局自动战斗\n'
                '（设置 → 其他 → 自动战斗设置），开启后勾选本项'
            ),
            '当前物资关卡名称': (
                '活动自律中当前大活动的名称\n'
                '例：铸碑者的黎明\n'
                '章节"上篇/下篇"与"初篇/转篇"等价，填活动名即可'
            ),
            '用户名': '使用账户密码方式登录网页社区时(不是直接的手机号或邮箱)\n account 请求负载中的 account_name 的值',
            '密码': '使用账户密码方式登录网页社区时(不是直接的密码)\n account 请求负载中的 passwd 的值',
            '喝水': (
                '活动层喝水动作的按键时长，格式：a键时长-w键时长-d键时长\n'
                '例：1.087-1.4-0.5'
            ),
            '吃饭': (
                '活动层吃饭动作的按键时长，格式：时长（秒）\n'
                '例：1.0'
            ),
            '社区每日': '自动完成社区每日任务（需填写用户名和密码）',
            '邮件': '自动领取邮件中的所有奖励',
            '情报/战前补给': '自动领取活动页面中的情报补给奖励',
            '战前补给': '自动领取活动页面中的战前补给奖励',
            '闪耀星愿': '自动完成活动页面中的闪耀星愿关卡',
            '活动自律': (
                '自动进入限时开启活动并挑战物资关卡\n'
                '关卡名称在"当前物资关卡名称"中配置'
            ),
            '活动层': '自动完成活动层中的喝水、吃饭和奖励领取流程',
            '公共区/调度室': '自动完成公共区委托的派遣与领取',
            '自主循环': (
                '开启后公共区将启动游戏内自主循环模式\n'
                '同时跳过：体力本、自动刷体力、刷钱本、竞技场'
            ),
            '购买免费礼包': '自动购买商城中的免费礼包',
            '商店心愿单购买': (
                '自动在各商店（家具/班组/调度/讯段/心智/人形堆栈）中\n'
                '一键购买心愿单商品'
            ),
            "尘烟": '需开启班组项',
            '领任务': '自动领取委托中的每日任务奖励',
            '大月卡': '自动领取巡录（大月卡）的每日沿途行动奖励',
            '探索领取': '自动领取边界推进探索区域的采集与派遣奖励',
            '生成汇总文件': (
                '任务结束后把执行情况写成 txt 汇总\n'
                '目录：系统临时目录/ok-gf2/一键日常/'
            ),
            '自动打开汇总文件': '生成汇总后自动用系统默认程序打开它'
        })
        self.default_config.update({
            '已确认启用游戏内全局自动功能': False,
            '当前物资关卡名称': '铸碑者的黎明',
            '体力本': "军备解析",
            '用户名': "",
            '密码': "",
            '喝水': '1.087-1.4-0.5',
            '吃饭': '1.0',
            "社区每日": False,
            '邮件': True,
            '情报和战前补给': True,
            '闪耀星愿': False,
            '活动自律': True,
            '活动层': True,
            '公共区/调度室': True,
            '自主循环': False,
            '购买免费礼包': True,
            '商店心愿单购买': True,
            '自动刷体力': True,
            '刷钱本': False,
            '竞技场': True,
            '班组': True,
            '尘烟': True,
            '领任务': True,
            '大月卡': True,
            '探索领取': True,
            '生成汇总文件': True,
            '自动打开汇总文件': False
        })

    def _init_stamina_options(self):
        """

            下拉框配置

        """
        self.stamina_options = ['军备解析', '深度搜索', '决策构象', '定向']
        self.config_type["体力本"] = {'type': "drop_down", 'options': self.stamina_options}

    def _init_default_config_group(self):
        """
            配置组，开启自主循环后会跳过的项目

        """
        self.default_config_group.update({
            "社区每日": ["用户名", "密码"],
            "活动自律": ["当前物资关卡名称"],
            "活动层": ["喝水", "吃饭"],
            "公共区/调度室": ["自主循环"],
            "自主循环跳过项": ["自动刷体力", "刷钱本", "竞技场"],
            "购买免费礼包": ["商店心愿单购买"],
            "自动刷体力": ["体力本"],
            "班组": ["尘烟"],
        })
        for group, keys in self.default_config_group.items():
            self.config_type.update({group: {'sub_configs': {True: keys}}})

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
            ("ensure_main", lambda: self.ensure_main(
                recheck_time=2,
                time_out=90
            )),
            ('邮件', self.mail),
            ('情报和战前补给', self.activities),
            ('活动自律', self.activity),
            ('活动层', self.free_time_layer),
            ('公共区/调度室', self.gongongqu),
            ('购买免费礼包', self.shopping),
            ('自动刷体力', self.battle),
            ('竞技场', self.arena),
            ('班组', self.guild),
            ('领任务', self.claim_quest),
            ('大月卡', self.xunlu),
            ('探索领取', self.explore_claim),
            ('闪耀星愿', self.star_wish),
        ]

    def run(self):
        if not self.config.get('已确认启用游戏内全局自动功能'):
            self.confirm_auto_battle_up()
        try:
            self.daily_runner = DailyTaskRunner(self, self.build_task_plan())
            self.daily_runner.run()
        finally:
            # 无论正常结束还是异常中断，都尝试落地汇总，便于事后排查
            self.run_daily_finally()

    def run_daily_finally(self):
        """生成执行情况汇总 txt。整个过程失败只记日志，不影响任务本身的结果。"""
        try:
            if not self.config.get('生成汇总文件', True):
                return True
            if not (self.daily_runner and self.daily_runner.has_summary_data()):
                self.log_info('无可用汇总信息，跳过生成汇总文件')
                return True

            summary_path = create_task_summary_report(
                self, Path(tempfile.gettempdir()), self.daily_runner.final_summary
            )
            if self.config.get('自动打开汇总文件', False):
                open_local_path_with_default_app(summary_path)
                self.log_info(f'日常执行情况汇总已创建并打开: {summary_path}')
            else:
                self.log_info(f'日常执行情况汇总已创建（未打开）: {summary_path}')
            return True
        except Exception as e:
            self.log_info(f'创建日常任务汇总文件失败: {e}', notify=True)
            return False
