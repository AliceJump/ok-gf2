"""用可见页面和弹窗状态验证吃饭，不发送游戏输入。"""

import ast
import re
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

source = Path(__file__).resolve().parents[1] / "src/tasks/daily/daily_activity_mixin.py"
task_class = next(n for n in ast.parse(source.read_text(encoding="utf-8")).body if isinstance(n, ast.ClassDef))
method = next(n for n in task_class.body if isinstance(n, ast.FunctionDef) and n.name == "do_food_flow")
namespace = {"re": re}
exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace)
base_source = source.parents[2] / "core/BaseGfTask.py"
base_tree = ast.parse(base_source.read_text(encoding="utf-8"))
base_methods = [n for n in ast.walk(base_tree) if isinstance(n, ast.FunctionDef) and n.name == "_confirm_meal_result"]
exec(compile(ast.Module(body=base_methods, type_ignores=[]), str(base_source), "exec"), namespace)
dialog_namespace = {"re": re, "time": time, "pop_ups": ["点击空白处关闭"]}
dialog_method = next(n for n in ast.walk(base_tree) if isinstance(n, ast.FunctionDef) and n.name == "skip_dialogs")
exec(compile(ast.Module(body=[dialog_method], type_ignores=[]), str(base_source), "exec"), dialog_namespace)


