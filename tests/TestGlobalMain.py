import builtins
import dis
import importlib
import re
import types
import unittest

import pywintypes

from unittest import mock

from ok import Box, find_boxes_by_name
from ok.task.task import BaseTask
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


class TestWalkTimes(unittest.TestCase):
    """The Crew Deck is walked to on a timer, so the timings are the one part worth checking without a game."""

    def walk_times(self, option, key_count):
        return importlib.import_module('src.global.GlobalDailyTask').walk_times(option, key_count)

    def test_one_duration_per_movement_key(self):
        self.assertEqual([0.636, 1.25, 0.495], self.walk_times('0.636-1.25-0.495', 3))

    def test_a_short_setting_pads_with_taps(self):
        """A setting naming fewer durations than the walk has keys shortens the walk rather than raising."""
        self.assertEqual([1.0, 0.0], self.walk_times('1.0', 2))

    def test_a_non_numeric_setting_is_rejected(self):
        """Callers catch this to skip the station rather than crash the whole run."""
        with self.assertRaises(ValueError):
            self.walk_times('fast', 2)


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


class TestActiveDishes(unittest.TestCase):
    """The dish buff does not stack, so cooking while one is in effect spends ingredients for nothing.

    The line is read off the bottom of the dish screen, which is also covered in ingredient counters that must not be mistaken for it.
    """

    def parse(self, text):
        return importlib.import_module('src.global.GlobalDailyTask').parse_active_dishes(text)

    def test_a_dish_in_effect_is_counted(self):
        self.assertEqual(1, self.parse('Number of Experimental Dishes that can be effective at once 1/3'))

    def test_no_dish_in_effect_reads_zero(self):
        self.assertEqual(0, self.parse('Number of Experimental Dishes that can be effective at once 0/3'))

    def test_ocr_spacing_still_reads(self):
        self.assertEqual(2, self.parse('effective at once 2 / 3'))

    def test_ingredient_counters_are_not_mistaken_for_it(self):
        """The tiles read "1/20", "0/17" and so on. Matching one of those would skip cooking every run."""
        self.assertIsNone(self.parse('Rarity 1/20 1/17 0/12 0/14 Next'))

    def test_a_missing_line_is_unknown_rather_than_active(self):
        """Returning a truthy value here would skip the dish forever. None means go ahead and find out."""
        self.assertIsNone(self.parse('Select ingredients Cannot Make Dishes'))


class TestActivityButtons(unittest.TestCase):
    """The Crew Deck activities end on screens where the wrong button is costly.

    The dish's closing screen puts `To Battle!` beside `Confirm`, and the drink's confirmation puts `Cancel` beside it. Every pattern the flow clicks has to
    miss the neighbour.
    """

    def daily(self):
        return importlib.import_module('src.global.GlobalDailyTask')

    def clickable_patterns(self):
        """Every pattern `crew_deck` clicks by name, so a new one cannot quietly opt out of this check."""
        daily = self.daily()
        base = importlib.import_module('src.global.BaseGlobalTask')
        return {'MAKE': daily.MAKE, 'NEXT': daily.NEXT, 'INVITE': daily.INVITE, 'CONFIRM': base.CONFIRM, 'SKIP': base.SKIP}

    def test_nothing_the_flow_clicks_matches_to_battle(self):
        """Starting a battle nobody asked for is the worst thing this flow could do."""
        label = 'To Battle!'
        self.assertIsNotNone(self.daily().TO_BATTLE.search(label), 'TO_BATTLE should describe the button it is named for')
        for name, pattern in self.clickable_patterns().items():
            self.assertIsNone(pattern.search(label), f'{name} matches the To Battle button on the dish summary')

    def test_nothing_the_flow_clicks_matches_cancel(self):
        """Cancel sits beside Confirm on the Caution dialog, and would silently make no drink at all."""
        for name, pattern in self.clickable_patterns().items():
            self.assertIsNone(pattern.search('Cancel'), f'{name} matches the Cancel button beside Confirm')

    def test_make_does_not_match_the_cooking_screens_prose(self):
        """The cooking screen reads "Cannot Make Dishes", which an unanchored Make would click."""
        self.assertIsNone(self.daily().MAKE.search('Cannot Make Dishes'))

    def test_the_buttons_still_match_themselves(self):
        daily = self.daily()
        base = importlib.import_module('src.global.BaseGlobalTask')
        for pattern, label in ((daily.MAKE, 'Make'), (daily.NEXT, 'Next'), (daily.INVITE, 'Confirm Invite'),
                               (daily.INVITE, 'Invite'), (base.CONFIRM, 'Confirm'), (base.SKIP, 'Skip')):
            self.assertIsNotNone(pattern.search(label), f'{label!r} is a real button and must still be clickable')


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


