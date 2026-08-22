import builtins
import dis
import importlib
import re
import types
import unittest

import pywintypes

from unittest import mock

from ok import Box, find_boxes_by_name
from ok.gui.common.config import Language
from ok.test.TaskTestCase import TaskTestCase
from src.config import config

# src/global/ cannot be imported statically because `global` is a Python keyword, so the class is
# resolved the same way the framework resolves it - by name, through importlib.
GlobalDailyTask = importlib.import_module('src.global.GlobalDailyTask').GlobalDailyTask
BaseGlobalTask = importlib.import_module('src.global.BaseGlobalTask').BaseGlobalTask


class TestGlobalMain(TaskTestCase):
    task_class = GlobalDailyTask
    lang = Language.ENGLISH
    config = config

    def test_is_main_on_english_home_screen(self):
        """The Global home screen should be recognised from its English labels plus the two home-only icons."""
        self.set_image('tests/images/english_main.png')
        self.assertTrue(self.task.is_main())

        self.set_image('tests/images/english_main2.png')
        self.assertTrue(self.task.is_main())

    def test_ocr_text_is_not_translated_to_chinese(self):
        """Global tasks must see English.

        `Recruitment` has an entry in `i18n/en_US/LC_MESSAGES/ocr.po` mapping it onto the Chinese literal the CN tasks expect. A Global task overrides
        `fix_texts`, so it should read the English straight off the screen instead.
        """
        self.set_image('tests/images/english_main.png')
        boxes = self.task.ocr(box='right')
        names = [b.name for b in boxes]
        self.assertTrue(any(re.search('Recruitment', n, re.I) for n in names), f'expected English text, got {names}')
        self.assertFalse(any('招募' in n for n in names), f'text was translated into Chinese: {names}')


class TestMenuLabelFilter(unittest.TestCase):
    """Guards the home-screen check against text that merely mentions the menu entries.

    Every string here came out of a real run's OCR, not from imagination.
    """

    def test_real_menu_entries_are_kept(self):
        base = importlib.import_module('src.global.BaseGlobalTask')
        for name in ('Campaign', 'Refitting', 'Room', 'Refitting Room', 'Crew Deck', 'Recruitment', 'Shop', 'Public Area'):
            self.assertTrue(base.is_menu_label(name), f'{name!r} is a real home-screen entry and must count')

    def test_loading_screen_prose_is_rejected(self):
        """A loading screen describing the ship once satisfied the home check and stopped the bot early."""
        base = importlib.import_module('src.global.BaseGlobalTask')
        for name in ('gine Room, Refitting Room,', 'a Crew Deck, Lounge and other', 'Do you wish to leave the Crew Deck?'):
            self.assertFalse(base.is_menu_label(name), f'{name!r} is prose, not a menu entry')


