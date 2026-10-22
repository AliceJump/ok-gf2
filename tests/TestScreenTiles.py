"""
切块补读（实录 2026-10-22）：整屏 OCR 把 2560 宽的画面缩小后，低对比的小字检测不到——
驻足之地「当前」剧情关 DS-1-1（浅绿底深色字）、瑞骋迎春至未解锁的关（暗红底灰字）；切成 3x2 块分别 OCR 都读得到。
"""

import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

source = Path(__file__).resolve().parents[1] / "src/tasks/ClearMapTask.py"
tree = ast.parse(source.read_text(encoding="utf-8"))
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "ClearMapTask")
nodes = [
    n
    for n in tree.body
    if (isinstance(n, ast.FunctionDef) and n.name in ("screen_tiles", "merge_maps", "order_maps"))
    or (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "TILE_GRID" for t in n.targets))
] + [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in ("scan_maps", "scan_tiles")]
ns = {"re": re, "Box": lambda x, y, w, h: SimpleNamespace(x=x, y=y, width=w, height=h), "map_re": re.compile("x")}
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), ns)
W, H = 2560, 1440


class ScreenTilesTest(unittest.TestCase):
    def test_tiles_cover_screen_with_overlap(self):
        tiles = ns["screen_tiles"](W, H)
        self.assertEqual(len(tiles), 6)
        for x, y, w, h in tiles:
            self.assertTrue(0 <= x and 0 <= y and x + w <= W and y + h <= H)
        # 每个像素都在某一块里；相邻块重叠，宽 150 的关卡名不会被切断
        for px in range(0, W - 150, 37):
            for py in range(0, H - 40, 53):
                self.assertTrue(any(x <= px and px + 150 <= x + w and y <= py and py + 40 <= y + h for x, y, w, h in tiles))


class ScanTilesTest(unittest.TestCase):
    def make_task(self, full, hidden):
        """full：整屏 OCR 读得到的关卡；hidden：只有切块才读得到的关卡。"""
        task = Mock()
        task.width, task.height = W, H
        task.processors = [None]
        task.read_tiles = False

        def ocr(*a, box=None, **k):
            if box is None:
                return list(full)
            return [b for b in hidden if box.x <= b.x and b.x + b.width <= box.x + box.width and box.y <= b.y and b.y + b.height <= box.y + box.height]

        task.ocr.side_effect = ocr
        task.scan_tiles.side_effect = lambda maps: ns["scan_tiles"](task, maps)
        return task

    def card(self, name, x, y=684):
        return SimpleNamespace(name=name, x=x, y=y, width=150, height=40)

    def test_screen_full_of_locked_cards_still_counts_as_map(self):
        """瑞骋迎春至：视野里全是未解锁的暗红卡，整屏一张都读不到，切块后读到，不能当成不在地图上。"""
        hidden = [self.card("LA-1-4", 250), self.card("LA-1-5", 870), self.card("LZ-1-3", 1690, 920)]
        task = self.make_task([], hidden)
        ordered = ns["scan_maps"](task)
        self.assertEqual([m.name for m, _ in ordered], ["LA-1-4", "LA-1-5", "LZ-1-3"])

    def test_tiles_not_read_when_cards_found_and_not_asked(self):
        task = self.make_task([self.card("DA-1-7", 1179)], [self.card("DS-1-1", 571)])
        self.assertEqual([m.name for m, _ in ns["scan_maps"](task)], ["DA-1-7"])

    def test_deep_scan_adds_only_new_positions(self):
        """驻足之地：DS-1-1 整屏读不到；切块时已读到的 DA-1-7 再读一次也不重复加。"""
        task = self.make_task([self.card("DA-1-7", 1179)], [self.card("DS-1-1", 571), self.card("DA-1-7", 1181)])
        task.read_tiles = True
        ordered = ns["scan_maps"](task)
        self.assertEqual([m.name for m, _ in ordered], ["DS-1-1", "DA-1-7"])


if __name__ == "__main__":
    unittest.main()
