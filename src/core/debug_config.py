"""
全局「调试」配置：开了「调试截图」后所有任务（推图、一键日常、周常……）都会把各阶段截图存到
screenshots/<任务名>/<日期>/，每个任务最多 400 张，自动轮转。
"""

from ok.util.config import ConfigOption

DEBUG_OPTION_NAME = "调试"
KEY_DEBUG_SHOT = "调试截图"

debug_option = ConfigOption(
    DEBUG_OPTION_NAME,
    {KEY_DEBUG_SHOT: True},
    description="排查问题用的全局开关，对所有任务生效",
    config_description={
        KEY_DEBUG_SHOT: "把每个任务各阶段的截图保存到 screenshots/任务名/日期/ 下，每个任务最多保留 400 张；关掉就不存",
    },
)