class TestPurchaseSafety(unittest.TestCase):
    """Guards the one flow that could spend real money.

    Coordinates are measured off a real screenshot of the Daily Supply Box dialog at 1920x1080, with the shop page visible around it.
    """

    def dialog_band(self):
        daily = importlib.import_module('src.global.GlobalDailyTask')
        x, y, to_x, to_y = daily.DIALOG_BAND
        return x * 1920, y * 1080, to_x * 1920, to_y * 1080

    def test_band_covers_the_dialog_but_not_the_page_behind_it(self):
        """Reading the page behind the dialog once made it refuse a free box as costing $9.99."""
        x0, y0, x1, y1 = self.dialog_band()

        def inside(px, py):
            return x0 <= px <= x1 and y0 <= py <= y1

        for name, px, py in (('Free label', 1524, 297), ('dialog Purchase', 1213, 834), ('dialog Cancel', 745, 834)):
            self.assertTrue(inside(px, py), f'{name} belongs to the dialog and must be read')
        for name, px, py in (('background price', 817, 970), ('background Purchase', 875, 1020), ('currency total', 1810, 47)):
            self.assertFalse(inside(px, py), f'{name} is the page behind the dialog and must not be read')

    def test_cancel_and_purchase_never_match_each_other(self):
        """Cancelling an accidentally-opened paid pack must not be able to buy it.

        The two buttons sit side by side in the same dialog, so a pattern that matched both would turn the safety into the accident.
        """
        base = importlib.import_module('src.global.BaseGlobalTask')
        daily = importlib.import_module('src.global.GlobalDailyTask')
        self.assertIsNone(base.CANCEL.search('Purchase'), 'CANCEL matches the Purchase button')
        self.assertIsNone(daily.PURCHASE.search('Cancel'), 'PURCHASE matches the Cancel button')
        self.assertIsNotNone(base.CANCEL.search('Cancel'))
        self.assertIsNotNone(daily.PURCHASE.search('Purchase'))

    def test_price_pattern_matches_money_and_not_dialog_prose(self):
        daily = importlib.import_module('src.global.GlobalDailyTask')
        for money in ('$ 9.99', '$0.99', '0.99'):
            self.assertTrue(daily.PRICE.search(money), f'{money!r} must block a purchase')
        for prose in ('Current progress: 12/21', 'Daily Limit 1/1', '3 Hours', 'Free', 'Daily Supply Box'):
            self.assertFalse(daily.PRICE.search(prose), f'{prose!r} appears in the free dialog and must not block it')


class _CardScreen:
    """A stand-in for a task, showing `click_card_button` a fixed screen and recording what it clicks.

    The real `TaskTestCase` harness is a process-wide singleton, so a second one in this module tears down the first. Nothing here needs a live executor -
    the method under test only reads OCR boxes and clicks one - so it borrows the real method and the real box matcher and skips the harness entirely.
    """

    click_card_button = BaseGlobalTask.click_card_button

    def __init__(self, boxes):
        self.boxes = boxes
        self.clicked = []

    def ocr(self, *args, **kwargs):
        return self.boxes

    def find_boxes(self, boxes, match=None, boundary=None):
        return find_boxes_by_name(boxes, match) if match else boxes

    def click(self, box, **kwargs):
        self.clicked.append(box)


class TestCardButtonSelection(unittest.TestCase):
    """Guards the rule that picks one card's button out of a list where every card carries the same one.

    Coordinates are read off a real Boundary Push screenshot at 1920x1080. Breakthrough and Phase Clash are stacked and both show a `Proceed`, so clicking
    whichever OCR returned first is a coin flip between the mode we want and one we do not.
    """

    def cards(self):
        return [Box(415, 160, 250, 50, name='Breakthrough'),
                Box(1600, 360, 250, 50, name='Proceed'),
                Box(415, 510, 250, 50, name='Phase Clash'),
                Box(1600, 710, 250, 50, name='Proceed')]

    def test_picks_the_button_under_the_named_card(self):
        daily = importlib.import_module('src.global.GlobalDailyTask')
        screen = _CardScreen(self.cards())
        screen.click_card_button(daily.BREAKTHROUGH, daily.PROCEED)
        self.assertEqual([360], [box.y for box in screen.clicked], 'clicked a Proceed belonging to another card')

    def test_picks_the_second_card_when_asked_for_it(self):
        """The rule has to be positional, not merely "the first Proceed on screen"."""
        daily = importlib.import_module('src.global.GlobalDailyTask')
        screen = _CardScreen(self.cards())
        screen.click_card_button(re.compile('Phase Clash', re.I), daily.PROCEED)
        self.assertEqual([710], [box.y for box in screen.clicked])

    def test_a_missing_card_clicks_nothing(self):
        """Clicking blind on a screen we did not expect is how a bot ends up in the wrong mode."""
        daily = importlib.import_module('src.global.GlobalDailyTask')
        screen = _CardScreen([Box(1600, 360, 250, 50, name='Proceed')])
        self.assertIsNone(screen.click_card_button(daily.BREAKTHROUGH, daily.PROCEED))
        self.assertEqual([], screen.clicked)


