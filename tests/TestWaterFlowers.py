import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

source = Path(__file__).resolve().parents[1] / "src/tasks/daily/daily_activity_mixin.py"
node = next(n for n in ast.parse(source.read_text(encoding="utf-8")).body if isinstance(n, ast.ClassDef))
methods = [
    n
    for n in node.body
    if isinstance(n, ast.FunctionDef)
    and n.name
    in (
        "water_flowers",
        "_ensure_activity_panel",
        "free_time_layer",
        "do_food_flow",
        "_route",
        "go_drink",
        "go_eat",
        "_flowerpot_page",
        "_harvest_flower",
        "_plant_seed",
    )
]
DRINK_ROUTE, EAT_ROUTE = "1.087-1.0-0.6", "0.65"
ns = {
    "re": re,
    "DRINK_ROUTE": DRINK_ROUTE,
    "EAT_ROUTE": EAT_ROUTE,
    "LEGACY_ROUTES": {"喝水": ("1.087-1.0-0.8", DRINK_ROUTE), "吃饭": ("1.0", EAT_ROUTE)},
    "parse_time_option": lambda v: [float(x) for x in v.split("-")],
    "NO_SEED": "不种",
}
exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), ns)
water_flowers = ns["water_flowers"]
ensure_panel = ns["_ensure_activity_panel"]
do_food_flow = ns["do_food_flow"]


class ActivityPanelTest(unittest.TestCase):
    def make_task(self, open_after=None, initially_open=False, click_opens=False):
        task = Mock()
        task.box_of_screen.side_effect = lambda *bounds: bounds
        state = {"open": initially_open, "keys": 0}

        def ocr(**kwargs):
            return state["open"]

        def key(*args, **kwargs):
            state["keys"] += 1
            if state["keys"] == open_after:
                state["open"] = True

        def click(**kwargs):
            state["open"] = click_opens
            return True

        task.wait_ocr.side_effect = ocr
        task.send_key.side_effect = key
        task.wait_click_ocr.side_effect = click
        return task

    def test_already_open_never_toggles_f2(self):
        task = self.make_task(initially_open=True)
        self.assertTrue(ensure_panel(task))
        task.send_key.assert_not_called()
        task.wait_click_ocr.assert_not_called()

    def test_successful_first_key_does_not_retry(self):
        task = self.make_task(open_after=1)
        self.assertTrue(ensure_panel(task))
        task.send_key.assert_called_once_with("f2", down_time=0.15, after_sleep=1)
        task.wait_click_ocr.assert_not_called()

    def test_dropped_first_key_retries(self):
        task = self.make_task(open_after=2)
        self.assertTrue(ensure_panel(task))
        self.assertEqual(2, task.send_key.call_count)
        task.wait_click_ocr.assert_not_called()

    def test_keyboard_failure_uses_click(self):
        task = self.make_task(click_opens=True)
        self.assertTrue(ensure_panel(task))
        self.assertEqual(2, task.send_key.call_count)
        task.wait_click_ocr.assert_called_once()

    def test_click_without_open_panel_is_failure(self):
        task = self.make_task()
        self.assertFalse(ensure_panel(task))
        self.assertEqual(2, task.send_key.call_count)
        self.assertIn("F2 面板未打开", task.log_error.call_args.args[0])

    def test_missing_entry_is_failure(self):
        task = self.make_task()
        task.wait_click_ocr.side_effect = None
        task.wait_click_ocr.return_value = False
        self.assertFalse(ensure_panel(task))

    def test_water_stops_before_searching_when_panel_fails(self):
        """Verify water stops before searching when panel fails."""
        task = Mock()
        task._ensure_activity_panel.return_value = False
        self.assertEqual("待核查", water_flowers(task))
        task.wait_ocr.assert_not_called()
        task.wait_click_ocr.assert_not_called()


