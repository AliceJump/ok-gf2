import ast
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


source = Path(__file__).resolve().parents[1] / 'src/tasks/DailyTask.py'
cls = next(n for n in ast.parse(source.read_text(encoding='utf-8')).body
           if isinstance(n, ast.ClassDef) and n.name == 'DailyTask')
names = {'activity', '_activity_chapter_pattern',
         '_box_center_ratio', '_filter_boxes_near_candidates'}
namespace = {'re': re, 'map_re': re.compile('关卡')}
method_nodes = list(cls.body)
for mixin in ('daily_activity_mixin.py', 'daily_common_mixin.py'):
    tree = ast.parse((source.parent / 'daily' / mixin).read_text(encoding='utf-8'))
    method_nodes.extend(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
exec(compile(ast.Module(body=[n for n in method_nodes if isinstance(n, ast.FunctionDef)
                             and n.name in names], type_ignores=[]), str(source), 'exec'), namespace)


def box(name, x):
    return SimpleNamespace(name=name, x=x, y=880, width=100, height=20)


class ActivityChaptersTest(unittest.TestCase):
    def run_activity(self, name='静默突触', lower=True, locked=False, supplies=True,
                     classic=False, chapter='转篇'):
        task = Mock()
        for method in names:
            setattr(task, method, namespace[method].__get__(task))
        task.width, task.height = 2000, 1250
        task.config = {'当前物资关卡名称': name, '物资篇章名称': chapter}
        up = box('静默突触·上篇' if classic else '静默突触·初篇', 100)
        down = box('静默突触·下篇' if classic else '静默突触·转篇', 1400)
        candidates = [up, down]
        task.wait_ocr_until_count.side_effect = lambda **kw: [
            b for b in candidates if kw['match'][0].search(b.name)]
        def wait_ocr(**kw):
            if kw['match'] == ['开启中']:
                return ['event']
            if kw['match'] is namespace['map_re']:
                return ['last-stage']
            return ([box('物资100%', 100)] + ([box('物资100%', 1400)] if lower else [])) if supplies else []
        task.wait_ocr.side_effect = wait_ocr
        task.ocr.side_effect = lambda **kw: ([box('未开启', 1400)] if locked else []) if kw['box'] is None else []
        task.activity()
        clicked = [c.args[0] for c in task.click.call_args_list]
        return task, [b.name for b in clicked if isinstance(b, SimpleNamespace)]

    def test_exact_turn_chapter_clicks_once(self):
        task, clicked = self.run_activity()
        self.assertEqual(clicked, ['静默突触·转篇'])
        task.fast_combat.assert_called_once()

    def test_exact_initial_chapter(self):
        _, clicked = self.run_activity(chapter='初篇')
        self.assertEqual(clicked, ['静默突触·初篇'])

    def test_classic_lower_requires_actual_name(self):
        _, clicked = self.run_activity(classic=True, chapter='下篇')
        self.assertEqual(clicked, ['静默突触·下篇'])

    def test_no_alias_conversion(self):
        task, clicked = self.run_activity(chapter='下篇')
        self.assertEqual(clicked, [])
        task.fast_combat.assert_not_called()

    def test_unavailable_supply_never_falls_back(self):
        for kwargs in ({'lower': False}, {'locked': True}, {'supplies': False}):
            with self.subTest(kwargs=kwargs):
                task, clicked = self.run_activity(**kwargs)
                self.assertEqual(clicked, [])
                task.fast_combat.assert_not_called()

    def test_empty_chapter_stops_before_navigation(self):
        task, clicked = self.run_activity(chapter='')
        self.assertEqual(clicked, [])
        task.wait_click_ocr.assert_not_called()

    def test_mismatched_activity_chapter_counts_stop(self):
        task, _ = self.run_activity(name='静默突触-另一个活动')
        task.wait_click_ocr.assert_not_called()

    def test_generic_full_chapter_name_and_literal_matching(self):
        pattern = namespace['_activity_chapter_pattern'](None, '活动(一)', '特别物资篇')
        self.assertIsNotNone(pattern.search(' 活动(一) ： 特别物资篇 '))
        for title in ('活动一·特别物资篇', '活动(一)·特别物资篇后续', '其他活动(一)·特别物资篇'):
            self.assertIsNone(pattern.search(title))

    def test_configuration_groups_new_text_field(self):
        methods = [n for n in cls.body if isinstance(n, ast.FunctionDef)
                   and n.name in ('_init_default_config', '_init_default_config_group')]
        config_namespace = {}
        exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), 'exec'), config_namespace)
        task = SimpleNamespace(config_description={}, default_config={}, default_config_group={}, config_type={})
        for method in config_namespace.values():
            if callable(method):
                method(task)
        self.assertEqual(task.default_config['物资篇章名称'], '')
        self.assertEqual(task.config_type['活动自律']['sub_configs'][True],
                         ['当前物资关卡名称', '物资篇章名称'])


if __name__ == '__main__':
    unittest.main()