class TestEventTickets(unittest.TestCase):
    """Without tickets an event stage cannot be run, so the whole trip through the map and the auto dialog is wasted.

    The count has no label and shares its corner with an icon, so it is read by position out of whatever OCR returns there.
    """

    def parse(self, names):
        return importlib.import_module('src.global.GlobalDailyTask').parse_tickets(names)

    def test_an_empty_count_stops_the_flow(self):
        self.assertEqual(0, self.parse(['0']))

    def test_a_count_is_read(self):
        self.assertEqual(12, self.parse(['12']))

    def test_a_grouped_count_is_read(self):
        """A well-stocked account shows thousands, and OCR keeps the separator."""
        self.assertEqual(1234, self.parse(['1,234']))

    def test_the_icon_beside_it_is_skipped(self):
        """The band holds the ticket icon too, which OCR returns as junk rather than nothing."""
        self.assertEqual(3, self.parse(['\u25a0', '3']))

    def test_the_events_own_text_is_not_mistaken_for_a_count(self):
        self.assertIsNone(self.parse(['SEXTANS', 'Moonshroud Requiem']))

    def test_nothing_readable_is_unknown_rather_than_empty(self):
        """Returning 0 here would skip the event every run, and silently."""
        self.assertIsNone(self.parse([]))


class TestRewardProgress(unittest.TestCase):
    """The Breakthrough card says up front whether anything is left to collect.

    Every box below is what OCR actually returned for this screen, including the row of three counters arriving as one merged box with a stray character in
    it, and the sidebar sitting level with the card's reward row.
    """

    def base(self):
        return importlib.import_module('src.global.BaseGlobalTask')

    def screen_boxes(self):
        return [
            # The sidebar, level with the card and further left than anything on it.
            Box(70, 145, 194, 26, name='Expansion Drills'),
            Box(95, 180, 120, 24, name='40/4018/40'),
            Box(70, 250, 122, 26, name='Boss Fight'),
            Box(70, 285, 120, 22, name='Attempts: 3/3'),
            Box(70, 412, 210, 22, name='Frenzy Level: 54/120'),
            Box(70, 487, 200, 22, name='Purification Credits: 4600/3800'),
            # The Breakthrough card.
            Box(413, 262, 293, 18, name='Reward Progress-Deep Layer'),
            Box(413, 292, 407, 24, name='24/24 112/112 m168/168'),
            Box(413, 344, 84, 18, name='Bounties'),
            Box(413, 379, 40, 24, name='0/4'),
            # The Phase Clash card below it.
            Box(413, 612, 148, 18, name='Reward Details'),
            Box(437, 645, 40, 24, name='0/1'),
            Box(413, 694, 200, 18, name='Purification Credits'),
            Box(413, 728, 130, 30, name='4600/3800'),
        ]

    def read(self, boxes):
        base = self.base()
        daily = importlib.import_module('src.global.GlobalDailyTask')
        task = types.SimpleNamespace(height=1080, width=1920, ocr=lambda **kwargs: boxes,
                                     find_boxes=lambda b, match=None, boundary=None: [x for x in b if match.search(x.name)])
        return base.BaseGlobalTask.read_counter_under(task, daily.REWARD_PROGRESS)

    def test_it_reads_the_first_counter_out_of_the_merged_row(self):
        """OCR returns "24/24 112/112 m168/168" as one box, which is not a counter on its own."""
        self.assertEqual((24, 24), self.read(self.screen_boxes()))

    def test_the_sidebar_is_not_read_instead(self):
        """`Attempts: 3/3` is level with the reward row and further left, so leftmost alone would pick it."""
        self.assertNotEqual((3, 3), self.read(self.screen_boxes()))

    def test_the_bounties_counter_below_is_not_picked_up(self):
        """`Bounties 0/4` is on the same card and would read as "nothing collected" forever."""
        boxes = [b for b in self.screen_boxes() if '24/24' not in b.name]
        self.assertIsNone(self.read(boxes), 'reached past the reward row into the next heading')

    def test_the_other_cards_numbers_are_not_picked_up(self):
        """Phase Clash carries `4600/3800`, which is complete and would skip the flow wrongly."""
        self.assertNotEqual((4600, 3800), self.read(self.screen_boxes()))

    def test_a_missing_heading_reads_nothing(self):
        """Unknown means go and look, not assume it is done."""
        boxes = [b for b in self.screen_boxes() if 'Reward Progress' not in b.name]
        self.assertIsNone(self.read(boxes))

    def test_an_incomplete_card_is_not_skipped(self):
        boxes = [b if '24/24' not in b.name else Box(413, 292, 407, 24, name='12/24 40/112 m80/168')
                 for b in self.screen_boxes()]
        done, total = self.read(boxes)
        self.assertLess(done, total, 'a card with rewards left must not report itself complete')


