"""
部署界面整理阵容：观察 → 规划（src/core/lineup_plan.py）→ 执行 → 再观察，直到阵容就是目标状态。

为什么不是一条道走到底：每一步（读计数、认名字、找地格、点部署）在实机上都可能失手，旧流程任何一步
失手后面就全按错误的前提走（实录 2026-10-20：椎数全没认出来 → 借了别人；场上同时有旧助战和同名人形
→ 只撤了一个，助战上不去；计数被关卡目标「1/3」干扰没读到 → 没补人）。现在每轮都重新看画面再算。
"""

from collections import Counter

from src.core.lineup_config import KEY_FALLBACK, KEY_MIN_BADGE, KEY_ROLE
from src.core.lineup_plan import LineupState, Unit, plan_lineup
from src.core.support_select import (
    check_point,
    PANEL_BOX,
    filter_point,
    forced_re,
    freed_tile,
    is_orange_check,
    mark_forced,
    pick_candidates,
)

LINEUP_MAX_ROUNDS = 4
STEP_MAX_FAILS = 2  # 同一个动作失手两次就不再试（撤人/上助战偶尔一次点不上）


class LineupMixin:
    _borrowed_support = None  # 这次整理借上场的助战名字（补人时跳过同名）
    _freed_tiles = None  # 撤人后空出来的地格，部署时优先点
    _lineup_capacity = None  # 这个部署界面里读到过的「部署人形 n/m」的 m

    # ------------------------------------------------------------------ 入口
    def prepare_lineup(self):
        """开战前整理阵容：切到配置的整备室编队 → （开了借助战）选定助战 → 按规则撤人/上助战/补满，做完再核对。"""
        if not self.ocr(match="作战开始", box=self.box.bottom):
            self.log_info("不在部署界面，跳过整理阵容", notify=False)
            return
        if not self._ensure_panel():
            self.log_info("打不开部署面板，跳过整理阵容", notify=True)
            return
        self._borrowed_support = None
        self._freed_tiles = []
        preset = self._preset_name()
        if preset:
            self.info_set("current_task", "切换编队")
            self.apply_preset(preset)
        want = None
        if self._support_enabled():
            self.info_set("current_task", "选助战")
            cfg = self._lineup_cfg()
            want = self._choose_support(
                (cfg.get(KEY_ROLE) or "").strip(), int(cfg.get(KEY_MIN_BADGE) or 0), bool(cfg.get(KEY_FALLBACK))
            )
            if want is None:
                self.log_info("没有可借的助战，只用自己的人形", notify=True)
        self.reconcile_lineup(want)
        self.next_frame()
        self.debug_shot("lineup_ready")

    def fill_lineup(self):
        """只补空位、不动助战（沿用阵容时人数不够、「本关至少需要出击」时用）。返回是否满员。"""
        if self._freed_tiles is None:
            self._freed_tiles = []
        return self.reconcile_lineup(None)

    def reconcile_lineup(self, want=None, max_rounds=LINEUP_MAX_ROUNDS):
        """
        :param want: 要借的助战 Unit（_choose_support 的结果），None 不借
        :return: 最后一次观察时是否满员（读不到计数返回 False）
        """
        self.info_set("current_task", "整理阵容")
        self._lineup_capacity = None
        wanted = want
        failed = Counter()  # 动作 -> 失手次数
        state = None
        for rnd in range(max_rounds):
            state = self._observe_lineup(need_map=want is not None, want=want)
            if want is not None and any(self._name_like(u.name, want.name) for u in state.supports_on_map):
                self._borrowed_support = want.name
            # 我方卡片点了一次没上去就换下一张（多半是这张卡本身的问题）；撤人/上助战可以再试一次
            exclude = {(k[1], k[2]) for k in failed if k[0] == "deploy" and not k[3]}
            steps = [
                s
                for s in plan_lineup(state, want, self._name_like, exclude)
                if failed[self._step_key(s)] < STEP_MAX_FAILS
            ]
            self.log_info(
                f"阵容第 {rnd + 1} 轮：{state.used()}/{state.capacity}，我方在场 "
                f"{[f'{u.name}(强制出战)' if u.locked else u.name for u in state.own_deployed()]}，"
                f"场上助战 {[u.name for u in state.supports_on_map]}，"
                f"要做 {[str(s) for s in steps] or '无'}",
                notify=True,
            )
            if not steps:
                if state.capacity is None and rnd < max_rounds - 1:
                    # 没读到 n/m 时规划不敢补人，换一帧再看，别当成已经整理好了
                    self.sleep(0.5)
                    continue
                break
            for step in steps:
                ok = self._withdraw(step) if step.action == "withdraw" else self._deploy(step, want)
                if ok:
                    continue
                failed[self._step_key(step)] += 1
                if step.action == "deploy" and step.unit.support:
                    if failed[self._step_key(step)] >= STEP_MAX_FAILS:
                        # 助战放不上去：别为它再撤人了，按不借助战补满（撤下的同名人形也可以补回来）
                        self.log_info(f"助战 {step.unit.name} 两次没放上去，改为只补我方人形", notify=True)
                        want = None
                    break
                if step.action == "withdraw" and want is not None:
                    # 该撤的没撤掉，后面的上助战/补人前提不成立，下一轮重新看
                    break
        else:
            state = self._observe_lineup(need_map=False)
        if wanted is not None and not self._borrowed_support:
            self.log_info(f"助战 {wanted.name} 没能上场", notify=True)
            self.debug_shot("support_not_deployed")
        full = state is not None and state.capacity is not None and state.used() >= state.capacity
        if not full:
            self.log_info(
                f"阵容没上满（{state.used() if state else '?'}/{state.capacity if state else '?'}）", notify=True
            )
        self.debug_shot("lineup_done")
        return full

    @staticmethod
    def _step_key(step):
        return step.action, step.unit.name, step.unit.power, step.unit.support

    # ------------------------------------------------------------------ 观察
    def _observe_lineup(self, need_map=True, want=None):
        """读顶部 n/m、我的人形面板（打勾=在场），需要时再点地图上的单位找出场上的助战。"""
        count = self._deploy_count()
        if count is not None:
            self._lineup_capacity = count[1]
        own = self._observe_own()
        supports = []
        own_on = sum(1 for u in own if u.deployed)
        known = self._borrowed_support or (want.name if want is not None and want.deployed else None)
        if need_map and known and (count is None or count[0] - own_on == 1):
            # 要借的助战已经在场（这次刚放上去的，或好友助战列表里它打了勾），不用再挨个点地图
            # （实录 2026-10-20 LA-1-3：游戏沿用了上一关的助战，点地图没认出来，白撤了一个人；
            #  13-1：顶部只读到「4」没读到「/4」，又去点地图，没认出助战，白试了一分钟部署）
            supports = [Unit(known, 0, deployed=True, support=True)]
        elif need_map and (count is None or count[0] > own_on):
            # 场上人数比我方打勾的多 = 有助战在场（读不到计数也看一眼）
            supports = self._supports_on_map(own)
        if self._deploy_button()[0] in ("withdraw", "blocked", "swap"):
            self._clear_selection()
        # 顶部 n/m 这一帧没读到时，用这个部署界面里之前读到过的总人数；已上场人数按打勾的卡片 + 场上助战数
        return LineupState(count[1] if count else self._lineup_capacity, count[0] if count else None, own, supports)

    def _open_own_tab(self):
        """切到我的人形并点「全部」筛选（筛选和好友助战共用，借完助战可能还停在某个属性上）。"""
        tab = self._click_tab("我的人形")
        fx, fy = filter_point(tab, "全部", self.width, self.height, my_tab=True)
        self.click_relative(fx / self.width, fy / self.height, after_sleep=0.8)
        self.next_frame()
        return tab

    def _observe_own(self):
        self._open_own_tab()
        cards = self._scan_cards()
        # 「强制出战」的卡勾是灰白的（不是橙勾），也算在场，并且撤不下来（实录 2026-10-21 LA-1-5）
        mark_forced(cards, self._ocr_panel(PANEL_BOX, match=forced_re), self.width, self.height)
        units = []
        for c in cards:
            forced = c.get("forced", False)
            on = forced or is_orange_check(self.frame, *check_point(c, self.width, self.height))
            units.append(Unit(c["name"], c["power"], deployed=on, locked=forced, ref=c))
        for u in units:
            if u.deployed and not u.name:
                # 在场的必须知道名字（同名判断要用），立绘没认出来就点一下读
                u.name = self._click_card(u.ref) or None
        self.debug_shot("lineup_own", [u.ref["power_box"] for u in units if u.deployed])
        return units

    def _supports_on_map(self, own):
        """逐个点地图上有人的地格：能撤回、名字又不是我方在场人形的，就是助战。"""
        names = [u.name for u in own if u.deployed and u.name]
        out = []
        for tile, desc in self._unit_tiles():
            self.click_relative(tile[0] / self.width, tile[1] / self.height, after_sleep=0.8)
            self.next_frame()
            name = self._selected_role_name()
            kind, _ = self._deploy_button()
            if kind == "withdraw" and name and not any(self._name_like(name, n) for n in names):
                out.append(Unit(name, 0, deployed=True, support=True, ref=tile))
            self._clear_selection()
        return out

    # ------------------------------------------------------------------ 撤人
    def _withdraw(self, step):
        u = step.unit
        if u.support:
            ok = self._withdraw_at(u.ref, u.name, step.why)
        else:
            ok = self._withdraw_own_card(u, step.why)
        if not ok:
            self.log_info(f"没撤下 {u.name}（{step.why}）", notify=True)
        return ok

    def _locate_own_card(self, u):
        """
        重新扫一遍我的人形，按战力（和名字）找到这张卡现在的位置。
        面板里在场的卡片排在前面，撤下/补上一个人后顺序就变了（实录 2026-10-20：撤下威玛西娜后按旧位置点，
        点到的是威玛西娜而不是要补的 OTs-14），所以不能用观察时记下的坐标。
        """
        self._open_own_tab()
        cards = self._scan_cards()
        same = [c for c in cards if c["power"] == u.power]
        named = [c for c in same if u.name and c["name"] and self._name_like(c["name"], u.name)]
        card = (named or same or [None])[0]
        if card is None:
            self.log_info(f"面板上没找到 {u.name}（战力 {u.power}）", notify=False)
        return card

    def _withdraw_own_card(self, u, why):
        """
        在地图上找到这个单位再撤。面板上点在场的卡片不行：实录 2026-10-20 两次都只是选中卡片
        （按钮是「请点击地格」），不会出现「撤回人形」。地图上的候选格子按编号标签 + 地格找，逐个点开核对名字。
        """
        for tile, desc in self._unit_tiles():
            if self._withdraw_at(tile, u.name, why, quiet=True):
                return True
        return False

    def _withdraw_at(self, tile, name, why, quiet=False):
        self.click_relative(tile[0] / self.width, tile[1] / self.height, after_sleep=0.8)
        self.next_frame()
        kind, button = self._deploy_button()
        if kind != "withdraw" or not self._name_like(self._selected_role_name(), name):
            self._clear_selection()
            if not quiet:
                self.log_info(f"重新点中 {name} 失败，没撤回", notify=False)
            return False
        return self._press_withdraw(button, name, why, tile)

    def _press_withdraw(self, button, name, why, tile=None):
        before = self.frame.copy() if self.frame is not None else None
        self.click(button, after_sleep=1)
        self.next_frame()
        if self._deploy_button()[0] == "withdraw" and self._name_like(self._selected_role_name(), name):
            self.log_info(f"点了撤回 {name} 但它还在", notify=False)
            return False
        spot = freed_tile(before, self.frame, self.width, self.height) or tile
        if spot:
            self._freed_tiles.insert(0, spot)
        self.log_info(f"撤下 {name}（{why}），空出地格 {tuple(int(v) for v in spot) if spot else '未知'}", notify=True)
        self.debug_shot("withdrawn")
        return True

    # ------------------------------------------------------------------ 上人
    def _deploy(self, step, want):
        u = step.unit
        before = self._deploy_count()
        if u.support:
            u.ref["reselect"]()
            self.next_frame()
            ok = self._place_selected(f"助战 {u.ref['label']}", u.name, before=before, reselect=u.ref["reselect"])
            if ok:
                self._borrowed_support = u.name
        else:
            card = self._locate_own_card(u)
            if card is None:
                return False
            reselect = self._own_reselect(card)
            reselect()
            name = self._selected_role_name() or u.name
            if want is not None and self._name_like(name, want.name):
                self.log_info(f"{name} 和助战同名，不补", notify=False)
                return False
            if not u.name and name:
                self._learn_card(card, name)
            ok = self._place_selected(
                f"我的人形 {name}（战力 {u.power}，{step.why}）", name, before=before, reselect=reselect
            )
        if ok and self._freed_tiles:
            self._freed_tiles.pop(0)
        return ok

    def _own_reselect(self, card):
        x, y = card["center"]

        def _do():
            self._open_own_tab()
            self.click_relative(x / self.width, y / self.height, after_sleep=0.8)
            self.next_frame()

        return _do

    # ------------------------------------------------------------------ 选助战
    def _choose_support(self, role, min_badge, fallback):
        """
        在好友助战里选一张卡：椎数达标的 role（按战力），否则（开了兜底）「全部」里战力最高的。
        返回 Unit(support=True, ref={"reselect", "label"}) 或 None。
        """
        tab = self._click_tab("好友助战")
        if role:
            attr = self.get_role_by_name(role)
            fx, fy = filter_point(tab, attr, self.width, self.height)
            self.click_relative(fx / self.width, fy / self.height, after_sleep=1)
            self.next_frame()
            cards = self._scan_cards()
            self.debug_shot("support_scan", [c["power_box"] for c in cards])
            if cards and all(c["badge"] is None for c in cards):
                # 一张都没认出椎数，多半是识别坏了（实录 2026-10-20 2560x1440 下蓝圈颜色对不上），不是真没有
                self.log_info(f"好友助战 {len(cards)} 张卡片的椎数一个都没认出来，换一帧再认", notify=True)
                self.sleep(0.5)
                self.next_frame()
                cards = self._scan_cards()
            candidates = pick_candidates(cards, min_badge)
            candidates = [c for c in candidates if c["name"] is None or self._name_like(c["name"], role)]
            candidates.sort(key=lambda c: (c["name"] != role, c["name"] is None, -c["power"]))
            self.log_info(
                f"好友助战({attr or '全部'}) 识别 {len(cards)} 张 {[(c['name'], c['badge'], c['power']) for c in cards]}，"
                f"椎数>={min_badge} 且可能是 {role} 的 {len(candidates)} 张",
                notify=False,
            )
            for c in candidates:
                name = self._click_card(c)
                if self._name_like(name, role):
                    return self._support_unit(c, name, f"{c['badge']}椎 {name}（战力 {c['power']}）", (fx, fy))
                self.log_info(f"{c['badge']}椎 战力{c['power']} 是 {name}，不是 {role}，跳过", notify=False)
            self.log_info(f"没有 {min_badge} 椎及以上的 {role} 助战", notify=True)
        if not fallback:
            return None
        self._click_tab("好友助战")
        fx, fy = filter_point(tab, "全部", self.width, self.height)
        self.click_relative(fx / self.width, fy / self.height, after_sleep=1)
        self.next_frame()
        cards = self._scan_cards()
        self.debug_shot("support_scan_all", [c["power_box"] for c in cards])
        self.log_info(f"兜底借战力最高：全部列表 {[(c['name'], c['badge'], c['power']) for c in cards]}", notify=False)
        for c in cards[:3]:
            name = self._click_card(c)
            if name:
                return self._support_unit(c, name, f"战力最高 {name}（{c['badge']}椎 战力 {c['power']}）", (fx, fy))
            self.log_info(f"战力 {c['power']} 的卡片点了没读到名字，跳过", notify=False)
        return None

    def _support_unit(self, card, name, label, filter_xy):
        x, y = card["center"]
        fx, fy = filter_xy

        def reselect():
            self._click_tab("好友助战")
            self.click_relative(fx / self.width, fy / self.height, after_sleep=0.8)
            self.click_relative(x / self.width, y / self.height, after_sleep=0.8)

        self.next_frame()
        on = is_orange_check(self.frame, *check_point(card, self.width, self.height))
        self.log_info(f"选定助战 {label}{'（已在场上）' if on else ''}", notify=True)
        return Unit(name, card["power"], deployed=on, support=True, ref={"reselect": reselect, "label": label})
