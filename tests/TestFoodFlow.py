"""用可见页面和弹窗状态验证吃饭，不发送游戏输入。已有菜品生效时只取消、不覆盖（覆盖会再花一遍材料）。"""

import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

source = Path(__file__).resolve().parents[1] / "src/tasks/daily/daily_activity_mixin.py"
task_class = next(n for n in ast.parse(source.read_text(encoding="utf-8")).body if isinstance(n, ast.ClassDef))
method = next(n for n in task_class.body if isinstance(n, ast.FunctionDef) and n.name == "do_food_flow")
namespace = {"re": re}
exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), namespace)


class FoodScreen:
    do_food_flow = namespace["do_food_flow"]

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
        self.box = SimpleNamespace(bottom_right="bottom_right", bottom="bottom")

    def box_of_screen(self, *bounds):
        """以归一化边界表示识别区域。"""
        return bounds

    def _skip_active_food_buff(self, next_match=None, stay_match=None):
        """模拟已有菜品生效的弹窗：只点「取消」回到选菜页，绝不确认覆盖（会把材料再花一遍）。"""
        if self.state != "overwrite":
            return None
        self.clicks.append("取消")
        self.state = "menu"
        return True

    def log_info(self, *args, **kwargs):
        """忽略运行日志。"""
        pass

    def press_keys_sequence(self, keys, holds, **kwargs):
        """找不到入口时的前后微调走位，不改变可见页面。"""
        pass

    def sleep(self, *args):
        """不做真实等待。"""
        pass

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
            "result": ["确认"],
            "finished": [],
        }["overwrite" if self.state == "closing" else self.state]

    @staticmethod
    def matches(match, text):
        """兼容生产流程使用的正则和字符串匹配。"""
        return bool(match.search(text)) if hasattr(match, "search") else match in text

    def wait_ocr(self, *, match=None, box=None, **kwargs):
        """推进关闭动画并按识别区域筛选当前可见文字。"""
        if self.state == "closing":
            if self.dismiss_frames:
                self.dismiss_frames -= 1
            else:
                self.state = "invite"
        labels = self.visible()
        if self.state in ("overwrite", "closing") and isinstance(box, tuple):
            labels = [
                label for label in labels
                if box[0] <= (self.prompt_position if label == self.prompt else self.confirm_position)[0] <= box[2]
                and box[1] <= (self.prompt_position if label == self.prompt else self.confirm_position)[1] <= box[3]
            ]
        if match is None:
            return labels
        return [label for label in labels if self.matches(match, label)]

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
            self.state = "result"
        elif self.state == "result":
            self.state = "finished"
        return True

    def skip_dialogs(self, **kwargs):
        """只允许已完成确认的结果页跳过对话。"""
        assert self.state == "result", "不能跳过尚未完成确认的流程"
        self.dialogs_skipped = True

    def wait_pop_up(self, **kwargs):
        """要求结果页已关闭才接受流程完成。"""
        assert self.state == "finished"

    def back(self, **kwargs):
        """将模拟页面返回入口以支持再次检查。"""
        self.state = "entry"

    def screenshot(self, name):
        """记录失败路径截图请求。"""
        self.screenshots.append(name)

    def run(self):
        """用吃饭或饮品参数执行真实 do_food_flow 方法。"""
        return self.do_food_flow(
            enter_func=lambda **kw: None,
            entry_match=re.compile("茶歇一刻" if self.drink else "美味烹调"),
            main_btn="制作" if self.drink else "下一步",
            second_btn="确认" if self.drink else "确认邀请",
            skip_end_match=["饮品加成" if self.drink else "前往战役"],
            need_extra_confirm=not self.drink,
            need_again_test=not self.drink,
        )


class FoodFlowTest(unittest.TestCase):
    def test_existing_dish_is_cancelled_not_overwritten(self):
        """已有菜品生效时点「取消」当作今天已吃过，不点覆盖确认、不进邀请页。"""
        task = FoodScreen()
        self.assertIs(True, task.run())
        self.assertEqual(["下一步", "取消"], task.clicks)
        self.assertNotIn("确认", task.clicks)
        self.assertFalse(task.dialogs_skipped)

    def test_no_overwrite_goes_straight_to_invitation(self):
        """没有覆盖弹窗时直接继续原有邀请流程。"""
        task = FoodScreen(overwrite=False)
        self.assertIs(True, task.run())
        self.assertEqual(["下一步", "确认邀请", "确认", "确认"], task.clicks)

    def test_missing_invitation_is_failure(self):
        """邀请按钮缺失时不能报告成功。"""
        task = FoodScreen(overwrite=False)
        task.invite_present = False
        self.assertEqual("confirm", task.run())
        self.assertEqual(["下一步"], task.clicks)
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
