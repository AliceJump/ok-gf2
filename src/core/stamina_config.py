"""
全局「体力」配置：推图、一键日常等所有任务遇到体力不足弹窗（情报拼图补充）时都按这里的开关处理。
"""

from ok.util.config import ConfigOption

STAMINA_OPTION_NAME = "体力"
KEY_AUTO_POTION = "自动使用体力药"

stamina_option = ConfigOption(
    STAMINA_OPTION_NAME,
    {KEY_AUTO_POTION: False},
    description="体力不足时怎么办，对推图和一键日常等所有任务生效",
    config_description={
        KEY_AUTO_POTION: (
            "体力不足弹出「情报拼图补充」时，只用调度室储存和情报拼图道具（含接入密钥）恢复，每次用 1 份，"
            "绝不使用坍塌晶条\n关闭时：推图遇到体力不足直接停止；一键日常刷体力则当作刷完，继续后面的任务"
        ),
    },
)