class FoodScreen:
    do_food_flow = namespace["do_food_flow"]
    if "_confirm_meal_result" in namespace:
        _confirm_meal_result = namespace["_confirm_meal_result"]

    def __init__(self, *, overwrite=True, drink=False):
        """初始化菜品覆盖、邀请和饮品流程的可见状态。"""
        self.state = "entry"
        self.overwrite = overwrite
        self.drink = drink
        self.prompt = "同名菜品已生效，番茄鱼汤可能覆盖已生效菜品，是否确认继续"
        self.confirm_label = "确认"
        self.prompt_position = (0.50, 0.45)
        self.confirm_position = (0.62, 0.65)
        self.confirm_works = True
        self.dismiss_frames = 0
        self.invite_present = True
        self.extra_present = True
        self.entry_present = True
        self.main_present = True
        self.clicks = []
        self.unsafe_clicks = []
        self.screenshots = []
        self.dialogs_skipped = False
        self.result_clicks_dropped = 0
        self.result_confirm_label = "确认"
        self.reward_popup = False
        self.hud_present = True
        self.warnings = []
        self.cooking_failures = 0
        self.cooking_attempts = 0
        self.return_clicks_dropped = 0
        self.return_button_present = True
        self.return_label = "返回烹饪"
        self.return_works = True
        self.retry_menu_present = True
        self.entry_moves = []
        self.unknown_result = False
        self.now = 0
        self.blind_clicks = []
        self.box = SimpleNamespace(bottom_right="bottom_right", bottom="bottom")

    def box_of_screen(self, *bounds):
        """以归一化边界表示识别区域。"""
        return bounds

    def _skip_active_food_buff(self, next_match=None):
        """模拟无重复饮食提示时继续当前流程。"""
        return None

    def _confirm_drink_result(self):
        """模拟点击饮品结果页确认并返回活动层。"""
        return self.wait_click_ocr(match=re.compile(r"^\s*确\s*认\s*$"), box=self.box.bottom)

    def visible(self):
        """返回当前页面可见文字，关闭动画期间保留弹窗。"""
        return {
            "entry": ["茶歇一刻" if self.drink else "美味烹调"] if self.entry_present else [],
            "menu": ["制作" if self.drink else "下一步"] if self.main_present else [],
            "overwrite": [self.prompt, "取消", self.confirm_label],
            "invite": ["确认邀请"] if self.invite_present else [],
            "extra": ["确认"] if self.extra_present else [],
            "drink_confirm": ["确认"],
            "result": ["用餐效果", "前往战役", self.result_confirm_label],
            "unknown": ["无法辨识的结果"],
            "cooking_failed": ["失败", "烹调熟练度+1", "确认"]
            + ([self.return_label] if self.return_button_present else []),
            "reward": ["点击空白处关闭"],
            "finished": ["Esc", "P", "M", "F1", "F2", "F3", "F4"] if self.hud_present else [],
        }["overwrite" if self.state == "closing" else self.state]

    @staticmethod
    def matches(match, text):
        """兼容生产流程使用的正则和字符串匹配。"""
        if isinstance(match, list):
            return any(FoodScreen.matches(item, text) for item in match)
        return bool(match.search(text)) if hasattr(match, "search") else match in text

    def wait_ocr(self, *, match=None, box=None, **kwargs):
        """推进关闭动画并按识别区域筛选当前可见文字。"""
        if self.state == "closing":
            if self.dismiss_frames:
                self.dismiss_frames -= 1
            else:
                self.state = "invite"
        labels = self.visible()
        if self.state == "cooking_failed" and box is not None:
            bounds = (
                {"bottom": (0, 0.5, 1, 1), "bottom_right": (0.5, 0.5, 1, 1)}.get(box) if isinstance(box, str) else box
            )
            if bounds:
                positions = {
                    "失败": (0.50, 0.51),
                    "烹调熟练度+1": (0.50, 0.57),
                    "确认": (0.62, 0.79),
                    self.return_label: (0.39, 0.79),
                }
                labels = [
                    label
                    for label in labels
                    if bounds[0] <= positions[label][0] <= bounds[2] and bounds[1] <= positions[label][1] <= bounds[3]
                ]
        if self.state in ("overwrite", "closing") and isinstance(box, tuple):
            labels = [
                label
                for label in labels
                if box[0] <= (self.prompt_position if label == self.prompt else self.confirm_position)[0] <= box[2]
                and box[1] <= (self.prompt_position if label == self.prompt else self.confirm_position)[1] <= box[3]
            ]
        if match is None:
            return labels
        found = [label for label in labels if self.matches(match, label)]
        return [SimpleNamespace(name=label) for label in found] if isinstance(match, list) else found

    def ocr(self, **kwargs):
        """以同一状态模型提供即时文字识别结果。"""
        return self.wait_ocr(**kwargs)

    def wait_until(self, predicate, **kwargs):
        """在有限模拟帧内轮询条件，不执行真实等待。"""
        # 模拟有界轮询，每次调用推进一帧，不在测试中真实等待。
        return any(predicate() for _ in range(4))

    def click_with_key(self, key, result):
        """验证入口快捷键后进入菜单。"""
        assert self.state == "entry" and key == "alt"
        self.state = "menu"

    def wait_click_ocr(self, *, match, box=None, **kwargs):
        """只点击可见匹配项，并记录不受区域或精确匹配保护的覆盖确认。"""
        found = self.wait_ocr(match=match, box=box)
        if not found:
            return False
        label = found[0]
        self.clicks.append(label)
        if self.state == "menu":
            self.state = "drink_confirm" if self.drink else "overwrite" if self.overwrite else "invite"
        elif self.state == "overwrite":
            # 覆盖确认必须精确匹配，并限制在中央弹窗，不能点击取消/确认邀请。
            if not isinstance(box, tuple) or box[0] < 0.20 or box[2] > 0.80 or self.matches(match, "确认邀请"):
                self.unsafe_clicks.append(label)
            if re.sub(r"\s+", "", label) == "确认" and self.confirm_works:
                self.state = "closing" if self.dismiss_frames else "invite"
        elif self.state == "invite":
            self.state = "extra"
        elif self.state in ("extra", "drink_confirm"):
            self.cooking_attempts += 1
            self.state = (
                "unknown"
                if self.unknown_result
                else "cooking_failed"
                if self.cooking_attempts <= self.cooking_failures
                else "result"
            )
        elif self.state == "cooking_failed":
            if self.matches(match, self.return_label):
                if self.return_clicks_dropped:
                    self.return_clicks_dropped -= 1
                elif self.return_works:
                    self.state = "menu"
                    self.main_present = self.retry_menu_present
            elif label == "确认":
                if self.result_clicks_dropped:
                    self.result_clicks_dropped -= 1
                else:
                    self.state = "finished"
        elif self.state == "result":
            if self.result_clicks_dropped:
                self.result_clicks_dropped -= 1
            else:
                self.state = "reward" if self.reward_popup else "finished"
        return True

    def skip_dialogs(self, **kwargs):
        """只允许已完成确认的结果页跳过对话。"""
        if self.state == "unknown":
            # 未知结果场景使用真实 skip_dialogs，仅模拟时钟与游戏 I/O。
            with patch.object(time, "time", lambda: self.now):
                return dialog_namespace["skip_dialogs"](self, **kwargs)
        assert self.state in ("result", "cooking_failed"), "不能跳过尚未完成确认的流程"
        if self.state == "cooking_failed" and not any(
            self.matches(kwargs["end_match"], text) for text in self.visible()
        ):
            raise RuntimeError("跳过剧情超时!")
        self.dialogs_skipped = True
        return [SimpleNamespace(name=text) for text in self.visible() if self.matches(kwargs["end_match"], text)]

    def info_set(self, *args):
        """测试中不写入任务面板。"""

    def find_boxes(self, boxes, *, match, **kwargs):
        """为真实剧情循环筛选当前帧可见文字。"""
        return [box for box in boxes if self.matches(match, box)]

    def _is_loading_frame(self, boxes):
        """未知结果不是加载页。"""
        return False

    def click_relative(self, x, y):
        """记录未知界面上的盲目点击。"""
        self.blind_clicks.append((x, y))

    def sleep(self, seconds):
        """推进模拟时钟，测试不真实等待。"""
        self.now += seconds

    def next_frame(self):
        """模拟每次取帧的有限耗时。"""
        self.now += 0.1

    def wait_pop_up(self, **kwargs):
        """只关闭奖励弹窗，不把点击失败的用餐结果页当作奖励。"""
        if self.state == "reward":
            self.state = "finished"

    def is_free_layer(self, **kwargs):
        """活动层必须显示完整 HUD。"""
        return self.state == "finished" and self.hud_present

    def log_warning(self, message):
        self.warnings.append(message)

    log_error = log_warning

    def back(self, **kwargs):
        """将模拟页面返回入口以支持再次检查。"""
        self.state = "entry"

    def screenshot(self, name):
        """记录失败路径截图请求。"""
        self.screenshots.append(name)

    def run(self):
        """用吃饭或饮品参数执行真实 do_food_flow 方法。"""
        return self.do_food_flow(
            enter_func=lambda **kw: self.entry_moves.append(kw),
            entry_match=re.compile("茶歇一刻" if self.drink else "美味烹调"),
            main_btn="制作" if self.drink else "下一步",
            second_btn="确认" if self.drink else "确认邀请",
            skip_end_match=["饮品加成" if self.drink else "前往战役"],
            need_extra_confirm=not self.drink,
            need_again_test=not self.drink,
        )


