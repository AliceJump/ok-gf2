import re
import unittest
from unittest.mock import Mock
import ast
from pathlib import Path
source = Path(__file__).resolve().parents[1] / 'src/tasks/daily/daily_activity_mixin.py'
node = next(n for n in ast.parse(source.read_text(encoding='utf-8')).body if isinstance(n, ast.ClassDef))
methods = [n for n in node.body if isinstance(n, ast.FunctionDef) and n.name in ('water_flowers', '_ensure_activity_panel', 'free_time_layer')]
ns = {'re': re}
exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), 'exec'), ns)
water_flowers = ns['water_flowers']
ensure_panel = ns['_ensure_activity_panel']
class ActivityPanelTest(unittest.TestCase):
    def make_task(self, open_after=None, initially_open=False, click_opens=False):
        task = Mock()
        task.box_of_screen.side_effect = lambda *bounds: bounds
        state = {'open': initially_open, 'keys': 0}
        def ocr(**kwargs):
            return state['open']
        def key(*args, **kwargs):
            state['keys'] += 1
            if state['keys'] == open_after:
                state['open'] = True
        def click(**kwargs):
            state['open'] = click_opens
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
        task.send_key.assert_called_once_with('f2', down_time=0.15, after_sleep=1)
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
        self.assertIn('F2 面板未打开', task.log_error.call_args.args[0])

    def test_missing_entry_is_failure(self):
        task = self.make_task()
        task.wait_click_ocr.side_effect = None
        task.wait_click_ocr.return_value = False
        self.assertFalse(ensure_panel(task))

    def test_water_stops_before_searching_when_panel_fails(self):
        task = Mock()
        task._ensure_activity_panel.return_value = False
        self.assertFalse(water_flowers(task))
        task.wait_ocr.assert_not_called()
        task.wait_click_ocr.assert_not_called()

class WaterFlowersTest(unittest.TestCase):
    def make_task(self, overview=False, already_done=False, succeeds=True, missing_tab=False, initial_page="tabs", overview_text="栽培天数"):
        task = Mock()
        task.box.right = 'right'
        task.box.bottom_right = 'bottom_right'
        task.box_of_screen.side_effect = lambda *bounds: bounds
        state = {'page': initial_page, 'done': already_done}
        clicks = []

        def matches(pattern, text):
            return bool(pattern.search(text)) if isinstance(pattern, re.Pattern) else pattern == text

        def click_ocr(*, match, **kwargs):
            labels = {'tabs': '' if missing_tab else '上栽培',
                      'overview': '前往', 'plant': '浇灌'}
            label = labels[state['page']]
            if not matches(match, label):
                return False
            clicks.append(label)
            if state['page'] == 'tabs':
                state['page'] = 'overview' if overview else 'plant'
            elif state['page'] == 'overview':
                state['page'] = 'plant'
            else:
                state['done'] = succeeds
            return True

        def ocr(*, match, box, **kwargs):
            if box == (0.13, 0.16, 0.87, 0.82):
                label = {'tabs': '逸趣事件', 'overview': overview_text, 'plant': '浇灌'}[state['page']]
                return matches(match, label)
            if state['page'] == 'overview':
                return matches(match, overview_text)
            if state['page'] != 'plant':
                return False
            text = '浇灌' if box == 'right' else ('1/1' if state['done'] else '0/1')
            return matches(match, text)

        task._ensure_activity_panel.side_effect = lambda: ensure_panel(task)
        task.wait_click_ocr.side_effect = click_ocr
        task.wait_ocr.side_effect = ocr
        return task, clicks

    def test_icon_prefix_from_failure_log_is_accepted(self):
        task, clicks = self.make_task()
        self.assertTrue(water_flowers(task))
        self.assertEqual(['上栽培', '浇灌'], clicks)
        task.back.assert_called_once()

    def test_overview_requires_go_button(self):
        task, clicks = self.make_task(overview=True)
        self.assertTrue(water_flowers(task))
        self.assertEqual(['上栽培', '前往', '浇灌'], clicks)

    def test_f2_direct_overview_skips_unreadable_tab(self):
        for label in ('栽培天数', '生 长 阶 段'):
            with self.subTest(label=label):
                task, clicks = self.make_task(initial_page='overview', missing_tab=True,
                                              overview_text=label)
                self.assertTrue(water_flowers(task))
                self.assertEqual(['前往', '浇灌'], clicks)

    def test_f2_direct_watering_page_skips_tab(self):
        task, clicks = self.make_task(initial_page='plant', missing_tab=True)
        self.assertTrue(water_flowers(task))
        self.assertEqual(['浇灌'], clicks)

    def test_unrelated_go_button_is_not_cultivation(self):
        task, clicks = self.make_task(initial_page='overview', missing_tab=True,
                                      overview_text='前往')
        self.assertFalse(water_flowers(task))
        self.assertEqual([], clicks)

    def test_already_watered_does_not_click_again(self):
        task, clicks = self.make_task(already_done=True)
        self.assertTrue(water_flowers(task))
        self.assertEqual(['上栽培'], clicks)
        task.back.assert_called_once()

    def test_click_without_updated_count_is_failure(self):
        task, _ = self.make_task(succeeds=False)
        self.assertFalse(water_flowers(task))
        task.back.assert_called_once()

    def test_missing_tab_does_not_water(self):
        task, clicks = self.make_task(missing_tab=True)
        self.assertFalse(water_flowers(task))
        self.assertEqual([], clicks)


class WaterIntegrationTest(unittest.TestCase):
    def test_water_runs_after_food_and_propagates_failure(self):
        task = Mock()
        task.config = {'活动层浇花': True}
        events = []
        task.is_free_layer.return_value = True
        task.do_food_flow.side_effect = lambda **kw: events.append('food') or True
        task.water_flowers.side_effect = lambda: events.append('water') or False
        self.assertIs(False, ns['free_time_layer'](task))
        self.assertEqual(['food', 'food', 'water'], events)

    def test_disabled_water_preserves_food_only_flow(self):
        task = Mock()
        task.config = {'活动层浇花': False}
        task.is_free_layer.return_value = True
        self.assertIs(True, ns['free_time_layer'](task))
        task.water_flowers.assert_not_called()
        self.assertEqual(2, task.do_food_flow.call_count)
