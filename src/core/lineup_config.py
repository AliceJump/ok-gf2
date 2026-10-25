"""
全局「阵容与助战」配置：所有会进部署界面的任务共用一套。

取值优先级：内置默认 -> 全局设置 -> 各场景单独设置（越后面越优先）。
- 编队：「<场景>编队」留空就用全局「编队名」。
- 借助战：「<场景>助战」选「沿用全局」就用全局「借好友助战」（内置默认开）。
场景都登记在 SCOPES 里；Qt 设置页在「阵容与助战」里逐个列出这些键，可选的 web_v2 新界面在对应板块里显示（catalog.json 的 lineup_scopes）。
"""

from ok.util.config import ConfigOption

LINEUP_OPTION_NAME = "阵容与助战"
KEY_PRESET = "编队名"
KEY_SUPPORT = "借好友助战"
KEY_ROLE = "助战角色"
KEY_MIN_BADGE = "助战最低椎数"
KEY_FALLBACK = "找不到就借战力最高"

SUPPORT_INHERIT = "沿用全局"
SUPPORT_ON = "开"
SUPPORT_OFF = "关"
SUPPORT_CHOICES = [SUPPORT_INHERIT, SUPPORT_ON, SUPPORT_OFF]

# 场景（= set_lineup_kind 的 kind；推图任务的 kind 是 None，按「推图」算）
# support=False 的场景游戏里没有好友助战或流程没接，不显示「助战」键，也永远不借
SCOPES = [
    {"name": "推图", "support": True, "desc": "推图任务"},
    {"name": "竞技场", "support": False, "desc": "一键日常「竞技场」（实兵演习）"},
    {"name": "体力本", "support": False, "desc": "一键日常「自动刷体力」手动挑战"},
    {"name": "班组", "support": False, "desc": "一键日常「班组」要务"},
    {"name": "尘烟前哨战", "support": True, "desc": "一键日常「班组」里的尘烟前线·前哨战（借助战时选战力最高的人形）"},
    {"name": "活动", "support": False, "desc": "一键日常「活动自律」"},
    {"name": "扩编实练", "support": False, "desc": "周常「扩编实练」特殊增强关卡"},
    {"name": "首领挑战", "support": False, "desc": "周常「首领挑战」常规挑战（没到最高层级时手动打）"},
]
SCOPE_BY_NAME = {s["name"]: s for s in SCOPES}
DEFAULT_SCOPE = "推图"


def preset_key(scope):
    return f"{scope}编队"


def support_key(scope):
    return f"{scope}助战"


def scope_of_kind(kind):
    return kind or DEFAULT_SCOPE


_defaults = {
    KEY_PRESET: "编队1",
    KEY_SUPPORT: True,
    KEY_ROLE: "威玛西娜",
    KEY_MIN_BADGE: 6,
    KEY_FALLBACK: True,
}
_descriptions = {
    KEY_PRESET: "默认编队：下面各场景没单独填编队时都用它（游戏里可自定义名字，默认 编队1）。留空就不切编队，只补满空位",
    KEY_SUPPORT: "默认借不借好友助战：各场景「助战」选「沿用全局」时按这里",
    KEY_ROLE: "要借的助战角色名，须与游戏内显示一致，如 威玛西娜",
    KEY_MIN_BADGE: "卡片左上角蓝圈里的椎数至少要多少，默认 6",
    KEY_FALLBACK: "没有椎数达标的指定角色时，切到「全部」按战力从高到低借第一个",
}
_types = {
    KEY_PRESET: {"type": "line_edit"},
    KEY_ROLE: {"type": "line_edit"},
    KEY_MIN_BADGE: {"min": 0, "max": 6},
}
for _s in SCOPES:
    _defaults[preset_key(_s["name"])] = ""
    _descriptions[preset_key(_s["name"])] = f"{_s['desc']}用的编队，留空沿用默认编队"
    _types[preset_key(_s["name"])] = {"type": "line_edit"}
    if _s["support"]:
        _defaults[support_key(_s["name"])] = SUPPORT_INHERIT
        _descriptions[support_key(_s["name"])] = f"{_s['desc']}借不借好友助战，「沿用全局」按上面的「借好友助战」"
        _types[support_key(_s["name"])] = {"type": "drop_down", "options": SUPPORT_CHOICES}

lineup_option = ConfigOption(
    LINEUP_OPTION_NAME,
    _defaults,
    description="所有会进部署界面的任务共用。优先级：内置默认 → 这里的全局值 → 下面各场景单独的「××编队 / ××助战」",
    config_description=_descriptions,
    config_type=_types,
)


def preset_name_for_kind(cfg, kind):
    """kind（竞技场/体力本/班组/尘烟前哨战/活动/扩编实练/None=推图）对应的编队名；该场景没填就退回「编队名」。"""
    name = (cfg.get(preset_key(scope_of_kind(kind))) or "").strip()
    return name or (cfg.get(KEY_PRESET) or "").strip()


def support_enabled_for_kind(cfg, kind):
    """该场景借不借助战：场景不支持 -> False；场景设了开/关按场景；沿用全局 -> 全局「借好友助战」（默认开）。"""
    scope = SCOPE_BY_NAME.get(scope_of_kind(kind))
    if not scope or not scope["support"]:
        return False
    own = cfg.get(support_key(scope["name"])) or SUPPORT_INHERIT
    if own == SUPPORT_ON:
        return True
    if own == SUPPORT_OFF:
        return False
    return bool(cfg.get(KEY_SUPPORT, _defaults[KEY_SUPPORT]))