class TestGoHomePolling(unittest.TestCase):
    """The home button is not on every screen, and each look for it costs up to three OCR passes.

    Polling flat out spent the whole window re-reading a screen that could not change until something was pressed, which reads in the log as the bot hanging.
    """

    def go_home(self, is_main_results):
        base = importlib.import_module('src.global.BaseGlobalTask')
        looks = []

        def is_main(esc=True):
            looks.append(esc)
            return is_main_results.pop(0) if is_main_results else False

        clock = {'now': 0.0}
        task = types.SimpleNamespace(info_set=mock.Mock(), click_relative=mock.Mock(), log_info=mock.Mock(),
                                     ensure_main=mock.Mock(), is_main=is_main,
                                     sleep=mock.Mock(side_effect=lambda seconds: clock.__setitem__('now', clock['now'] + seconds)))
        with mock.patch.object(base.time, 'time', lambda: clock['now']):
            base.BaseGlobalTask.go_home(task)
        return task, looks

    def test_it_stops_as_soon_as_the_button_takes(self):
        task, looks = self.go_home([True])
        self.assertEqual(1, len(looks))
        task.ensure_main.assert_not_called()

    def test_it_waits_between_looks_rather_than_spinning(self):
        base = importlib.import_module('src.global.BaseGlobalTask')
        task, looks = self.go_home([])
        expected = base.HOME_BUTTON_TIME_OUT / base.HOME_BUTTON_CHECK_INTERVAL + 1
        self.assertLessEqual(len(looks), expected, 'polling faster than the interval wastes OCR on an unchanged screen')
        self.assertGreater(len(looks), 1, 'it should look more than once before giving up')

    def test_it_falls_back_to_backing_out(self):
        """Screens without a home button are normal - the event map is one - so this is not an error."""
        task, _ = self.go_home([])
        task.ensure_main.assert_called_once()

    def test_the_poll_never_presses_escape(self):
        """Escape here would back out of the screen the home button was meant to leave from, racing it."""
        _, looks = self.go_home([])
        self.assertTrue(all(esc is False for esc in looks), 'the home-button poll must be a pure query')


class TestRegionHiding(unittest.TestCase):
    """Hiding a task means wrapping its `post_init`, and each class must be wrapped in its own right.

    Every task in `VerifyTasks` subclasses a composed task. A marker read through the bases reports the subclasses as already wrapped, so they keep their
    inherited `post_init` and stay visible in the region they do not belong to.
    """

    def region(self):
        return importlib.import_module('src.region')

    def test_a_class_that_was_wrapped_reports_itself_hidden(self):
        region = self.region()

        class Parent:
            pass

        setattr(Parent, region.HIDDEN_MARKER, True)
        self.assertTrue(region.already_hidden(Parent))

    def test_a_subclass_of_a_wrapped_class_is_not_reported_hidden(self):
        """Without this, every single-flow task is skipped and shows up in the wrong region."""
        region = self.region()

        class Parent:
            pass

        setattr(Parent, region.HIDDEN_MARKER, True)

        class Child(Parent):
            pass

        self.assertFalse(region.already_hidden(Child))

    def test_an_untouched_class_is_not_reported_hidden(self):
        class Fresh:
            pass

        self.assertFalse(self.region().already_hidden(Fresh))