class WaterFlowersTest(unittest.TestCase):
    def test_progress_rewards_dialog_is_closed_before_cultivation_lookup(self):
        """Verify progress rewards dialog is closed before cultivation lookup."""
        tree = ast.parse(source.read_text(encoding="utf-8"))
        method = next(
            (
                n
                for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "_dismiss_activity_progress_dialog"
            ),
            None,
        )
        self.assertIsNotNone(method, "missing progress dialog recovery")
        local = {"re": re}
        exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), local)
        task = Mock()
        task.box_of_screen.side_effect = lambda *bounds: bounds
        task.wait_ocr.side_effect = [True, False]
        self.assertTrue(local["_dismiss_activity_progress_dialog"](task))
        task.back.assert_called_once_with(after_sleep=1)

    def test_blocked_progress_dialog_stops_before_cultivation_search(self):
        """Verify blocked progress dialog stops before cultivation search."""
        task = Mock()
        task._ensure_activity_panel.return_value = True
        task._dismiss_activity_progress_dialog.return_value = False
        self.assertEqual("待核查", water_flowers(task))
        task.wait_ocr.assert_not_called()
        task.wait_click_ocr.assert_not_called()

    def make_task(
        self,
        overview=False,
        already_done=False,
        succeeds=True,
        missing_tab=False,
        initial_page="tabs",
        overview_text="栽培天数",
    ):
        task = Mock()
        task.box.right = "right"
        task.box.bottom_right = "bottom_right"
        task.width = 1920
        task.height = 1080
        task.box_of_screen.side_effect = lambda *bounds: bounds
        state = {"page": initial_page, "done": already_done}
        clicks = []

        def matches(pattern, text):
            if isinstance(pattern, list):
                return any(matches(p, text) for p in pattern)
            return bool(pattern.search(text)) if isinstance(pattern, re.Pattern) else pattern == text

        def click_ocr(*, match, **kwargs):
            labels = {"tabs": "" if missing_tab else "上栽培", "overview": "前往", "plant": "浇灌"}
            label = labels[state["page"]]
            if not matches(match, label):
                return False
            clicks.append(label)
            if state["page"] == "tabs":
                state["page"] = "overview" if overview else "plant"
            elif state["page"] == "overview":
                state["page"] = "plant"
            else:
                state["done"] = succeeds
            return True

        def ocr(*, match, box, **kwargs):
            if box == (0.13, 0.16, 0.87, 0.82):
                label = {"tabs": "逸趣事件", "overview": overview_text, "plant": "浇灌"}[state["page"]]
                return matches(match, label)
            if state["page"] == "overview":
                return matches(match, overview_text)
            if state["page"] != "plant":
                return False
            # 按钮中心取自 issue #80 日志；次数坐标为旧框下方的模拟样本。
            if box == "right":
                return (
                    [SimpleNamespace(name="浇灌", x=1520, y=568, width=60, height=30)] if matches(match, "浇灌") else []
                )
            left, top, right, bottom = box
            labels = [(1550, 660, "1/1" if state["done"] else "0/1"), (1760, 660, "1/1")]  # 施肥始终已完成
            return [
                SimpleNamespace(name=text)
                for x, y, text in labels
                if left <= x / task.width <= right and top <= y / task.height <= bottom and matches(match, text)
            ]

        task._ensure_activity_panel.side_effect = lambda: ensure_panel(task)
        task._flowerpot_page.side_effect = lambda **kw: ns["_flowerpot_page"](task, **kw)
        task.wait_click_ocr.side_effect = click_ocr
        task.wait_ocr.side_effect = ocr
        return task, clicks

    def test_icon_prefix_from_failure_log_is_accepted(self):
        """Verify icon prefix from failure log is accepted."""
        task, clicks = self.make_task()
        self.assertIs(True, water_flowers(task))
        self.assertEqual(["上栽培", "浇灌"], clicks)
        task.back.assert_called_once()

    def test_overview_requires_go_button(self):
        """Verify overview requires go button."""
        task, clicks = self.make_task(overview=True)
        self.assertIs(True, water_flowers(task))
        self.assertEqual(["上栽培", "前往", "浇灌"], clicks)

    def test_f2_direct_overview_skips_unreadable_tab(self):
        for label in ("栽培天数", "生 长 阶 段"):
            with self.subTest(label=label):
                task, clicks = self.make_task(initial_page="overview", missing_tab=True, overview_text=label)
                self.assertTrue(water_flowers(task))
                self.assertEqual(["前往", "浇灌"], clicks)

    def test_f2_direct_watering_page_skips_tab(self):
        """Verify f2 direct watering page skips tab."""
        task, clicks = self.make_task(initial_page="plant", missing_tab=True)
        self.assertIs(True, water_flowers(task))
        self.assertEqual(["浇灌"], clicks)

    def test_unrelated_go_button_skips_watering(self):
        """Verify unrelated go button skips watering."""
        task, clicks = self.make_task(initial_page="overview", missing_tab=True, overview_text="前往")
        self.assertEqual("待核查", water_flowers(task))
        self.assertEqual([], clicks)

    def test_already_watered_does_not_click_again(self):
        task, clicks = self.make_task(already_done=True)
        self.assertTrue(water_flowers(task))
        self.assertEqual(["上栽培"], clicks)
        task.back.assert_called_once()

    def test_click_without_updated_count_is_failure(self):
        task, _ = self.make_task(succeeds=False)
        self.assertFalse(water_flowers(task))
        task.back.assert_called_once()

    def test_count_region_tracks_button_at_other_resolutions(self):
        task, clicks = self.make_task(initial_page="plant")
        original_ocr = task.wait_ocr.side_effect
        task.width = 2560
        task.height = 1440

        def moved_ocr(*, match, box, **kwargs):
            if box == "right":
                return [SimpleNamespace(name="浇灌", x=2100, y=780, width=80, height=40)]
            if kwargs.get("time_out") in (1, 10):
                left, top, right, bottom = box
                self.assertTrue(left <= 2140 / 2560 <= right)
                self.assertTrue(top <= 900 / 1440 <= bottom)
                self.assertLess(right, 2400 / 2560)  # 不包含施肥列
                return kwargs["time_out"] == 10
            return original_ocr(match=match, box=box, **kwargs)

        task._ensure_activity_panel.side_effect = None
        task._ensure_activity_panel.return_value = True
        task.wait_ocr.side_effect = moved_ocr
        self.assertTrue(water_flowers(task))
        self.assertEqual(["浇灌"], clicks)

    def test_panel_closed_by_progress_esc_is_reopened(self):
        """实录 2026-10-22：关进度窗口的 ESC 把 F2 面板一起关了，要重新打开面板再找栽培。"""
        task, clicks = self.make_task()
        opened = []
        task._ensure_activity_panel.side_effect = lambda: opened.append(1) or ensure_panel(task)
        self.assertIs(True, water_flowers(task))
        self.assertEqual(2, len(opened))
        self.assertEqual(["上栽培", "浇灌"], clicks)

    def test_panel_not_reopened_skips_watering(self):
        task = Mock()
        task._ensure_activity_panel.side_effect = [True, False]
        task._dismiss_activity_progress_dialog.return_value = True
        self.assertEqual("待核查", water_flowers(task))
        task.wait_click_ocr.assert_not_called()
        task.info_set.assert_any_call("浇灌", "已跳过：未识别到栽培入口")

    def test_missing_tab_does_not_water(self):
        """Verify missing tab does not water."""
        task, clicks = self.make_task(missing_tab=True)
        self.assertEqual("待核查", water_flowers(task))
        self.assertEqual([], clicks)
        task.info_set.assert_any_call("浇灌", "已跳过：未识别到栽培入口")


