"""
部署界面阵容的「目标 → 差异 → 动作」规划（纯函数，不碰画面，便于单测）。

整理阵容不再是「切编队 → 借助战撤一人 → 补满」一条道走到底，而是：
观察当前阵容（我的人形打勾的卡片、顶部 n/m、场上有没有别的助战）→ 按规则算出要做的动作 →
执行 → 再观察一次重新规划，直到没有动作可做（最多几轮）。哪一步没成功，下一轮会按新的画面重新算。

规则（用户定的，实录 2026-10-20：借到 6 椎威玛西娜时自己的威玛西娜也在场上）：
1. 场上已是要借的助战：保留；
2. 场上有别的助战（上一关留下的）：撤掉；
3. 我方和助战同名的人形：撤掉（游戏不让同名人形同时上场）；
4. 腾完还是满的：撤我方战力最低的给助战让位；
5. 部署助战；
6. 剩下的空位按战力从高到低补我方没上场的人形（不补和助战同名的）。
7. 「强制出战」的人形（关卡指定，撤不下来）：当它占的格子不存在，不撤、不拿来让位；
   它和要借的助战同名时这次不借助战（实录 2026-10-21 LA-1-5：闪电、乌尔丽德强制出战）。
"""

import re
from dataclasses import dataclass, field


@dataclass
class Unit:
    """面板上的一张卡片，或地图上的一个单位。"""

    name: str | None
    power: int = 0
    deployed: bool = False
    support: bool = False  # 好友助战（不是我的人形）
    locked: bool = False  # 「强制出战」：关卡指定上场，撤不下来
    ref: object = None  # 执行时用的定位信息（卡片 dict / 地格坐标），规划不看


@dataclass
class LineupState:
    capacity: int | None  # 顶部「部署人形 n/m」的 m，读不到为 None
    deployed: int | None  # n
    own: list = field(default_factory=list)  # 我的人形面板里的卡片 [Unit]
    supports_on_map: list = field(default_factory=list)  # 场上的助战 [Unit]（名字可能为 None）

    def own_deployed(self):
        return [u for u in self.own if u.deployed]

    def used(self):
        """场上人数：优先用顶部计数，读不到就数打勾的卡片 + 场上助战。"""
        if self.deployed is not None:
            return self.deployed
        return len(self.own_deployed()) + len(self.supports_on_map)


@dataclass
class Step:
    action: str  # "withdraw" / "deploy"
    unit: Unit
    why: str

    def __str__(self):
        verb = "撤下" if self.action == "withdraw" else "部署"
        who = ("助战 " if self.unit.support else "") + (self.unit.name or "?")
        return f"{verb}{who}（{self.why}）"


def name_like(a, b):
    """OCR 认名字偶尔错一个字（可露凯/可露凱），这里只做最基本的包含比较；执行层可传更宽松的。"""
    return bool(a) and bool(b) and (a in b or b in a)


def plan_lineup(state, want_support=None, like=name_like, exclude=()):
    """
    :param state: LineupState
    :param want_support: 要借的助战 Unit（support=True），None 表示不借
    :param exclude: 补空位时跳过的我方卡片 {(名字, 战力)}（上一轮点了没部署上的），轮到下一张
    :return: [Step]，按顺序执行；空列表表示阵容已经是目标状态
    """
    steps = []
    used = state.used()
    cap = state.capacity
    support_ok = False
    if want_support is not None:
        for s in state.supports_on_map:
            if like(s.name, want_support.name):
                support_ok = True
            else:
                steps.append(Step("withdraw", s, "上一关留下的助战"))
                used -= 1
        if not support_ok and any(u.locked and like(u.name, want_support.name) for u in state.own_deployed()):
            # 强制出战里有同名人形，游戏不让同名同时上场，助战上不去
            want_support = None
        if want_support is not None and not support_ok:
            for u in state.own_deployed():
                if like(u.name, want_support.name):
                    steps.append(Step("withdraw", u, "与助战同名"))
                    used -= 1
            if cap is not None and used >= cap:
                withdrawn = {id(s.unit) for s in steps}
                left = [u for u in state.own_deployed() if id(u) not in withdrawn and not u.locked]
                if left:
                    weakest = min(left, key=lambda u: u.power)
                    steps.append(Step("withdraw", weakest, f"给助战让位，我方战力最低({weakest.power})"))
                    used -= 1
            steps.append(Step("deploy", want_support, "借助战"))
            used += 1
    if cap is None:
        return steps
    banned = {id(s.unit) for s in steps if s.action == "withdraw"}
    support_name = want_support.name if want_support is not None else None
    spare = [
        u
        for u in state.own
        if not u.deployed
        and id(u) not in banned
        and not (support_name and like(u.name, support_name))
        and (u.name, u.power) not in exclude
    ]
    spare.sort(key=lambda u: -u.power)
    for u in spare[: max(0, cap - used)]:
        steps.append(Step("deploy", u, f"补空位，没上场里战力最高({u.power})"))
    return steps


# ------------------------------------------------------------------ 顶部计数
count_re = re.compile(r"(\d)\s*[/|\\]\s*(\d)")


def parse_count_text(text):
    """「3/4」→ (3, 4)。斜杠常被 OCR 读成 1/l/I（如 '414'、'3l4'），单独一个三字符的也接受；总数比已上场小当读错。"""
    m = count_re.search(text) or re.fullmatch(r"(\d)[1lI](\d)", text.strip())
    if not m:
        return None
    n, total = int(m.group(1)), int(m.group(2))
    return (n, total) if total >= n else None


def deploy_count_from_boxes(boxes, label="部署人形"):
    """
    顶部计数区 OCR 结果里找「部署人形」后面那个 n/m。
    实录 2026-10-20：关卡目标「使用刀的人形 1/3」就在下面一行，旧逻辑拿到哪个 n/m 算哪个，会读错或读丢。
    有标签时只认标签同一行、在它右边最近的 n/m（也接受「部署人形4/4」粘在一起）；没读到标签才退回第一个 n/m。
    """
    labels = [b for b in boxes if label in b.name]
    for b in labels:
        tail = b.name.split(label, 1)[1]
        if parsed := parse_count_text(tail):
            return parsed
    if labels:
        lb = labels[0]
        ly = lb.y + lb.height / 2
        row = []
        for b in boxes:
            if b is lb or b.x < lb.x + lb.width * 0.5:
                continue
            if abs(b.y + b.height / 2 - ly) > max(lb.height, b.height):
                continue
            if parsed := parse_count_text(b.name):
                row.append((b.x, parsed))
        if row:
            return min(row)[1]
        return None
    for b in boxes:
        if parsed := parse_count_text(b.name):
            return parsed
    return None