class FoodFlowTest(unittest.TestCase):
    def test_failed_result_uses_real_dialog_and_box_matchers(self):
        """生产剧情循环和匹配器能从混合结束条件识别底部失败按钮。"""
        from ok import BaseTask, Box

        task = FoodScreen(overwrite=False)
        boxes = [
            Box(480, 510, 60, 30, name="失败"),
            Box(450, 570, 150, 30, name="烹调熟练度+1"),
            Box(620, 790, 100, 40, name="确认"),
            Box(340, 790, 150, 40, name="返 回 烹 饪"),
        ]
        task.ocr = lambda **kwargs: boxes
        task.find_boxes = BaseTask.find_boxes.__get__(task)
        with patch.object(time, "time", lambda: task.now):
            result = dialog_namespace["skip_dialogs"](
                task,
                end_match=["前往战役", re.compile(r"^\s*返\s*回\s*烹\s*饪\s*$")],
                end_box=Box(0, 500, 1000, 500),
                time_out=3,
                has_dialog=False,
                raise_if_not_found=False,
            )
        self.assertEqual([boxes[-1]], result)
        self.assertEqual([], task.blind_clicks)

    def test_exhausted_exit_rechecks_transient_missing_failed_page(self):
        """退出前短暂漏读失败页时仍使用剩余预算重新识别并确认。"""
        task = FoodScreen(overwrite=False)
        task.cooking_failures = 100
        read_page = task.wait_ocr
        misses = [True]

        def read(**kwargs):
            """只在第三次烹饪后的首次退出检查漏读返回按钮。"""
            if task.state == "cooking_failed" and task.cooking_attempts == 3 and misses:
                misses.pop()
                return None
            return read_page(**kwargs)

        task.wait_ocr = read
        self.assertEqual("confirm", task.run())
        self.assertEqual("finished", task.state)
        self.assertNotIn("cooking_failed_result_blocked", task.screenshots)

    def test_dropped_failed_exit_and_ocr_miss_retries_until_hud(self):
        """退出点击丢失后的单帧漏读不能代替活动层 HUD 确认。"""
        task = FoodScreen(overwrite=False)
        task.cooking_failures = 100
        task.result_clicks_dropped = 1
        click, read_page = task.wait_click_ocr, task.wait_ocr
        misses = []

        def wait_click_ocr(**kwargs):
            """丢失退出确认后，让下一次页面识别短暂超时。"""
            dropped = task.state == "cooking_failed" and task.result_clicks_dropped > 0
            result = click(**kwargs)
            if dropped and task.matches(kwargs["match"], "确认"):
                misses.append(True)
            return result

        def read(**kwargs):
            """模拟点击之后的短暂 OCR 漏读，其余帧保持实际状态。"""
            if task.state == "cooking_failed" and misses:
                misses.pop()
                return None
            return read_page(**kwargs)

        task.wait_click_ocr, task.wait_ocr = wait_click_ocr, read
        self.assertEqual("confirm", task.run())
        self.assertEqual("finished", task.state)
        self.assertEqual(5, task.clicks.count("确认"))

    def test_unknown_page_during_failed_exit_never_blindly_confirms(self):
        """退出时页面持续未知，识别和确认都有界且不盲目点击。"""
        task = FoodScreen(overwrite=False)
        task.cooking_failures = 100
        read_page = task.wait_ocr
        reads = []
        click = task.wait_click_ocr
        exit_confirms = []

        def read(**kwargs):
            """耗尽烹饪次数后持续返回真实超时值。"""
            if task.state == "cooking_failed" and task.cooking_attempts == 3:
                reads.append(True)
                return None
            return read_page(**kwargs)

        def click_ocr(**kwargs):
            """记录未知页退出阶段的确认调用，确保不会盲点。"""
            if task.state == "cooking_failed" and task.cooking_attempts == 3 and task.matches(kwargs["match"], "确认"):
                exit_confirms.append(kwargs)
            return click(**kwargs)

        task.wait_ocr = read
        task.wait_click_ocr = click_ocr
        self.assertEqual("confirm", task.run())
        self.assertEqual("cooking_failed", task.state)
        self.assertEqual(3, task.clicks.count("确认"))
        self.assertEqual([], exit_confirms)
        self.assertEqual([], task.blind_clicks)
        self.assertLessEqual(len(reads), 3)
        self.assertIn("cooking_failed_result_blocked", task.screenshots)

    def test_recipe_recheck_timeout_none_returns_failure_without_exception(self):
        """真实 wait_ocr 超时返回 None 时，未知页仍正常记录失败。"""
        task = FoodScreen(overwrite=False)
        task.cooking_failures = 1
        task.retry_menu_present = False
        read_page = task.wait_ocr
        task.wait_ocr = lambda **kwargs: read_page(**kwargs) or None
        self.assertEqual("confirm", task.run())
        self.assertIn("cooking_retry_menu_missing", task.screenshots)
        self.assertEqual(1, task.cooking_attempts)

    def test_unknown_cooking_result_returns_failure_without_blind_clicks(self):
        """无法识别结果页时不盲点，也不抛出剧情跳过超时。"""
        task = FoodScreen(overwrite=False)
        task.unknown_result = True
        self.assertEqual("confirm", task.run())
        self.assertEqual([], task.blind_clicks)
        self.assertEqual("unknown", task.state)

    def test_recipe_becomes_visible_during_failure_page_recheck(self):
        """配方页在初次等待结束后出现时，复查仍能继续做菜。"""
        task = FoodScreen(overwrite=False)
        task.cooking_failures = 1
        read_page = task.wait_ocr
        delayed = [True]

        def wait_ocr(**kwargs):
            """首次配方识别超时后，下一个有限复查帧显示下一步。"""
            if task.state == "menu" and task.cooking_attempts == 1 and kwargs.get("match") == "下一步" and delayed:
                delayed.pop()
                return []
            return read_page(**kwargs)

        task.wait_ocr = wait_ocr
        self.assertIs(True, task.run())
        self.assertEqual(2, task.cooking_attempts)
        self.assertEqual("finished", task.state)

    def test_transient_entry_ocr_miss_still_allows_bounded_retry(self):
        """交互未切页且入口瞬时漏读时，限时等待应容许饮品和用餐再次交互。"""

        def run_scene(drink):
            """为每个子场景创建独立状态，避免回调捕获循环变量。"""
            task = FoodScreen(drink=drink)
            click_entry, read_page = task.click_with_key, task.wait_ocr
            entry_label = "茶歇一刻" if drink else "美味烹调"
            entry_clicks, misses = [], []

            def click(key, result):
                """第一次交互丢失，并让下一帧入口识别短暂失败。"""
                entry_clicks.append(result)
                if len(entry_clicks) == 1:
                    misses.append(True)
                else:
                    click_entry(key, result)

            def read(**kwargs):
                """只漏读一次原入口，其余文字仍反映真实模拟页面。"""
                if task.state == "entry" and misses and task.matches(kwargs.get("match"), entry_label):
                    misses.pop()
                    return []
                return read_page(**kwargs)

            def wait(**kwargs):
                """入口等待推进多个识别帧，不能等同于一次即时 OCR。"""
                if task.matches(kwargs.get("match"), entry_label):
                    for _ in range(3):
                        if result := read(**kwargs):
                            return result
                    return []
                return read_page(**kwargs)

            task.click_with_key, task.ocr, task.wait_ocr = click, read, wait
            self.assertIs(True, task.run())
            self.assertEqual(2, len(entry_clicks))
            self.assertEqual([], misses)

        for drink in (False, True):
            with self.subTest(drink=drink):
                run_scene(drink)

    def test_dropped_drink_entry_is_retried_while_entry_remains_visible(self):
        """日志中 Alt 点击后仍停留茶歇入口时，应重试交互而非直接失败。"""
        task = FoodScreen(drink=True)
        original = task.click_with_key
        entry_clicks = []

        def drop_first_entry(key, result):
            """丢失首次入口交互，第二次才切换到制作页。"""
            entry_clicks.append(result)
            if len(entry_clicks) > 1:
                original(key, result)

        task.click_with_key = drop_first_entry
        self.assertIs(True, task.run())
        self.assertEqual(2, len(entry_clicks))
        self.assertEqual(["制作", "确认", "确认"], task.clicks)

    def test_stuck_drink_entry_retries_are_bounded(self):
        """入口始终可见但交互无效时，最多点击三次后失败。"""
        task = FoodScreen(drink=True)
        entry_clicks = []
        task.click_with_key = lambda key, result: entry_clicks.append(result)
        self.assertEqual("button", task.run())
        self.assertEqual(3, len(entry_clicks))
        self.assertEqual([], task.clicks)

    def test_missing_drink_menu_on_unknown_page_does_not_reclick_entry(self):
        """入口消失且制作页未知时，不再次发送入口交互。"""
        task = FoodScreen(drink=True)
        entry_clicks = []

        def unknown_page(key, result):
            """首次交互后切到没有原入口的未知页面。"""
            entry_clicks.append(result)
            task.state = "finished"

        task.click_with_key = unknown_page
        self.assertEqual("button", task.run())
        self.assertEqual(1, len(entry_clicks))
        self.assertEqual([], task.clicks)

    def test_failed_cooking_returns_to_recipe_and_retries_to_success(self):
        """失败后返回配方重做，整个流程只移动到入口一次。"""
        task = FoodScreen(overwrite=False)
        task.cooking_failures = 1
        self.assertIs(True, task.run())
        self.assertEqual("finished", task.state)
        self.assertEqual(2, task.cooking_attempts)
        self.assertEqual(1, task.clicks.count("返回烹饪"))
        self.assertEqual(2, task.clicks.count("下一步"))
        self.assertEqual([{"after_sleep": 1}], task.entry_moves)

    def test_failed_result_from_dialog_skip_survives_next_ocr_miss(self):
        """跳剧情已识别失败页时，不因下一帧漏读而放弃重做。"""
        task = FoodScreen(overwrite=False)
        task.cooking_failures = 1
        read_page = task.ocr
        misses = [True]

        def ocr(**kwargs):
            """仅丢弃失败结果页的一次返回按钮识别。"""
            if task.state == "cooking_failed" and task.matches(kwargs.get("match"), "返回烹饪") and misses:
                misses.pop()
                return []
            return read_page(**kwargs)

        task.ocr = ocr
        self.assertIs(True, task.run())
        self.assertEqual(2, task.cooking_attempts)
        self.assertEqual("finished", task.state)

    def test_dropped_return_and_transient_ocr_miss_rechecks_failure_page(self):
        """返回点击丢失且误以为失败页消失时，应重新识别并有限重试。"""
        task = FoodScreen(overwrite=False)
        task.cooking_failures = 1
        task.return_clicks_dropped = 1
        click, read_page = task.wait_click_ocr, task.ocr
        misses = []

        def wait_click_ocr(**kwargs):
            """丢失第一次返回点击后模拟一次文字漏识别。"""
            dropped = task.state == "cooking_failed" and task.return_clicks_dropped > 0
            result = click(**kwargs)
            if dropped and task.matches(kwargs["match"], "返回烹饪"):
                misses.append(True)
            return result

        def ocr(**kwargs):
            """下一次页面消失轮询短暂漏读返回按钮。"""
            if task.state == "cooking_failed" and task.matches(kwargs.get("match"), "返回烹饪") and misses:
                misses.pop()
                return []
            return read_page(**kwargs)

        task.wait_click_ocr, task.ocr = wait_click_ocr, ocr
        self.assertIs(True, task.run())
        self.assertEqual(2, task.cooking_attempts)
        self.assertEqual(2, task.clicks.count("返回烹饪"))
        self.assertEqual("finished", task.state)

    def test_failed_cooking_retry_repeats_overwrite_and_invitation(self):
        """每次重做均重新核验覆盖提示和邀请步骤。"""
        task = FoodScreen()
        task.cooking_failures = 2
        self.assertIs(True, task.run())
        self.assertEqual(3, task.cooking_attempts)
        self.assertEqual(3, task.clicks.count("确认邀请"))
        self.assertEqual([], task.unsafe_clicks)

    def test_repeated_cooking_failures_are_bounded_and_leave_result_screen(self):
        """三次失败后退出结果页并保留失败状态。"""
        task = FoodScreen(overwrite=False)
        task.cooking_failures = 100
        self.assertEqual("confirm", task.run())
        self.assertEqual(3, task.cooking_attempts)
        self.assertEqual("finished", task.state)

    def test_return_to_cooking_retries_dropped_click(self):
        """返回点击丢失时在原结果页重试。"""
        task = FoodScreen(overwrite=False)
        task.cooking_failures = 1
        task.return_clicks_dropped = 1
        self.assertIs(True, task.run())
        self.assertEqual(2, task.cooking_attempts)
        self.assertEqual(2, task.clicks.count("返回烹饪"))

    def test_blocked_return_button_does_not_start_another_cooking_attempt(self):
        """无法返回配方时退出失败页，不盲目继续邀请。"""
        task = FoodScreen(overwrite=False)
        task.cooking_failures = 1
        task.return_works = False
        self.assertEqual("confirm", task.run())
        self.assertEqual(1, task.cooking_attempts)
        self.assertLessEqual(task.clicks.count("返回烹饪"), 3)
        self.assertEqual("finished", task.state)

    def test_exhausted_cooking_retries_dropped_exit_confirmation(self):
        """退出失败页的确认点击丢失时仍进行有限重试。"""
        task = FoodScreen(overwrite=False)
        task.cooking_failures = 100
        task.result_clicks_dropped = 1
        self.assertEqual("confirm", task.run())
        self.assertEqual(3, task.cooking_attempts)
        self.assertEqual("finished", task.state)

    def test_return_to_cooking_accepts_ocr_spaces(self):
        """返回烹饪按钮支持 OCR 在汉字间插入空格。"""
        task = FoodScreen(overwrite=False)
        task.cooking_failures = 1
        task.return_label = "返 回 烹 饪"
        self.assertIs(True, task.run())
        self.assertEqual(2, task.cooking_attempts)

    def test_return_to_unknown_page_does_not_repeat_invitation(self):
        """无法确认配方页时停止重做并避免未知页面点击。"""
        task = FoodScreen(overwrite=False)
        task.cooking_failures = 1
        task.retry_menu_present = False
        self.assertEqual("confirm", task.run())
        self.assertEqual(1, task.cooking_attempts)
        self.assertEqual(1, task.clicks.count("确认邀请"))

    def test_meal_result_retries_dropped_confirmation(self):
        """确认被识别和点击，但游戏未响应时，需要重新确认。"""
        task = FoodScreen(overwrite=False)
        task.result_clicks_dropped = 1
        self.assertIs(True, task.run())
        self.assertEqual("finished", task.state)
        self.assertEqual(3, task.clicks.count("确认"))

    def test_meal_result_stuck_is_failure(self):
        task = FoodScreen(overwrite=False)
        task.result_clicks_dropped = 100
        self.assertEqual("confirm", task.run())
        self.assertEqual("result", task.state)
        self.assertLessEqual(task.clicks.count("确认"), 4)
        self.assertIn("meal_result_blocked", task.screenshots)

    def test_meal_result_missing_confirm_is_failure(self):
        task = FoodScreen(overwrite=False)
        task.result_confirm_label = "确认邀请"
        self.assertEqual("confirm", task.run())
        self.assertEqual("result", task.state)

    def test_meal_result_requires_activity_hud(self):
        task = FoodScreen(overwrite=False)
        task.hud_present = False
        self.assertEqual("confirm", task.run())

    def test_meal_reward_popup_is_closed_before_finishing(self):
        task = FoodScreen(overwrite=False)
        task.reward_popup = True
        self.assertIs(True, task.run())
        self.assertEqual("finished", task.state)

    def test_existing_dish_overwrite_then_invitation_completes(self):
        """已有同名菜品时先确认覆盖，再完成邀请和结果确认。"""
        task = FoodScreen()
        self.assertIs(True, task.run())
        self.assertEqual(["下一步", "确认", "确认邀请", "确认", "确认"], task.clicks)
        self.assertEqual([], task.unsafe_clicks)
        self.assertTrue(task.dialogs_skipped)

    def test_ocr_spaces_in_overwrite_prompt_and_button(self):
        """识别覆盖提示与确认按钮中的 OCR 空白。"""
        task = FoodScreen()
        task.prompt = "覆 盖 已 生 效 菜 品，是否确认继续"
        task.confirm_label = "确 认"
        self.assertIs(True, task.run())
        self.assertEqual([], task.unsafe_clicks)

    def test_overwrite_dialog_can_take_multiple_frames_to_close(self):
        """允许覆盖确认后的关闭动画持续多个识别帧。"""
        task = FoodScreen()
        task.dismiss_frames = 2
        self.assertIs(True, task.run())
        self.assertEqual(["下一步", "确认", "确认邀请", "确认", "确认"], task.clicks)

    def test_no_overwrite_goes_straight_to_invitation(self):
        """没有覆盖弹窗时直接继续原有邀请流程。"""
        task = FoodScreen(overwrite=False)
        self.assertIs(True, task.run())
        self.assertEqual(["下一步", "确认邀请", "确认", "确认"], task.clicks)

    def test_unknown_confirmation_is_not_accepted(self):
        """未知购买提示不能授权点击确认。"""
        task = FoodScreen()
        task.prompt = "是否消耗晶条购买次数"
        self.assertEqual("confirm", task.run())
        self.assertEqual(["下一步"], task.clicks)
        self.assertFalse(task.dialogs_skipped)

    def test_background_overwrite_text_does_not_authorize_dialog_confirmation(self):
        """中央弹窗之外的覆盖文字不能授权确认。"""
        task = FoodScreen()
        task.prompt_position = (0.90, 0.15)
        self.assertEqual("confirm", task.run())
        self.assertEqual(["下一步"], task.clicks)

    def test_background_confirmation_button_is_not_clicked(self):
        """中央弹窗之外的确认按钮不能被点击。"""
        task = FoodScreen()
        task.confirm_position = (0.90, 0.90)
        self.assertEqual("confirm", task.run())
        self.assertEqual(["下一步"], task.clicks)

    def test_missing_overwrite_confirm_does_not_click_invite_label(self):
        """缺少精确确认按钮时不能误点确认邀请。"""
        task = FoodScreen()
        task.confirm_label = "确认邀请"
        self.assertEqual("confirm", task.run())
        self.assertEqual(["下一步"], task.clicks)
        self.assertFalse(task.dialogs_skipped)

    def test_overwrite_dialog_stuck_stops_after_one_confirmation(self):
        """覆盖弹窗卡住时仅点击一次并返回确认失败。"""
        task = FoodScreen()
        task.confirm_works = False
        self.assertEqual("confirm", task.run())
        self.assertEqual(["下一步", "确认"], task.clicks)
        self.assertFalse(task.dialogs_skipped)

    def test_missing_invitation_after_overwrite_is_failure(self):
        """覆盖完成但邀请按钮缺失时不能报告成功。"""
        task = FoodScreen()
        task.invite_present = False
        self.assertEqual("confirm", task.run())
        self.assertEqual(["下一步", "确认"], task.clicks)
        self.assertFalse(task.dialogs_skipped)

    def test_drinking_still_completes(self):
        """饮品流程继续使用原有确认顺序。"""
        task = FoodScreen(drink=True)
        self.assertIs(True, task.run())
        self.assertEqual(["制作", "确认", "确认"], task.clicks)

    def test_missing_entry_or_main_button_remains_failure(self):
        """入口或主按钮缺失时保留对应失败结果。"""
        for stage in ("entry", "button"):
            with self.subTest(stage=stage):
                task = FoodScreen(drink=True)
                task.entry_present = stage != "entry"
                task.main_present = stage != "button"
                self.assertEqual(stage, task.run())
                self.assertEqual([], task.clicks)


if __name__ == "__main__":
    unittest.main()