# 实录 2026-11-11 各页 OCR：花熟了的 F2 栽培概览 / 花盆页、收获后的空盆概览、海伦娜那里的选种子页
RIPE_OVERVIEW = [
    "逸趣事件",
    "宜居值",
    "栽培",
    "三色堇",
    "花朵盛放值",
    "90/90",
    "栽培天数",
    "24天",
    "生长阶段",
    "可收获",
]
RIPE_OVERVIEW += ["花朵可收获", "前往"]
RIPE_POT = ["三色堇", "盛放值：90", "栽培天数", "24天", "生长阶段", "可收获", "收获", "获得【三色堇】"]
RIPE_POT += ["当前存在可领取的奖励"]
EMPTY_OVERVIEW = ["逸趣事件", "宜居值", "栽培", "当前未种植花朵，可找到海伦娜进行种植", "前往"]
SEED_PAGE = ["请选择一个种子进行播种", "三色堇", "成熟后可收获【三色堇】", "幽蓝美人", "成熟后可收获【幽蓝美人】"]
SEED_PAGE += ["紫阳花", "成熟后可收获【紫阳花】", "番茄", "成熟后可收获【番茄】", "确认"]
# 播种后的花盆页没有实录，按平时的浇灌页（浇灌 + 下方次数）模拟
NEW_POT = ["三色堇", "栽培天数", "0天", "浇灌", "0/1"]


