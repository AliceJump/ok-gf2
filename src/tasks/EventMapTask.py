"""
往期活动推图：主页「战役推进」→ 右上「往期活动」→ 左边「活动剧情」，活动卡片从左到右排，卡片下面写「完成度 xx%」。
找第一个完成度不到 100% 的活动点进去，进去后的关卡地图、关卡面板和主线一样（MA-1-1 / MS-1-1 …，「挑战 / 观看」），
所以每关怎么推、阵容怎么整理都直接沿用 ClearMapTask，这里只换「章节」层的导航：
- 主线的「章节选择页 + 章节进度」换成「活动列表 + 卡片上的完成度」；
- 「进下一章」换成「回列表找下一个完成度不到 100% 的活动」。
"""

import re
from difflib import SequenceMatcher

from src.core.BaseGfTask import map_re, nav_tabs_re
from src.core.chapter_reward import card_has_badge, event_badges
from src.tasks.ClearMapTask import DIFFICULTY_FILL, DIFFICULTY_MIN_FILL, ClearMapTask, campaign_re, difficulty_fill

event_percent_re = re.compile(r"完\s*成\s*度\s*(\d{1,3})\s*%")
event_tab_re = re.compile(r"^往期活动$")
event_story_re = re.compile(r"^活动剧情$")
map_tab_re = re.compile(r"^(剧\s*情|物\s*资)$")  # 活动地图右下的页签
EVENT_TITLE_DX = 0.08  # 活动名在「完成度」正上方：中心 x 相差不超过画面宽的这个比例
EVENT_TITLE_DY = (0.02, 0.07)  # 活动名中心在「完成度」中心上方多远（画面高的比例）
EVENT_LIST_DRAG = (0.75, 0.35)  # 拖活动列表时按住的起止 x（相对宽），一次挪两张多卡片，不会跳过
EVENT_LIST_Y = 0.45  # 拖列表的高度：卡片立绘中间
EVENT_LIST_SAME_X = 0.02  # 拖列表前后同一张卡片 x 差不超过画面宽的这个比例，算没挪动
EVENT_LIST_HOLD = 0.5  # 拖到位停多久再松手（秒），不停会甩出惯性
EVENT_LIST_MAX_DRAGS = 30  # 拖到位停住后一次只挪一张卡片（实测），18 个活动、一屏 4 张要拖 14 次
EVENT_MAX = 40  # 一次最多推多少个活动（防止死循环）
EVENT_TABS = ("剧情", "物资")  # 活动地图右下的两个页签，各是一张关卡地图
EVENT_TAB_MIN_S = 50  # 只看到一个页签时，算「实心」的饱和度门槛：纪念日礼赞的选中按钮是灰绿色（S≈70），难度按钮用的 90 认不出
EVENT_TAB_MIN_DV = 20  # 两个页签都在时，选中的要比另一个亮多少（HSV 的 V）：实测选中 129～177，没选中 74～100


def _center(b):
    return b.x + b.width / 2, b.y + b.height / 2


def event_cards(boxes, width, height):
    """
    活动列表上的卡片：每个「完成度 xx%」配上它正上方的活动名，返回 [(活动名框, 完成度)]，按 x 从左到右。
    实录 2026-10-22（2560x1440）：「狂想四重奏」(667,1083)，「完成度0%」(691,1141)。
    """
    titles = [
        b
        for b in boxes
        if not event_percent_re.search(b.name or "") and re.search(r"[一-鿿]{2,}", b.name or "")
    ]
    out = []
    for p in boxes:
        m = event_percent_re.search(p.name or "")
        if not m:
            continue
        px, py = _center(p)
        above = [
            t
            for t in titles
            if abs(_center(t)[0] - px) < EVENT_TITLE_DX * width
            and EVENT_TITLE_DY[0] * height < py - _center(t)[1] < EVENT_TITLE_DY[1] * height
        ]
        if above:
            title = min(above, key=lambda t: py - _center(t)[1])
            out.append((title, min(int(m.group(1)), 100)))
    return sorted(out, key=lambda c: c[0].x)


def same_event(a, b):
    """活动名 OCR 常错一两个字（实录「狂想四重奏」读成「狂想四重秦」），按相似度比；上 / 中 / 下篇不同算两个。"""
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return False
    pa, pb = re.search(r"[上中下]篇", a), re.search(r"[上中下]篇", b)
    if pa and pb and pa.group(0) != pb.group(0):
        return False  # 「密米尔的返演·上篇 / 下篇」只差一个字，是两个活动
    return a in b or b in a or SequenceMatcher(None, a, b).ratio() >= 0.6