class TestSwipeRecovery(unittest.TestCase):
    """A refused cursor move during a swipe leaves the mouse button held.

    The framework presses the button, moves, then releases, each through the call that can be refused. A refusal on the way in unwinds past the release, and
    a held button turns every later click into a drag.
    """

    def base(self):
        return importlib.import_module('src.global.BaseGlobalTask')

    def task(self, interaction):
        return types.SimpleNamespace(log_info=mock.Mock(), executor=types.SimpleNamespace(interaction=interaction))

    def test_the_button_is_released(self):
        release = mock.Mock()
        self.base().BaseGlobalTask.release_mouse(self.task(types.SimpleNamespace(mouse_up=release)))
        release.assert_called_once()

    def test_an_interaction_without_a_release_is_tolerated(self):
        """`PostMessage` is selectable on the Start tab and does not offer the same surface."""
        self.base().BaseGlobalTask.release_mouse(self.task(types.SimpleNamespace()))

    def test_a_refused_release_is_logged_rather_than_raised(self):
        """The same contention that broke the swipe can refuse the release, and there is nothing left to abort."""
        release = mock.Mock(side_effect=pywintypes.error(0, 'SetCursorPos', ''))
        task = self.task(types.SimpleNamespace(mouse_up=release))
        self.base().BaseGlobalTask.release_mouse(task)
        task.log_info.assert_called_once()


class TestCursorContention(unittest.TestCase):
    """The Genshin interaction warps the real cursor onto the game and back around every action.

    Windows refuses that while something else holds the input queue, which is what happens whenever the mouse is in use during a run. It killed a Crew Deck
    walk and an Event Supply swipe outright, on an error that said nothing about the game.
    """

    def base(self):
        return importlib.import_module('src.global.BaseGlobalTask')

    def task(self, cursor_position=(10, 20)):
        """A stand-in with just the parts `despite_cursor_error` and `recover_cursor` touch."""
        interaction = types.SimpleNamespace(cursor_position=cursor_position, unblock_input=mock.Mock())
        return types.SimpleNamespace(
            log_info=mock.Mock(),
            sleep=mock.Mock(),
            executor=types.SimpleNamespace(interaction=interaction),
            recover_cursor=mock.Mock(),
        )

    def cursor_error(self):
        return pywintypes.error(0, 'SetCursorPos', 'No error message is available')

    def raiser(self, error):
        def action():
            raise error
        return action

    def test_a_refused_cursor_move_does_not_stop_the_run(self):
        task = self.task()
        result = self.base().BaseGlobalTask.despite_cursor_error(task, self.raiser(self.cursor_error()), 'send_key')
        self.assertIsNone(result)
        task.recover_cursor.assert_called_once()

    def test_the_action_is_not_repeated(self):
        """The cursor restore runs after the action, so repeating it would press twice or swipe twice."""
        task, calls = self.task(), []

        def action():
            calls.append(1)
            raise self.cursor_error()

        self.base().BaseGlobalTask.despite_cursor_error(task, action, 'send_key')
        self.assertEqual(1, len(calls), 'the action was repeated, which would double a key press')

    def test_a_successful_action_passes_its_result_through(self):
        task = self.task()
        self.assertEqual('clicked', self.base().BaseGlobalTask.despite_cursor_error(task, lambda: 'clicked', 'click'))
        task.recover_cursor.assert_not_called()

    def test_other_errors_still_surface(self):
        """Swallowing everything here would hide real bugs behind a message about the mouse."""
        with self.assertRaises(ValueError):
            self.base().BaseGlobalTask.despite_cursor_error(self.task(), self.raiser(ValueError('a real bug')), 'click')


    def test_the_wrapped_arguments_reach_the_action_untouched(self):
        """`click` has its own `name`, which bound to this wrapper's parameter and raised instead of clicking.

        Every `click_relative` call passes one, so this broke far more than the flow it was noticed in.
        """
        seen = {}

        def action(*args, **kwargs):
            seen['args'], seen['kwargs'] = args, kwargs
            return 'clicked'

        result = self.base().BaseGlobalTask.despite_cursor_error(
            self.task(), action, 'click', 0.1, 0.2, name='Supply', after_sleep=3)
        self.assertEqual('clicked', result)
        self.assertEqual((0.1, 0.2), seen['args'])
        self.assertEqual({'name': 'Supply', 'after_sleep': 3}, seen['kwargs'])

    def test_an_argument_named_like_the_wrapper_itself_is_still_passed_through(self):
        """Positional-only parameters are what make this safe, so a caller with an `action` or `label` cannot collide either."""
        seen = {}
        self.base().BaseGlobalTask.despite_cursor_error(
            self.task(), lambda **kwargs: seen.update(kwargs), 'swipe', action='x', label='y')
        self.assertEqual({'action': 'x', 'label': 'y'}, seen)