class TestCounterParsing(unittest.TestCase):
    """The "n of m" shape the game uses for daily uses, reward progress and clear counts alike."""

    def parse(self, name):
        return importlib.import_module('src.global.BaseGlobalTask').first_counter(name)

    def test_a_complete_counter(self):
        self.assertEqual((24, 24), self.parse('24/24'))

    def test_the_first_of_several_merged_together(self):
        self.assertEqual((24, 24), self.parse('24/24 112/112 m168/168'))

    def test_ocr_spacing(self):
        self.assertEqual((112, 112), self.parse('112 / 112'))

    def test_text_with_no_counter_in_it(self):
        for name in ('Reward Progress-Deep Layer', 'Bounties', 'Proceed'):
            self.assertIsNone(self.parse(name), f'{name!r} holds no counter')


class TestGlobalFlowWiring(unittest.TestCase):
    """Static checks on the flow tables. No game, no OCR - these guard the wiring only."""

    def test_every_flow_names_a_real_method(self):
        """A typo in a FLOWS method name would only surface when that flow ran, so check it here."""
        for module_name, class_name in (('GlobalDailyTask', 'GlobalDailyTask'), ('GlobalWeeklyTask', 'GlobalWeeklyTask')):
            module = importlib.import_module(f'src.global.{module_name}')
            task_class = getattr(module, class_name)
            for key, method, description in module.FLOWS:
                self.assertTrue(hasattr(task_class, method), f'{class_name}.{method} is missing, referenced by {key!r}')
                self.assertTrue(description.strip(), f'{key!r} has no settings description')

    def test_single_flow_tasks_cover_every_flow(self):
        """Every composed flow should be individually runnable, so a new flow is not left unverifiable."""
        verify = importlib.import_module('src.global.VerifyTasks')
        daily = importlib.import_module('src.global.GlobalDailyTask')
        weekly = importlib.import_module('src.global.GlobalWeeklyTask')

        wrapped = {task_class.flow for task_class in vars(verify).values()
                   if isinstance(task_class, type) and getattr(task_class, 'flow', None)}
        for _, method, _ in daily.FLOWS + weekly.FLOWS:
            self.assertIn(method, wrapped, f'{method} has no single-flow task in VerifyTasks')

    def test_single_flow_tasks_are_registered(self):
        """A task that is not in the task list never appears as a button."""
        import src.region as region

        registered = {class_name for module_path, class_name in region.GLOBAL_TASKS if 'VerifyTasks' in module_path}
        verify = importlib.import_module('src.global.VerifyTasks')
        expected = {name for name, value in vars(verify).items()
                    if isinstance(value, type) and getattr(value, 'flow', None) and not name.startswith('_')}
        self.assertEqual(expected, registered)


if __name__ == '__main__':
    unittest.main()