def text_matches(pattern, text):
    if isinstance(pattern, list):
        return any(text_matches(p, text) for p in pattern)
    return bool(pattern.search(text)) if isinstance(pattern, re.Pattern) else pattern == text


class Cultivation:
    """活动层栽培：花熟了 → 收获弹「获得道具」→ 关掉回到活动层（F2 关了）→ 空盆概览 → 前往 → 选种子 → 确认 → 浇灌。"""

    def __init__(self, ripe=True):
        self.page = "layer"
        self.ripe = ripe
        self.planted = None
        self.selected = "三色堇"  # 选种子页默认选中第一张
        self.harvests = 0
        self.watered = False
        self.clicks = []

    def texts(self):
        if self.page == "overview":
            return RIPE_OVERVIEW if self.ripe else EMPTY_OVERVIEW if not self.planted else ["栽培天数", "前往"]
        if self.page == "pot":
            return RIPE_POT if self.ripe else [*NEW_POT[:-1], "1/1" if self.watered else "0/1"]
        if self.page == "seed":
            return SEED_PAGE
        if self.page == "reward":
            return ["获得道具", "点击空白处关闭"]
        return []

    def find(self, match):
        return [
            SimpleNamespace(name=t, x=500, y=500, width=40, height=20) for t in self.texts() if text_matches(match, t)
        ]

    def tap(self, name):
        self.clicks.append(name)
        if self.page == "overview" and name == "前往":
            self.page = "pot" if self.ripe or self.planted else "seed"
        elif self.page == "pot" and self.ripe and name == "收获":
            self.ripe, self.harvests, self.page = False, self.harvests + 1, "reward"
        elif self.page == "pot" and name == "浇灌":
            self.watered = True
        elif self.page == "seed" and name == "确认":
            self.planted, self.page = self.selected, "pot"
        elif self.page == "seed" and name in SEED_PAGE:
            self.selected = name