class TestCursorRecovery(unittest.TestCase):
    """What a refused cursor move leaves behind, and how it is put right.

    A click blocks input for its duration and unblocks it only after restoring the cursor, so a restore that throws leaves the keyboard and mouse frozen for
    as long as the app lives. That is the part that must not be missed.
    """

    def base(self):
        return importlib.import_module('src.global.BaseGlobalTask')

    def task(self, cursor_position=(10, 20)):
        interaction = types.SimpleNamespace(cursor_position=cursor_position, unblock_input=mock.Mock())
        return types.SimpleNamespace(log_info=mock.Mock(), sleep=mock.Mock(),
                                     executor=types.SimpleNamespace(interaction=interaction))

    def recover(self, task, set_cursor):
        base = self.base()
        with mock.patch.object(base.win32api, 'SetCursorPos', set_cursor):
            base.BaseGlobalTask.recover_cursor(task, 'click')

    def test_input_is_unblocked_first(self):
        """Left blocked, the user's keyboard and mouse stay frozen until the app exits."""
        task = self.task()
        self.recover(task, mock.Mock())
        task.executor.interaction.unblock_input.assert_called_once()

    def test_input_is_unblocked_even_when_there_is_no_cursor_to_restore(self):
        task = self.task(cursor_position=None)
        self.recover(task, mock.Mock(side_effect=AssertionError('should not be called')))
        task.executor.interaction.unblock_input.assert_called_once()

    def test_the_cursor_move_is_retried_until_it_takes(self):
        """The reason it failed is that the mouse was in use, which passes on its own."""
        task = self.task()
        attempts = []

        def set_cursor(position):
            attempts.append(position)
            if len(attempts) < 3:
                raise pywintypes.error(0, 'SetCursorPos', '')

        self.recover(task, set_cursor)
        self.assertEqual([(10, 20)] * 3, attempts)
        self.assertEqual(2, task.sleep.call_count, 'it should wait between attempts rather than spin')

    def test_giving_up_is_logged_and_not_raised(self):
        """The action this belonged to already happened, so there is nothing left to abort."""
        task = self.task()
        base = self.base()
        clock = iter([0] + [base.CURSOR_RESTORE_SECONDS + 1] * 50)
        with mock.patch.object(base.time, 'time', lambda: next(clock)):
            self.recover(task, mock.Mock(side_effect=pywintypes.error(0, 'SetCursorPos', '')))
        task.log_info.assert_called_once()