def list_moved(before, after, width):
    """
    拖活动列表前后的卡片 [(活动名框, 完成度)]：有同一个活动 x 挪了、或者一张都对不上，算挪动了；同名卡片都还在原位算没挪（到头了）。
    实录 2026-10-22：一次只挪一张时，边上半张卡片读成「离赛博格 / 成度100%」配不上对，新露出的「素银匿信」只读到「完成度」，
    前后都只剩中间三张、名字一样，按名字比被当成到头，后面三个活动没推就收工了。
    """
    if not before or not after:
        return [t.name for t, _ in before] != [t.name for t, _ in after]
    shared = [(a, b) for a, _ in after for b, _ in before if same_event(a.name, b.name)]
    return not shared or any(abs(a.x - b.x) > EVENT_LIST_SAME_X * width for a, b in shared)


def pick_event(cards, skip):
    """第一个完成度不到 100%、这次还没放弃过的活动。"""
    for title, percent in cards:
        if percent < 100 and not any(same_event(title.name, s) for s in skip):
            return title, percent
    return None


def event_title_on_map(boxes, width, height):
    """
    活动地图顶部正中：小字活动名在「活动剧情」上面一行。同一行可能被 OCR 拆成几个框
    （实录 2026-10-22「密米尔的返演·上篇」只读出「密米尔的返演」，上篇 / 下篇分不清），按 x 拼起来。
    活动名上面可能还有一行装饰英文（实录「前进吧，王牌配送员！」上面是「SAKURA」），从上往下取第一行有中文的。
    """
    cands = sorted(
        (
            b
            for b in boxes
            if b.y < 0.06 * height
            and 0.3 * width < _center(b)[0] < 0.7 * width
            and (b.name or "").strip()
            and not event_story_re.search(b.name or "")
        ),
        key=lambda b: b.y,
    )
    while cands:
        top = cands[0]
        line = [b for b in cands if abs(_center(b)[1] - _center(top)[1]) < 0.015 * height]
        title = "".join(b.name.strip() for b in sorted(line, key=lambda b: b.x))
        if re.search(r"[\u4e00-\u9fff]{2,}", title):
            return title
        cands = [b for b in cands if b not in line]
    return None


def button_brightness(frame, box, height):
    """按钮文字周围一块的平均亮度（HSV 的 V，取 BGR 三通道最大值），区域和 difficulty_fill 一样。"""
    cx, cy = box.x + box.width / 2, box.y + box.height / 2
    dx, dy = DIFFICULTY_FILL[0] * height, DIFFICULTY_FILL[1] * height
    region = frame[max(0, int(cy - dy)) : int(cy + dy), max(0, int(cx - dx)) : int(cx + dx)]
    return float(region.max(axis=2).mean()) if region.size else 0.0


def selected_event_tab(frame, boxes, height):
    """
    「剧情」「物资」哪个是选中的；认不出返回 None。
    选中按钮的颜色每个活动不一样：狂想四重奏橙色、拂晓的回响青色、纪念日礼赞灰绿色、沉没夜潮蓝灰色（饱和度只有 26），
    但都比没选中的灰底亮。所以两个页签都在时比亮度：实测 2560x1440 选中 129～177，没选中 74～100。
    只看到一个页签时退回看是不是实心彩色。
    """
    tabs = {re.sub(r"\s", "", b.name or ""): b for b in boxes}
    tabs = {name: b for name, b in tabs.items() if name in EVENT_TABS}
    if len(tabs) == 2:
        (best, v1), (_, v2) = sorted(
            ((name, button_brightness(frame, b, height)) for name, b in tabs.items()), key=lambda t: -t[1]
        )
        return best if v1 - v2 >= EVENT_TAB_MIN_DV else None
    for name, b in tabs.items():
        if difficulty_fill(frame, b, height, EVENT_TAB_MIN_S) > DIFFICULTY_MIN_FILL:
            return name
    return None