class FlowerHarvestTest(unittest.TestCase):
    """实录 2026-11-11：三色堇种了 24 天熟了，花盆页只有「收获」没有浇灌，浇花记待核查、花一直没收。"""

    def make_task(self, screen, seed="三色堇"):
        task = Mock()
        task.width, task.height = 1000, 1000
        task.config = {"栽培种子": seed}

        def open_panel():
            if screen.page == "layer":
                screen.page = "overview"
            return True

        def click_ocr(*, match, **kwargs):
            found = screen.find(match)
            if found:
                screen.tap(found[0].name)
            return found

        def close_popup():
            if screen.page == "reward":
                screen.page = "layer"  # 关掉「获得道具」后回到活动层，F2 面板也关了
            return True

        task._ensure_activity_panel.side_effect = open_panel
        task._dismiss_activity_progress_dialog.return_value = True
        task._close_reward_popup.side_effect = close_popup
        task.wait_ocr.side_effect = lambda *, match, **kw: screen.find(match)
        task.wait_click_ocr.side_effect = click_ocr
        task.click.side_effect = lambda b, **kw: screen.tap(b.name)
        for name in ("water_flowers", "_flowerpot_page", "_harvest_flower", "_plant_seed"):
            getattr(task, name).side_effect = lambda *a, _f=ns[name], **kw: _f(task, *a, **kw)
        return task

    def test_recorded_pages_are_classified(self):
        screen = Cultivation()
        task = self.make_task(screen)
        for page, ripe, kind in (("pot", True, "harvest"), ("seed", False, "seed"), ("overview", True, None)):
            with self.subTest(page=page):
                screen.page, screen.ripe = page, ripe
                self.assertEqual(kind, ns["_flowerpot_page"](task)[0])  # 「可收获」「花朵可收获」不算收获按钮
        screen.page, screen.ripe, screen.planted = "pot", False, "三色堇"
        self.assertEqual("water", ns["_flowerpot_page"](task)[0])

    def test_ripe_flower_is_harvested_replanted_and_watered(self):
        screen = Cultivation()
        task = self.make_task(screen)
        self.assertIs(True, water_flowers(task))
        self.assertEqual(1, screen.harvests)
        self.assertEqual("三色堇", screen.planted)
        self.assertTrue(screen.watered)
        self.assertEqual(["前往", "收获", "前往", "三色堇", "确认", "浇灌"], screen.clicks)
        task.info_set.assert_any_call("栽培", "已收获")
        task.info_set.assert_any_call("栽培", "已播种「三色堇」")

    def test_configured_seed_card_is_picked(self):
        screen = Cultivation()
        task = self.make_task(screen, seed="番茄")
        self.assertIs(True, water_flowers(task))
        self.assertEqual("番茄", screen.planted)

    def test_no_seed_leaves_pot_empty_for_user(self):
        screen = Cultivation()
        task = self.make_task(screen, seed="不种")
        self.assertEqual("待核查", water_flowers(task))
        self.assertEqual(1, screen.harvests)
        self.assertIsNone(screen.planted)
        self.assertNotIn("确认", screen.clicks)
        task.back.assert_called()

    def test_empty_pot_is_planted_then_watered(self):
        screen = Cultivation(ripe=False)
        task = self.make_task(screen)
        self.assertIs(True, water_flowers(task))
        self.assertEqual(0, screen.harvests)
        self.assertEqual(["前往", "三色堇", "确认", "浇灌"], screen.clicks)


class FoodFlowResultTest(unittest.TestCase):
    def test_missing_second_button_reports_confirm_failure(self):
        """Verify missing second button reports confirm failure."""
        task = Mock()
        task.box.bottom_right = "bottom_right"
        task.wait_ocr.return_value = [SimpleNamespace(name="entry")]
        task.wait_click_ocr.side_effect = [True, False]
        task._skip_active_food_buff.return_value = None  # 没弹「已有 xx 生效中，是否确认更换」
        task.ocr.return_value = []  # 没找到第二个按钮时会记录画面文字
        enter_func = Mock()

        result = do_food_flow(
            task,
            enter_func=enter_func,
            entry_match="entry",
            main_btn="制作",
            second_btn="确认",
            skip_end_match=["饮品加成"],
        )

        self.assertEqual("confirm", result)
        enter_func.assert_called_once_with(after_sleep=1)
        task.skip_dialogs.assert_not_called()