class TestDailyCounter(unittest.TestCase):
    """Each Crew Deck activity runs once a day, and its prompt says whether it has been used.

    Getting this backwards would either skip an available activity every day, or walk to a spent one and click through screens that do nothing.
    """

    def parse(self, text):
        return importlib.import_module('src.global.GlobalDailyTask').parse_uses_left(text)

    def test_a_spent_station_has_nothing_left(self):
        self.assertEqual(0, self.parse('Tea Time 1/1'))

    def test_an_untouched_station_has_a_use_left(self):
        self.assertEqual(1, self.parse('Tea Time 0/1'))

    def test_a_counter_split_by_ocr_still_reads(self):
        """OCR spaces the slash out sometimes, and returns the label and counter as separate boxes that get joined."""
        self.assertEqual(2, self.parse('Delicious Cuisine 0 / 2'))

    def test_a_prompt_with_no_counter_is_unknown_rather_than_spent(self):
        """Returning 0 here would silently skip the activity every run. None means go ahead and find out."""
        self.assertIsNone(self.parse('Makiatto'))
        self.assertIsNone(self.parse('Tea Time'))


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
        """Run the real `read_counter_under` over the given boxes.

        The stand-in borrows the framework's own `find_boxes` rather than approximating it. An approximation here ignored the boundary argument entirely,
        which is the very thing that keeps the sidebar's counters out, so the test agreed with code that would have failed against the game.

        Args:
            boxes: The text to pretend was read off the screen.

        Returns:
            Whatever `read_counter_under` made of it.
        """
        daily = importlib.import_module('src.global.GlobalDailyTask')
        task = types.SimpleNamespace(height=1080, width=1920, ocr=lambda **kwargs: boxes)
        task.find_boxes = lambda *args, **kwargs: BaseTask.find_boxes(task, *args, **kwargs)
        return BaseGlobalTask.read_counter_under(task, daily.REWARD_PROGRESS)

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


class TestSingleFlowConfig(unittest.TestCase):
    """A single-flow task should offer the settings its own flow uses, and no others.

    Every one of them once carried the Crew Deck walk timings, because stripping a flow's toggle left the settings nested under it behind. They did nothing
    on a task that never walks anywhere.
    """

    def strip(self, flow):
        """Run `_strip_flow_toggles` over a stand-in task and return the settings it would be left with."""
        verify = importlib.import_module('src.global.VerifyTasks')
        daily = importlib.import_module('src.global.GlobalDailyTask')
        task = types.SimpleNamespace(
            flow=flow,
            default_config={key: True for key, _, _ in daily.FLOWS} | {key: default for key, default, _ in daily.WALK_OPTIONS},
            config_description={},
            default_config_group={'Crew Deck': [key for key, _, _ in daily.WALK_OPTIONS]},
        )
        verify._strip_flow_toggles(task, daily.FLOWS)
        return task.default_config

    def test_the_crew_deck_task_keeps_its_walk_timings(self):
        daily = importlib.import_module('src.global.GlobalDailyTask')
        remaining = self.strip('crew_deck')
        for key, _, _ in daily.WALK_OPTIONS:
            self.assertIn(key, remaining, f'the Crew Deck task needs {key!r} - it is how the walk is tuned')

    def test_other_flows_are_left_with_nothing_to_set(self):
        self.assertEqual({}, self.strip('shopping'))
        self.assertEqual({}, self.strip('start_loop'))


class TestNoUndefinedNames(unittest.TestCase):
    """Catches a name that is used but never defined or imported.

    `CREW_DECK` was used by the Crew Deck flow and left out of its import line. Nothing caught it, because no test executes a flow body - the flow navigates
    a live game - so it surfaced only as a NameError mid-run. Reading the bytecode needs no game and covers every flow at once.
    """

    MODULES = ('BaseGlobalTask', 'GlobalDailyTask', 'GlobalWeeklyTask', 'VerifyTasks')

    def functions_defined_in(self, module):
        """Yield every function the module itself defines, methods included, skipping ones it merely imported."""
        for value in vars(module).values():
            if isinstance(value, types.FunctionType) and value.__module__ == module.__name__:
                yield value
            elif isinstance(value, type) and value.__module__ == module.__name__:
                for attribute in vars(value).values():
                    if isinstance(attribute, types.FunctionType):
                        yield attribute

    def test_every_global_name_is_defined(self):
        for name in self.MODULES:
            module = importlib.import_module(f'src.global.{name}')
            for function in self.functions_defined_in(module):
                for instruction in dis.get_instructions(function):
                    if instruction.opname != 'LOAD_GLOBAL':
                        continue
                    used = instruction.argval
                    self.assertTrue(hasattr(module, used) or hasattr(builtins, used),
                                    f'{name}.{function.__qualname__} uses {used!r}, which that module neither defines nor imports')


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