class EventMapTask(ClearMapTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "往期活动推图"
        self.description = (
            "从主页、作战页或活动列表启动：进第一个完成度不到 100% 的往期活动推图，推完回列表找下一个；"
            "停在活动地图上启动就先推当前这个"
        )
        for key in ("推完继续下一章", "难度", "英雄难度"):
            self.default_config.pop(key, None)
            self.config_description.pop(key, None)
        self.config_type.pop("难度", None)
        self.default_config["推完继续下一个活动"] = True
        self.config_description["推完继续下一个活动"] = (
            "当前活动推完（或剩下的关都推不动）后，回往期活动列表进下一个完成度不到 100% 的活动继续推"
        )
        self.default_config["看心智回溯"] = True
        self.config_description["看心智回溯"] = (
            "活动「剧情」页签左边有「心智回溯」（第 8 期起）时，把能看的剧情一条条播放（跳过）领抽卡资源\n"
            "开着「推完继续下一个活动」时，推完还会把列表上右上角带「!」（奖励没领完）的活动逐个进去领章节奖励和心智回溯"
        )
        self.event_name = None
        self.skipped_events = []  # 这次推过 / 推不动的活动，不再回头选

    # ------------------------------------------------------------------ 主流程
    def _run_sweep(self):
        self.event_name = None
        if not getattr(self, "crash_resume", False):
            # 游戏崩溃重跑时保留：已经推完/推不动的活动不用再进去核对一遍（95% 的活动每个要几分钟）
            self.skipped_events = []
        if self.scan_maps():
            self.event_name = event_title_on_map(self.ocr(box="top") or [], self.width, self.height)
            self.log_info(f"停在活动「{self.event_name or '?'}」的地图上，先推这个", notify=True)
        elif not self.enter_next_event():
            self.log_info("往期活动都推到 100% 了", notify=True)
            self.collect_event_rewards()
            return
        total = 0
        for _ in range(EVENT_MAX):
            self.ensure_map()
            self.prepare_chapter()
            count, locked = self.finish_chapter()
            total += count
            self.log_info(f"活动「{self.event_name or '?'}」本次推进 {count} 关，未解锁 {locked or '无'}", notify=True)
            if self.event_name:
                self.skipped_events.append(self.event_name)
            if not self.config.get("推完继续下一个活动", True):
                break
            if not self.enter_next_event():
                self.log_info("没有完成度不到 100% 的往期活动了", notify=True)
                self.collect_event_rewards()
                break
        self.log_info(f"往期活动推图完成, 本次推进 {total} 关", notify=True)

    def collect_event_rewards(self):
        """
        推完以后，把列表上卡片右上角带「!」（奖励没领完）的活动逐个进去：每个页签领章节奖励、看心智回溯。
        实录 2026-10-22：第 11 期素银匿信起的活动都已 100%，章节奖励和心智回溯都没领，推图不会再进这些活动。
        每个活动这次只进一次，领不掉的「!」（比如英雄难度的奖励）不会来回进。
        """
        if not (self.config.get("领取章节奖励", True) or self.config.get("看心智回溯", True)):
            return
        visited = []
        for _ in range(EVENT_MAX):
            self.info_set("current_task", "找奖励没领的往期活动")
            if not self.open_event_list():
                break
            hit = self.find_event(badge_skip=visited)
            if not hit:
                break
            title = hit[0]
            visited.append(title.name.strip())
            self.log_info(f"往期活动「{title.name}」卡片上有「!」（奖励没领完），进去领", notify=True)
            self.click_event(title)
            self.ensure_map()
            for tab in EVENT_TABS:
                if self.switch_event_tab(tab):
                    self.claim_chapter_reward()
                    self.watch_mind_replay()
        self.log_info(f"往期活动奖励领完，进了 {len(visited)} 个活动: {visited}", notify=True)

    def prepare_chapter(self):
        """活动地图没有普通 / 困难、英雄难度。"""
        self.close_map_panel()
        self.hero_mode = False

    def clear_chapter(self):
        """
        活动地图右下有「剧情 / 物资」两个页签，各是一张关卡地图，两边的关卡都算进完成度：先推「剧情」再推「物资」。
        实录 2026-10-22 狂想四重奏：剧情全推完完成度才 75%，剩下的是物资页签的 MF-1-1～（推荐等级 30）；
        拂晓的回响刚进去时「物资」点了没反应（剧情没推到解锁），这种就跳过，下一轮再试。
        """
        total, locked = 0, []
        for tab in EVENT_TABS:
            if not self.switch_event_tab(tab):
                continue
            count, tab_locked = super().clear_chapter()
            self.watch_mind_replay()
            total += count
            locked += tab_locked
        return total, locked

    def read_event_tab(self):
        """右下「剧情 / 物资」-> (选中的页签, {页签名: 按钮框})；没有页签返回 (None, {})。"""
        self.next_frame()
        boxes = self.ocr(box="bottom_right", match=map_tab_re) or []
        buttons = {re.sub(r"\s", "", b.name): b for b in boxes}
        return selected_event_tab(self.frame, boxes, self.height), buttons

    def switch_event_tab(self, tab):
        """
        切到右下的「剧情 / 物资」页签，返回切没切过去。按按钮是不是实心彩色认选中（同难度按钮）。
        实录 2026-10-22 密米尔的返演·上篇：旧逻辑看「点完地图上的关卡名变没变」，物资还锁着点了没反应，
        但地图视野挪了、关卡名变了，被当成切过去了，把剧情图又扫了一遍。
        """
        self.close_map_panel()
        self.ensure_map()
        current, buttons = self.read_event_tab()
        if not buttons:
            self.log_info("活动地图右下没找到页签", notify=False)
            return tab == EVENT_TABS[0]  # 没有页签的活动只有一张图，当作「剧情」
        for _ in range(2):
            if current == tab:
                self.log_info(f"推活动「{self.event_name or '?'}」的「{tab}」页签", notify=False)
                return True
            if tab not in buttons:
                break
            # 关卡面板刚关、还在收起动画时点页签可能不生效，没切过去再点一次
            self.click(buttons[tab], after_sleep=2)
            self.ensure_map()
            current, buttons = self.read_event_tab()
        if current == tab:
            self.log_info(f"推活动「{self.event_name or '?'}」的「{tab}」页签", notify=False)
            return True
        self.debug_shot(f"event_tab_{tab}")
        self.log_info(f"「{tab}」页签点了没切过去（还没解锁），先不推", notify=True)
        return False

    def chapter_medals(self):
        # 活动地图左下角的「0/45」是活动代币收集进度，不是勋章
        return None

    # ------------------------------------------------------------------ 活动列表
    def on_event_list(self):
        if not self.ocr(box="top", match=nav_tabs_re):
            return False
        return bool(event_cards(self.ocr(log=True) or [], self.width, self.height))

    def open_event_list(self):
        """从活动地图 / 作战的其他页签 / 主页回到往期活动列表。"""
        for _ in range(4):
            if self.on_event_list():
                return True
            self.close_map_panel()
            if self.ocr(box="top", match=nav_tabs_re):
                tab = self.ocr(box="top", match=event_tab_re)
                if tab:
                    self.click(tab, after_sleep=2)
                story = self.ocr(box="left", match=event_story_re)
                if story:
                    self.click(story, after_sleep=2)
                continue
            if entry := self.ocr(box="top_right", match=campaign_re):
                self.log_info("停在游戏主页，点「战役推进」", notify=False)
                self.click(entry, after_sleep=3)
                continue
            if self.scan_maps():
                self.back(after_sleep=2)  # 活动地图按 ESC 回列表
                continue
            if not self.resume_battle(time_out=300):
                self.back(after_sleep=2)
        return self.on_event_list()

    def read_event_cards(self):
        self.next_frame()
        boxes = self.ocr(log=True) or []
        cards = event_cards(boxes, self.width, self.height)
        self.debug_shot("event_list", [t for t, _ in cards])
        return cards

    def drag_event_list(self, direction):
        """
        往右（1）/ 往左（-1）挪活动列表，返回挪完的卡片；没挪动（到头了）返回 None。
        实录 2026-10-22：拖完马上松手会甩出惯性，有一次挪了五六张卡片，把「镜茧与囚蝶」等几个活动整段跳过，
        推完回列表找不到它、读不到完成度。现在拖到位停一下再松手；挪完和挪之前一张都对不上（跳过了卡片），就往回拖半程补看。
        """
        before = self.read_event_cards()
        after = self.swipe_event_list(direction)
        for _ in range(2):
            if after or self.on_event_list():
                break
            # 实录 2026-10-22 13:29：拖动被游戏当成了点击，进了「共诉隐匿时」，读不到卡片被当成到头，
            # 后面带「!」的虚境新始 / 瑞骋迎春至 / 月下安魂曲都没去领
            self.log_info("拖列表时被当成点击、误进了活动，退回列表再拖", notify=False)
            self.open_event_list()
            after = self.swipe_event_list(direction)
        for _ in range(3):
            if not before or not after or any(same_event(t.name, b.name) for t, _ in after for b, _ in before):
                break
            self.log_info("活动列表一次挪过头了（前后卡片对不上），往回拖半程补看")
            after = self.swipe_event_list(-direction, 0.5)
        return after if list_moved(before, after, self.width) else None

    def swipe_event_list(self, direction, scale=1.0):
        """按 EVENT_LIST_DRAG 拖一次（scale 缩放拖动距离），返回拖完的卡片。"""
        a, b = EVENT_LIST_DRAG
        mid, half = (a + b) / 2, (a - b) / 2 * scale * (1 if direction > 0 else -1)
        self.swipe_relative(mid + half, EVENT_LIST_Y, mid - half, EVENT_LIST_Y, duration=0.6, settle_time=EVENT_LIST_HOLD)
        self.sleep(1.5)
        return self.read_event_cards()

    def find_event(self, want=None, badge_skip=None):
        """
        从列表最左边往右找：want 为空找第一个完成度不到 100% 且没放弃过的活动，否则找名字是 want 的那个；
        给了 badge_skip（已进过的活动名）就找第一个卡片右上角带「!」、还没进过的活动。
        返回 (活动名框, 完成度) 或 None。
        """
        if want and (hit := next((c for c in self.read_event_cards() if same_event(c[0].name, want)), None)):
            return hit  # 从活动里退出来列表一般还停在原处，先看当前屏
        for _ in range(EVENT_LIST_MAX_DRAGS):
            if self.drag_event_list(-1) is None:
                break
        cards = self.read_event_cards()
        for _ in range(EVENT_LIST_MAX_DRAGS):
            if want:
                hit = next((c for c in cards if same_event(c[0].name, want)), None)
            elif badge_skip is not None:
                badges = event_badges(self.frame, self.width, self.height)
                hit = next(
                    (
                        c
                        for c in cards
                        if card_has_badge(c[0], badges, self.width)
                        and not any(same_event(c[0].name, v) for v in badge_skip)
                    ),
                    None,
                )
            else:
                hit = pick_event(cards, self.skipped_events)
            if hit:
                return hit
            cards = self.drag_event_list(1)
            if cards is None:
                return None
        return None

    def click_event(self, title):
        """点活动卡片进地图，跳过开场剧情直到看到关卡卡片。"""
        self.event_name = title.name.strip()
        self.info_set("current_task", f"活动 {self.event_name}")
        self.click(title, after_sleep=3)
        self.skip_dialogs(end_match=map_re, time_out=180, has_dialog=True, raise_if_not_found=False)

    def enter_next_event(self):
        """回列表进下一个完成度不到 100% 的活动，返回是否进去了。"""
        self.info_set("current_task", "找下一个往期活动")
        if not self.open_event_list():
            raise Exception("回不到往期活动列表, 请检查游戏画面")
        hit = self.find_event()
        if not hit:
            return False
        title, percent = hit
        self.log_info(f"进往期活动「{title.name}」（完成度 {percent}%）推图", notify=True)
        self.click_event(title)
        return True

    # ------------------------------------------------------------------ 覆盖主线的章节导航
    def chapter_percent(self):
        """回列表读当前活动卡片上的完成度（停在列表上）。"""
        if not self.open_event_list():
            return None
        if not self.event_name:
            return None
        hit = self.find_event(self.event_name)
        if not hit:
            self.log_info(f"列表上没找到活动「{self.event_name}」", notify=True)
            return None
        self.event_name = hit[0].name.strip()  # 列表上的名字比地图顶上的小字可靠，之后都用它
        self.log_info(f"活动「{self.event_name}」完成度 {hit[1]}%", notify=False)
        return hit[1]

    def reenter_from_chapter_select(self):
        """停在活动列表上：点回当前活动；没记住是哪个活动就进第一个没推完的。"""
        if not self.on_event_list():
            return False
        hit = self.find_event(self.event_name) if self.event_name else self.find_event()
        if not hit:
            return False
        self.click_event(hit[0])
        return True

    def open_campaign_from_main(self):
        """停在主页 / 作战其他页签：回到往期活动列表再进当前活动。"""
        if not (self.ocr(box="top_right", match=campaign_re) or self.ocr(box="top", match=nav_tabs_re)):
            return False
        return self.open_event_list() and self.reenter_from_chapter_select()