class WaterIntegrationTest(unittest.TestCase):
    def test_skipped_water_is_uncertain_and_returns_to_main(self):
        """Verify skipped water is uncertain and returns to main."""
        task = Mock()
        task.config = {"活动层浇花": True}
        task.is_free_layer.return_value = True
        task.do_food_flow.return_value = True
        task.water_flowers.return_value = "待核查"
        self.assertEqual("待核查", ns["free_time_layer"](task))
        self.assertEqual(3, task.ensure_main.call_count)

    def test_water_runs_after_food_and_propagates_failure(self):
        task = Mock()
        task.config = {"活动层浇花": True}
        events = []
        task.is_free_layer.return_value = True
        task.do_food_flow.side_effect = lambda **kw: events.append("food") or True
        task.water_flowers.side_effect = lambda: events.append("water") or False
        self.assertIs(False, ns["free_time_layer"](task))
        self.assertEqual(["food", "food", "water"], events)

    def test_disabled_water_preserves_food_only_flow(self):
        task = Mock()
        task.config = {"活动层浇花": False}
        task.is_free_layer.return_value = True
        task.do_food_flow.return_value = True
        self.assertIs(True, ns["free_time_layer"](task))
        task.water_flowers.assert_not_called()
        self.assertEqual(2, task.do_food_flow.call_count)

    def test_drink_confirm_failure_warns_and_continues(self):
        task = Mock()
        task.config = {"活动层浇花": True}
        task.is_free_layer.return_value = True
        task.do_food_flow.side_effect = ["confirm", True]
        task.water_flowers.return_value = True

        self.assertIs(False, ns["free_time_layer"](task))
        task.log_warning.assert_called_once()
        self.assertIn("确认", task.log_warning.call_args.args[0])
        self.assertEqual(2, task.do_food_flow.call_count)
        task.water_flowers.assert_called_once()

    def test_eat_confirm_failure_marks_incomplete_and_continues(self):
        task = Mock()
        task.config = {"活动层浇花": True}
        task.is_free_layer.return_value = True
        task.do_food_flow.side_effect = [True, "confirm"]
        task.water_flowers.return_value = True

        self.assertIs(False, ns["free_time_layer"](task))
        task.log_warning.assert_called_once()
        self.assertIn("吃饭", task.log_warning.call_args.args[0])
        self.assertEqual(2, task.do_food_flow.call_count)
        task.water_flowers.assert_called_once()

    def test_missing_drink_entry_keeps_key_duration_hint(self):
        task = Mock()
        task.config = {"活动层浇花": False}
        task.is_free_layer.return_value = True
        task.do_food_flow.side_effect = ["entry", True]

        self.assertIs(False, ns["free_time_layer"](task))
        message = task.log_warning.call_args.args[0]
        self.assertIn("茶歇一刻", message)
        self.assertIn("1.087-1.0-0.6", message)

    def test_missing_drink_button_does_not_blame_entry_or_duration(self):
        task = Mock()
        task.config = {"活动层浇花": False}
        task.is_free_layer.return_value = True
        task.do_food_flow.side_effect = ["button", True]

        self.assertIs(False, ns["free_time_layer"](task))
        message = task.log_warning.call_args.args[0]
        self.assertIn("喝水", message)
        self.assertNotIn("茶歇一刻", message)
        self.assertNotIn("1.087-1.0-0.6", message)


class WalkRouteTest(unittest.TestCase):
    """实录 2026-10-21：按键之间停顿时镜头会转到角色身后，走到的位置不稳定；改成连续按键并重新量时长。"""

    def make_task(self, **config):
        task = Mock()
        task.config = config
        task._route = lambda key: ns["_route"](task, key)
        return task

    def test_drink_keys_are_pressed_back_to_back(self):
        task = self.make_task(喝水="1.087-1.0-0.6")
        ns["go_drink"](task)
        task.press_keys_sequence.assert_called_once_with(["a", "w", "d"], [1.087, 1.0, 0.6], sleep_between=0)

    def test_eat_is_a_single_s_press(self):
        task = self.make_task(吃饭="0.7")
        ns["go_eat"](task)
        task.press_keys_sequence.assert_called_once_with(["s"], [0.7], sleep_between=0)

    def test_legacy_defaults_use_new_routes(self):
        task = self.make_task(喝水="1.087-1.0-0.8", 吃饭="1.0")
        ns["go_drink"](task)
        ns["go_eat"](task)
        self.assertEqual(task.press_keys_sequence.call_args_list[0].args[1], [1.087, 1.0, 0.6])
        self.assertEqual(task.press_keys_sequence.call_args_list[1].args[1], [0.65])

    def test_user_tuned_values_are_kept(self):
        task = self.make_task(喝水="1.0-1.1-0.5", 吃饭="")
        ns["go_drink"](task)
        ns["go_eat"](task)
        self.assertEqual(task.press_keys_sequence.call_args_list[0].args[1], [1.0, 1.1, 0.5])
        self.assertEqual(task.press_keys_sequence.call_args_list[1].args[1], [0.65])
