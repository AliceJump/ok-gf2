"""
周常各项的入口和峰值推定页确认。
实录 2026-11-03：新一期第一次进峰值推定没认出「常规峰值」，原流程每找不到一样东西就按一次 ESC，连按 6 次退过主页开出「个人信息」，
扩编实练接着找「战役推进」超时，整个周常报错停掉；极限峰值新一期部署界面是空的，「作战开始」点不动。
"""

import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

source = Path(__file__).resolve().parents[1] / "src/tasks/WeeklyTask.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
namespace = {"re": re}
for node in tree.body:
    if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "peak_tab_re" for t in node.targets):
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "WeeklyTask")
methods = [
    n
    for n in cls.body
    if isinstance(n, ast.FunctionDef) and n.name in {"_open_simulation", "_peak_page_ready", "peak_estimate_tion"}
]
exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), namespace)


def pattern(match):
    return match.pattern if isinstance(match, re.Pattern) else str(match)


class Game:
    """按调用顺序记下点了什么、按了几次 ESC；campaign_misses = 前几次找不到「战役推进」，peak_tabs = 每次看右下角能不能认出标签。"""

    _open_simulation = namespace["_open_simulation"]
    _peak_page_ready = namespace["_peak_page_ready"]
    peak_estimate_tion = namespace["peak_estimate_tion"]

    def __init__(self, campaign_misses=0, peak_tabs=(True,), peak_levels=("01",), lose=False):
        self.campaign_misses = campaign_misses
        self.peak_levels = peak_levels
        self.lose = lose
        self.peak_tabs = list(peak_tabs)
        self.clicks = []
        self.backs = 0
        self.mains = 0
        self.kinds = []
        self.battles = []
        self.logs = []
        self.shots = []

    def ensure_main(self, **kwargs):
        self.mains += 1

    def wait_click_ocr(self, *, match, raise_if_not_found=False, **kwargs):
        name = pattern(match)
        if name == "战役推进" and self.campaign_misses > 0:
            self.campaign_misses -= 1
            if raise_if_not_found:
                raise Exception("没找到战役推进")
            return None
        if name == "常规峰值" or (name in ("01", "02", "03") and name not in self.peak_levels):
            return None
        self.clicks.append(name)
        return [SimpleNamespace(name=name)]

    def wait_ocr(self, *, match, **kwargs):
        name = pattern(match)
        if name == pattern(namespace["peak_tab_re"]):
            seen = self.peak_tabs.pop(0) if self.peak_tabs else False
            return [SimpleNamespace(name="极限峰值")] if seen else None
        if name == "['开始作战']":
            return [SimpleNamespace(name="开始作战")]
        if name == "极限峰值":
            return [SimpleNamespace(name="极限峰值")]
        return None

    def click(self, box, **kwargs):
        pass

    def _tab_selected(self, match):
        return True

    def set_lineup_kind(self, kind):
        self.kinds.append(kind)

    def auto_battle(self, **kwargs):
        self.battles.append(self.kinds[-1])
        if self.lose:
            raise Exception("任务失败, 没打过!")

    def back(self, **kwargs):
        self.backs += 1

    def wait_pop_up(self, **kwargs):
        pass

    def screenshot(self, name=None, **kwargs):
        self.shots.append(name)

    def info_set(self, *args):
        pass

    def log_info(self, message, **kwargs):
        self.logs.append(message)


class OpenSimulationTest(unittest.TestCase):
    def test_goes_home_first_then_clicks_through(self):
        game = Game()
        game._open_simulation("扩编实练")
        self.assertEqual(1, game.mains)
        self.assertEqual(["战役推进", "模拟作战", "扩编实练"], game.clicks)

    def test_campaign_missing_goes_home_again(self):
        """实录 2026-11-03：回主页那一刻还认成主页，随后开出了「个人信息」；找不到「战役推进」就再回一次主页。"""
        game = Game(campaign_misses=1)
        game._open_simulation("扩编实练")
        self.assertEqual(2, game.mains)
        self.assertEqual(["战役推进", "模拟作战", "扩编实练"], game.clicks)

    def test_campaign_missing_twice_raises(self):
        game = Game(campaign_misses=2)
        with self.assertRaises(Exception):
            game._open_simulation("扩编实练")
        self.assertEqual(2, game.mains)


class PeakPageTest(unittest.TestCase):
    def test_page_recognised(self):
        game = Game(peak_tabs=[True])
        self.assertTrue(game._peak_page_ready())
        self.assertEqual(0, game.backs)

    def test_one_esc_closes_cover_then_recognised(self):
        game = Game(peak_tabs=[False, True])
        self.assertTrue(game._peak_page_ready())
        self.assertEqual(1, game.backs)

    def test_unknown_page_skips_without_blind_esc(self):
        """认不出峰值推定页时最多按一次 ESC，然后回主页跳过，不再连按 ESC 退出主页。"""
        game = Game(peak_tabs=[False, False])
        game.peak_estimate_tion()
        self.assertEqual(1, game.backs)
        self.assertEqual([], game.battles)
        self.assertEqual(2, game.mains)  # 入口一次 + 跳过时回主页一次
        self.assertTrue(any("没认出峰值推定页面" in m for m in game.logs))

    def test_extreme_peak_battle_uses_peak_lineup(self):
        """实录 2026-11-03：新一期极限峰值部署界面是空的，开战要按「峰值推定编队」整理阵容，打完恢复。"""
        game = Game(peak_tabs=[True])
        game.peak_estimate_tion()
        self.assertEqual(["峰值推定"], game.battles)
        self.assertEqual(["峰值推定", None], game.kinds)

    def test_extreme_peak_lost_stops_without_failing_weekly(self):
        """实录 2026-11-03：子群1 推荐 60 级、编队打输了；原来整个周常报错停掉。现在记下来、不再打更难的子群，回主页接着下一项。"""
        game = Game(peak_tabs=[True], peak_levels=("01", "02", "03"), lose=True)
        game.peak_estimate_tion()
        self.assertEqual(["峰值推定"], game.battles)
        self.assertEqual(["峰值推定", None], game.kinds)
        self.assertTrue(any("没打过" in m for m in game.logs))
        self.assertEqual(2, game.mains)  # 入口一次 + 结束回主页一次

    def test_extreme_peak_wins_go_on(self):
        game = Game(peak_tabs=[True], peak_levels=("01", "02", "03"))
        game.peak_estimate_tion()
        self.assertEqual(["峰值推定"] * 3, game.battles)


if __name__ == "__main__":
    unittest.main()
