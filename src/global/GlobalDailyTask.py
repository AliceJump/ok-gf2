import re
from typing import NamedTuple

from ok import Box

from src.tasks.BaseGfTask import map_re, parse_time_option

from .BaseGlobalTask import CANCEL, CLAIM_ALL, CLICK_ANYWHERE, CONFIRM, COUNTER, CREW_DECK, PROCEED, SHOP, SKIP, BaseGlobalTask

# Event. The banner sits at a fixed spot in the top-left of the home screen. When a second event is
# running its banner appears directly below this one - not supported, since two at once is rare.
EVENT_BANNER = (0.104, 0.157)
EVENT_PAGE = re.compile(r'Challenge|Supply|Story', re.I)
SUPPLY = re.compile(r'\bSupply\b', re.I)
# Anchored so it cannot match the "Auto Mode Preparation" dialog title that follows it.
AUTO = re.compile(r'^Auto$', re.I)
AUTO_DIALOG = re.compile(r'Number of Auto Battles', re.I)
ITEMS_OBTAINED = re.compile(r'Items Obtained', re.I)

# Event tickets, in the top-right corner of the event page. Every event puts the count in the same spot
# and none of them labels it, so it is found by position. The band stops above the event's own name,
# which sits just below it, and is generous to the left so a four-figure count still falls inside.
#
# This is a filter over a full-frame read, not a region to OCR. The count is a single glyph - measured
# at 8x25 - and the detector finds it in a whole frame but not in a crop around it, because a crop is
# resized before detection and one character does not survive that. `target_height` does not help: it
# scales relative to the frame, so asking for 260 shrank the crop to a quarter size and made it worse.
TICKETS_BAND = (0.86, 0.015, 1.0, 0.085)
TICKET_COUNT = re.compile(r'\d[\d,]*')

# How much to enlarge that corner before reading it. Six times turns an 8x25 glyph into 48x150, which is
# the size of ordinary on-screen text rather than something the detector has to be lucky to find.
TICKETS_ZOOM = 6
# What the end of a run of auto battles can look like. The reward summary is the expected outcome, but
# the click-anywhere overlay is what actually blocks progress, and it is not always preceded by a title
# the poll can see - so either one counts as done.
BATTLES_DONE = [ITEMS_OBTAINED, CLICK_ANYWHERE]

# Sets the battle count to the most the remaining Expenditure allows. Unlabelled, so clicked by position.
MAX_BATTLES = (0.653, 0.518)

# Stage nodes sit in a horizontal band across the middle of the Supply map. Scanning a band rather than
# the whole frame keeps the repeated scroll-and-look cheap.
STAGE_BAND = (0.0, 0.38, 1.0, 0.62)
STAGE_SWIPES = 5
EVENT_BATTLE_TIME_OUT = 900

# The flows this task performs, in the order it performs them: (config key, method, settings text).
# Single source for the toggles, the settings descriptions, and the run order. `VerifyTasks` also reads
# it, so a flow added here becomes individually runnable without any further wiring.
FLOWS = (
    # First, because the food and drink buffs only apply to battles fought after they are picked up, and
    # every flow that fights comes later - Start Loop waits out the whole in-game Loop, and Run Event
    # Supply auto-battles as well. Running this last spent the day's buffs on nothing.
    ('Crew Deck', 'crew_deck',
     'Visits the Crew Deck stations - Tea Time at the coffee machine, Delicious Cuisine at the kitchen. Walks there on a timer, so the walk settings below may need adjusting.'),
    ('Start Loop', 'start_loop',
     'Opens the Dispatch Room and starts the in-game Loop automation, then waits for it to finish.'),
    ('Claim Free Packs', 'shopping',
     'Claims the shop supply boxes that are currently free.'),
    ('Buy Wishlist Items', 'buy_wishlist',
     'Buys everything waiting in the shop Wishlist, one in-game shop at a time. Spends in-game currency, never real money, and only on what is already on the Wishlist.'),
    ('Run Event Supply', 'run_event_supply',
     'Auto-battles the last Supply stage of the current event, spending as much Expenditure as it can.'),
    ('Claim Boundary Push Rewards', 'claim_boundary_push',
     'Collects the Breakthrough rewards under Commissions.'),
)

# Flows that stay switched off until they are asked for. Buy Wishlist Items because it is the only flow
# that spends anything, and spending on the first run after an update is not something to decide on
# someone's behalf.
FLOWS_OFF_BY_DEFAULT = ('Buy Wishlist Items',)

# In-game Loop automation. The client runs the dailies itself once this is started, which is why the
# Global task set is so much smaller than the CN one.
#
# The entry point is the fourth of the small unlabelled icons along the bottom-left of the home screen,
# so it has to be clicked by position. Everything after that is real text. Opening it lands on the
# Dispatch Room page, which is what we check to confirm the click landed.
LOOP_ICON = (0.213, 0.896)
LOOP_SCREEN = re.compile(r'Dispatch Room|Start\s*Loop', re.I)
START_LOOP = re.compile(r'Start\s*Loop', re.I)
LOOP_ENDED = re.compile(r'Loop\s*ended', re.I)

# How long to wait for the in-game Loop to finish, and how often to look.
LOOP_TIME_OUT = 600
LOOP_POLL_INTERVAL = 5

# Shop. Each supply box carries its price where a button would be - the claimable ones read "Free".
# Matching on the price rather than on a box name covers the daily and the weekly box without hardcoding
# either, and a box on cooldown shows a timer instead, so it simply stops matching once claimed.
FREE = re.compile(r'^Free$', re.I)
PURCHASE = re.compile(r'Purchase', re.I)

# Where the shop opens is not fixed: with a free pack waiting the game drops straight into Quality
# Selection, otherwise it opens on Premium Selections. Rather than depend on that, the category and each
# tab holding a free box are opened by name. "Quality Selection" wraps onto two lines that OCR splits
# apart, so it is matched on its first word alone - the same reason `CRYSTAL_COLLECTION` is.
QUALITY_SELECTION = re.compile(r'Quality', re.I)
# The two tabs carrying a free box, in the order they are visited: Treasured holds the Weekly Joy Supply
# Box, Regular the Daily Supply Box. Matched on the one distinctive word, since OCR splits the three-word
# tab labels unpredictably and neither word appears in another tab or in the category list.
FREE_BOX_TABS = (re.compile(r'Treasured', re.I), re.compile(r'Regular', re.I))

# The card grid - everything right of the category sidebar and below the tab strip. Which card is the free
# one moves from tab to tab, so the whole grid is read rather than a measured corner. Reading only the
# bottom-right corner is what made this claim nothing at all on any page but Premium Selections.
CARD_GRID = (0.15, 0.18, 1.0, 1.0)

# Wishlist, reached from the bottom-left of the shop. It gathers what has been picked out for later across
# six in-game shops, each its own category in a left rail. Every label there wraps onto two lines that OCR
# splits apart, so each is matched on its distinctive first word.
WISHLIST = re.compile(r'Wishlist', re.I)
WISHLIST_CATEGORIES = (
    re.compile(r'Furniture', re.I),
    re.compile(r'Platoon', re.I),
    re.compile(r'Dispatch', re.I),
    re.compile(r'Battlelog', re.I),
    re.compile(r'Neural', re.I),
    re.compile(r'Growth', re.I),
)

# A category holding something shows a count in a badge to the right of its name and level with it. Reading
# the rail once and opening only the categories that carry one costs a single look on a quiet day instead
# of six. A badge missed by OCR therefore means a purchase missed, never a purchase made by mistake - what
# is actually bought is decided by `PURCHASE_ALL` being on the category's own page.
BADGE = re.compile(r'^\d+$')
# How far apart a badge and its category's name may sit vertically, as a fraction of frame height. Generous
# because the name wraps onto two lines and OCR returns whichever line it pleases, while the badge sits
# level with the middle of both.
BADGE_ROW_TOLERANCE = 0.04

# The two buy buttons. "Purchase All" is only drawn on a category that has something in it, so its presence
# is the check for whether there is anything to buy here - a spent category shows Sold Out rows and no
# button at all. Both are matched in the bottom right, which takes in the buttons but not the dialog's
# "Confirm Purchase(s)" heading over on its left. Deliberately not the existing `PURCHASE`, which is a bare
# "Purchase" and would match that heading and the dialog's own title just as readily as either button.
PURCHASE_ALL = re.compile(r'Purchase All', re.I)
PURCHASE_CONFIRM = re.compile(r'Purchase\(?s\)?', re.I)

# Any sign of a real-money price. The free box and the paid one are two tabs of a single popup and carry
# an identical Purchase button, and claiming the free box switches the popup to the paid tab, so the item
# that is open is not necessarily the one that was clicked. Nothing is ever bought without checking this first.
PRICE = re.compile(r'[$€£¥]|\d+\.\d{2}')

# The purchase dialog's own area. Scoped tightly on purpose: the shop page stays visible around the
# dialog, including the featured item's price and its own Purchase button, and reading those as if they
# belonged to the dialog is what made an earlier version refuse a genuinely free box as costing $9.99.
DIALOG_BAND = (0.14, 0.13, 0.86, 0.84)

# Upper bound on free boxes to claim in one run. The loop normally ends when nothing reads Free any
# more. This only stops it spinning if a dialog ever leaves "Free" on screen.
MAX_FREE_BOXES = 3

# Regular Commissions -> Boundary Push, which lists Breakthrough and Phase Clash as stacked cards. Only
# Breakthrough is wanted, and both cards carry an identical Proceed button, so the card is picked by
# title rather than by the button. The rewards then sit behind the Crystal Collection button in the
# bottom-right, matched on the first word alone because it wraps onto two lines that OCR splits apart.
BOUNDARY_PUSH = re.compile(r'Boundary Push', re.I)
# The Breakthrough card's reward row - "Reward Progress-Deep Layer" over three counters. Only the first
# says whether anything is left to collect. The Phase Clash card below says "Reward Details" instead, so
# this heading picks out the right card on its own.
REWARD_PROGRESS = re.compile(r'Reward Progress', re.I)

BREAKTHROUGH = re.compile(r'Breakthrough', re.I)
CRYSTAL_COLLECTION = re.compile(r'Crystal', re.I)
# The collection screen's own dispatch button, on screen only while at least one of the four slots is
# still empty. That makes its presence the check for whether there is anything to send out, which beats
# reading the plus symbol drawn in an empty slot - OCR has no word to give back for that.
DISPATCH = re.compile(r'Dispatch', re.I)

# Opening the collection screen at the start of a season. The card plays an animation for a few seconds
# during which the button is drawn but not yet live, so the press lands on nothing and the screen never
# changes. Arrival is confirmed rather than assumed, and the press repeated while it has not happened.
CRYSTAL_OPEN_ATTEMPTS = 3
CRYSTAL_ARRIVAL_TIME_OUT = 6
# How long to wait for the button itself once the card has been opened. Covers the card screen loading as
# well, which is why it is longer than a wait for something on a screen already up - the press that gets
# here does not sleep afterwards, so this budget is the whole allowance rather than a second helping.
CRYSTAL_BUTTON_TIME_OUT = 8

# Crew Deck. Unlike every other screen this is a walkable 3D area, so its two stations are reached by
# holding movement keys for a fixed time rather than by clicking anything. Entering always drops the
# character at the same spawn point, which is what makes fixed durations workable - each station re-enters
# the deck first so its walk always starts from there.
TEA_TIME = re.compile(r'Tea Time', re.I)
# The second alternative stands alone because OCR drops the leading word of a two-word prompt often enough.
DELICIOUS_CUISINE = re.compile(r'Delicious Cuisine|Cuisine', re.I)


# Anchored, both of them. The cooking screen carries the words "Cannot Make Dishes" in its preview panel,
# which an unanchored Make would match.
MAKE = re.compile(r'^Make$', re.I)
NEXT = re.compile(r'^Next$', re.I)
# The Confirm Invite button, matched on its second word alone. `CONFIRM` would also match it, but naming
# the distinctive word keeps the two confirmations from being confused for one another.
INVITE = re.compile(r'Invite', re.I)

# The dish ends on an "Effects When Eaten" screen offering "To Battle!" beside Confirm. Nothing here ever
# clicks by position on that screen, because taking the wrong one of the two drops the bot into a battle
# it was never asked to fight. Named so a test can assert no pattern the flow clicks matches it.
TO_BATTLE = re.compile(r'To Battle', re.I)

# How many dishes are already in effect, from the line along the bottom of the dish screen: "Number of
# Experimental Dishes that can be effective at once 1/3". Anchored on the phrase rather than read as a
# bare counter, because the ingredient tiles on the same screen are covered in counters of their own.
ACTIVE_DISHES = re.compile(r'at once\s*(\d+)\s*/\s*\d+', re.I)

# Upper bounds on what follows an activity. The drink plays one scene, the dish two, one of which is
# dialogue whose Skip has to be pressed once per line, and skipping a scene can raise a confirmation of
# its own. None of that is a fixed shape, so these only stop the loops spinning on something that looks
# like a button but never goes away.
MAX_ACTIVITY_SCREENS = 4
MAX_SCENE_SKIPS = 10
MAX_SUMMARY_CONFIRMS = 3
SCENE_SKIP_TIME_OUT = 2
SUMMARY_CONFIRM_TIME_OUT = 3

# How long to give the first scene to come up after an activity is committed. Generous because it is only
# ever waited out when something has gone wrong - the normal path returns the moment Skip appears. Without
# it, the clearing loop reads the transition before the scene as the activity already being over.
ACTIVITY_START_TIME_OUT = 15

# Budgets for looks taken at a screen already known to be sitting still. A skip pass that found nothing
# has just spent its own budget watching that screen, and a scene that is genuinely playing offers Skip
# straight away, so waiting the full amount again only adds dead time to the end of every activity.
QUIET_CONFIRM_TIME_OUT = 1
SCENE_RECHECK_TIME_OUT = 0.5

# How long Confirm has to hold still before it is clicked. The button animates in, and a click that lands
# during that is swallowed - the summary stays up having done nothing. Waiting for the match to settle
# stops the press being thrown away rather than noticing afterwards that it was.
CONFIRM_SETTLE = 0.5

# The first two ingredient tiles on the cooking grid, measured off a 1920x1080 capture. Any two will do -
# the dish is only worth the buff it gives - so this takes the first two rather than reading the grid.
INGREDIENT_SPOTS = ((0.236, 0.283), (0.308, 0.283))

# (config key, default, settings text). Durations rather than coordinates, because the walk is the part
# that varies between setups and it is the only part a user can usefully tune.
WALK_OPTIONS = (
    ('Tea Time Walk', '0.636-1.25-0.495',
     'How long to hold each movement key walking from the Crew Deck entrance to the coffee machine, as left-forward-right in seconds.'),
    ('Delicious Cuisine Walk', '0.747',
     'How long to hold the back key walking from the Crew Deck entrance to the kitchen, in seconds.'),
)

# How long to give a screen to appear after the click that opens it. These waits re-read flat out, so a
# generous one spends its whole budget on a question the first redraw already answered.
SCREEN_SETTLE_TIME_OUT = 5

# How many times to look for the loaded deck, and how long to wait for a station prompt once the walk
# has finished. The first is a count, not seconds: `is_free_layer` divides it by its own interval and
# each attempt costs up to the framework's scene timeout of 10s, so 25 was a four-minute stall.
CREW_DECK_LOAD_ATTEMPTS = 3
STATION_PROMPT_TIME_OUT = 4

# The movement key hints along the top of the walkable deck. Seeing them means an activity is well and
# truly over - the deck is only walkable again once its scenes and summaries have closed themselves - so
# they are what says an activity has finished, rather than repeatedly failing to find a Skip or a Confirm.
# Failing to find something costs a whole timeout each time it is asked, and asking four times over on a
# screen that had already gone back to the deck is what made the end of every activity take nine seconds.
#
# The same list and threshold `is_free_layer` uses, since it is the same evidence about the same screen.
# Read in one shot here rather than through that method, which polls on a timeout of its own.
DECK_KEY_HINTS = ['Esc', 'P', 'M', 'F1', 'F2', 'F3', 'F4']
DECK_KEYS_NEEDED = 5


class Station(NamedTuple):
    """One Crew Deck activity, how to walk to it, and what to do once it opens."""

    # Name shown in the log and used in screenshot filenames.
    label: str
    # Text that appears when the character is close enough to interact.
    prompt: re.Pattern
    # Movement keys held in order, walking from the deck entrance.
    keys: list
    # Config key holding this walk's hold durations.
    config_key: str
    # Seconds to pause between key presses, measured off a real walk.
    sleep_between: float
    # Name of the method that performs the activity once the station is open.
    action: str


# Visited in this order, each starting from the deck entrance.
STATIONS = (
    Station('Tea Time', TEA_TIME, ['a', 'w', 'd'], 'Tea Time Walk', 0.7, 'make_drink'),
    # One key, unlike the CN route, which taps `d` after holding `s`. Walking it by hand showed the tap
    # is not needed to end up in reach of the kitchen.
    Station('Delicious Cuisine', DELICIOUS_CUISINE, ['s'], 'Delicious Cuisine Walk', 1, 'cook_dish'),
)


def parse_tickets(names):
    """Pick the event ticket count out of what OCR found in the top-right corner.

    The band holds the ticket icon as well as the number, and the icon reads as junk, so this takes the first thing that is entirely a number rather than
    the first thing found.

    Args:
        names: The text OCR read in the ticket band.

    Returns:
        The count, or None when nothing there was a number.
    """
    for name in names:
        if TICKET_COUNT.fullmatch(name.strip()):
            return int(name.replace(',', ''))
    return None


def parse_active_dishes(text):
    """Read how many experimental dishes are already in effect, off the dish selection screen.

    A dish is only worth cooking while none is active - the buff does not stack, so cooking on top of one spends ingredients for nothing.

    Args:
        text: The bottom of the dish screen as OCR read it.

    Returns:
        How many dishes are in effect, or None when the line could not be found. None means unknown, not zero, so an unreadable line does not turn into a
        wasted dish.
    """
    if not (found := ACTIVE_DISHES.search(text)):
        return None
    return int(found.group(1))


def parse_uses_left(text):
    """Read a station's remaining daily uses out of its interaction prompt.

    The prompt reads "Tea Time 1/1", where the first number is how many times it has already been used today. Each activity is once a day, so walking into a
    spent one wastes a trip and clicks through screens that will not do anything.

    Args:
        text: The prompt line as OCR read it.

    Returns:
        How many uses are left, or None when the text carries no counter. None means unknown, not spent - a counter OCR failed to read is no reason to skip
        an activity that may well be available.
    """
    if not (counter := COUNTER.search(text)):
        return None
    used, total = int(counter.group(1)), int(counter.group(2))
    return max(0, total - used)


def walk_times(option, key_count):
    """Turn a walk-timing setting into one hold duration per movement key.

    A setting may name fewer durations than the walk has keys. Missing trailing values become 0, which `press_keys_sequence` sends as a tap rather than a
    hold, so a setting that is too short shortens the walk instead of raising.

    Args:
        option: The setting value, for example "0.636-1.25-0.495".
        key_count: How many movement keys the walk uses.

    Returns:
        A list of exactly `key_count` floats.

    Raises:
        ValueError: The setting is not a dash-separated list of numbers.
    """
    times = parse_time_option(option)
    return (times + [0.0] * key_count)[:key_count]


class GlobalDailyTask(BaseGlobalTask):
    """Daily upkeep on the Global client.

    Global ships its own Loop automation, so this task mostly starts that and then picks up the handful of things Loop does not cover.
    """

    def __init__(self, *args, **kwargs):
        """Build the task and describe it for the sidebar.

        Args:
            *args: Passed to the framework task.
            **kwargs: Passed to the framework task.
        """
        super().__init__(*args, **kwargs)
        self.name = 'Global Daily'
        self.description = 'Starts the in-game Loop, claims free shop packs, and collects Boundary Push rewards.'
        self.support_schedule_task = True
        self.register_flows(FLOWS)
        self.default_config.update({key: default for key, default, _ in WALK_OPTIONS})
        self.config_description.update({key: description for key, _, description in WALK_OPTIONS})
        # Nest the walk timings under their flow, so they only show when the flow is on.
        self.default_config_group.update({'Crew Deck': [key for key, _, _ in WALK_OPTIONS]})
        self.default_config.update({key: False for key in FLOWS_OFF_BY_DEFAULT})

    def run(self):
        """Run every enabled daily flow, in the order `FLOWS` lists them."""
        self.run_flows(FLOWS, 'Global Daily complete.')

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Loop automation

    def start_loop(self):
        """Open the Dispatch Room, start the in-game Loop, and wait for it to report back.

        The Loop runs for minutes at a time against a static screen, so the wait is a throttled poll rather than a tight one. Anything the Loop covers is
        deliberately not automated here.
        """
        self.info_set('current_task', 'start_loop')
        # No sleep: the wait below is for the screen this click opens, so it already covers the loading.
        self.click_relative(*LOOP_ICON)
        if not self.wait_ocr(match=LOOP_SCREEN, box=self.box.left, time_out=SCREEN_SETTLE_TIME_OUT, log=True):
            return self.stop_flow('Clicking the Loop icon did not open the Dispatch Room, skipping.')
        if not self.wait_click_ocr(match=START_LOOP, box=self.box.bottom_left, time_out=SCREEN_SETTLE_TIME_OUT, after_sleep=2):
            return self.stop_flow('Could not find the Start Loop button, skipping.')
        self.log_info('Loop started, waiting for it to finish.', notify=True)
        if self.poll_ocr(LOOP_ENDED, box=self.box.top, time_out=LOOP_TIME_OUT, interval=LOOP_POLL_INTERVAL):
            self.log_info('Loop finished.', notify=True)
            # The summary lists everything the Loop collected, behind a single Confirm at the bottom.
            self.wait_click_ocr(match=CONFIRM, box=self.box.bottom, time_out=10, after_sleep=2)
        else:
            self.log_info(f'Loop did not report finishing within {LOOP_TIME_OUT}s.', notify=True)
        self.go_home()

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Shop

    def shopping(self):
        """Open the shop and claim every supply box that is currently free.

        The category and both tabs are opened by name rather than the shop being read wherever it happened to land. The landing page moves - a waiting free
        pack redirects into Quality Selection - and the free box sits somewhere different on each, so reading only the page the shop opened on missed both
        the weekly box and the daily one.
        """
        self.info_set('current_task', 'shopping')
        # No sleep: the category click below waits for the shop's own rail to appear.
        self.click_ocr_word(SHOP, box=self.box.right, raise_if_not_found=True)
        claimed = 0
        if self.click_ocr_word(QUALITY_SELECTION, box=self.box.left, time_out=5, after_sleep=2):
            for tab in FREE_BOX_TABS:
                if self.click_ocr_word(tab, box=self.box.top, time_out=5, after_sleep=2):
                    claimed += self.claim_free_boxes()
        else:
            # Without the category this is on a page it does not recognise, and the page is still worth
            # reading before giving up - it is where the daily box used to be claimed from.
            self.log_info('No Quality Selection category in the shop, claiming from the landing page instead.')
            claimed += self.claim_free_boxes()
        self.log_info(f'claimed {claimed} free supply box(es)')
        self.go_home()

    def claim_free_boxes(self):
        """Claim every free box on the page that is open.

        Returns:
            How many boxes were claimed.
        """
        claimed = 0
        for _ in range(MAX_FREE_BOXES):
            if not self.claim_free_box():
                break
            claimed += 1
        return claimed

    def claim_free_box(self):
        """Claim one supply box priced Free, if there is one.

        Returns:
            True when a box was claimed, False when none was free or the purchase did not go through.
        """
        free = self.wait_ocr(match=FREE, box=self.box_of_screen(*CARD_GRID), time_out=3)
        if not free:
            return False
        self.click(free[0], after_sleep=1.5)
        # Re-read the dialog before committing. Clicking Free is not proof that a free item is what
        # ended up open, so this asks the dialog itself: it has to say Free, and it has to show no price.
        # Both, so that neither a missing label nor an unreadable price is enough to authorise a spend.
        opened = self.ocr(box=self.box_of_screen(*DIALOG_BAND), log=True)
        if priced := self.find_boxes(opened, match=PRICE):
            self.log_info(f'the open item costs {priced[0].name}, backing out without buying', notify=True)
            self.back(after_sleep=1)
            return False
        if not self.find_boxes(opened, match=FREE):
            self.log_info('the open item is not marked Free, backing out without buying', notify=True)
            self.back(after_sleep=1)
            return False
        purchase = self.find_boxes(opened, match=PURCHASE)
        if not purchase:
            self.log_info('opened a free supply box but found no Purchase button, backing out.')
            self.back(after_sleep=1)
            return False
        self.click(purchase[0], after_sleep=1.5)
        self.wait_pop_up(time_out=5, count=2)
        self.close_pack_dialog()
        return True

    def close_pack_dialog(self):
        """Close the supply box popup, which is left showing a priced pack once the free one has been claimed.

        The free box and the paid one are two tabs of the same popup, and claiming the free box switches the popup over to the paid tab by itself. A
        priced dialog here is the normal end of a successful claim, not a misclick, but leaving it open blocks the way out of the shop.

        A price and a Cancel button both have to be present before anything is clicked. The shop page itself carries prices, so a price alone is not a
        dialog, and acting on one would mean pressing things on an ordinary page.

        Returns:
            True when a dialog was closed.
        """
        dialog = self.ocr(box=self.box_of_screen(*DIALOG_BAND), log=True)
        priced = self.find_boxes(dialog, match=PRICE)
        cancel = self.find_boxes(dialog, match=CANCEL)
        if not (priced and cancel):
            return False
        # Matched by name, never by position: Purchase sits directly beside Cancel in this dialog.
        self.log_info(f'closing the supply box popup, left showing the paid tab ({priced[0].name})')
        self.click(cancel[0], after_sleep=1.5)
        return True

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Wishlist

    def buy_wishlist(self):
        """Buy everything waiting in the shop Wishlist, one in-game shop at a time.

        The only flow that spends anything, so it is off until it is switched on, and it is built to fail towards buying nothing: it opens only categories
        whose rail badge says they hold something, presses Purchase All only where the game draws one, and reads the confirmation dialog for a real-money
        price before pressing anything in it.

        Select All is never touched. It comes up already ticked, so clicking it would clear the selection and buy nothing.
        """
        self.info_set('current_task', 'buy_wishlist')
        # No sleep: the Wishlist click below waits for the shop to be up.
        self.click_ocr_word(SHOP, box=self.box.right, raise_if_not_found=True)
        if not self.click_ocr_word(WISHLIST, box=self.box.bottom_left, time_out=5, after_sleep=2):
            return self.stop_flow('No Wishlist in the shop, skipping.', dump='wishlist_missing')
        flagged = self.flagged_categories()
        if not flagged:
            return self.stop_flow('Nothing waiting on the Wishlist.')
        bought = 0
        for category in flagged:
            if not self.click_ocr_word(category, box=self.box.left, time_out=5, after_sleep=2):
                self.log_info(f'could not open the {category.pattern} category, skipping it')
                continue
            if self.purchase_category(category.pattern):
                bought += 1
        self.log_info(f'bought from {bought} of {len(flagged)} Wishlist category(ies)', notify=True)
        self.go_home()

    def flagged_categories(self):
        """Which Wishlist categories carry a count badge.

        Read off one look at the rail rather than by opening each category in turn. The badge sits to the right of its category's name and level with it, so
        it is paired by position the same way `read_counter_under` pairs a counter with its heading.

        Returns:
            The patterns of the categories holding something, in rail order.
        """
        rail = self.ocr(box=self.box.left, log=True)
        badges = [box for box in rail if BADGE.match(box.name.strip())]
        tolerance = self.height * BADGE_ROW_TOLERANCE
        flagged = []
        for category in WISHLIST_CATEGORIES:
            found = self.find_boxes(rail, match=category)
            if not found:
                continue
            name = found[0]
            middle = name.y + name.height / 2
            if any(badge.x > name.x and abs(badge.y + badge.height / 2 - middle) <= tolerance for badge in badges):
                flagged.append(category)
        self.log_info(f'Wishlist categories holding something: {[category.pattern for category in flagged] or "none"}')
        return flagged

    def purchase_category(self, label):
        """Buy everything selected in the category that is open.

        Args:
            label: The category's name, for the log.

        Returns:
            True when a purchase went through.
        """
        # A category with nothing left shows Sold Out rows and no button at all, so this is the check for
        # whether there is anything here rather than a step that is expected to succeed.
        if not self.wait_click_ocr(match=PURCHASE_ALL, box=self.box.bottom_right, time_out=3, after_sleep=2):
            return False
        # Everything on the Wishlist trades in an in-game currency, so a real-money price here means this is
        # not the dialog it looks like. Checked before anything in it is pressed, the same way a free supply
        # box is checked before its Purchase.
        dialog = self.ocr(box=self.box_of_screen(*DIALOG_BAND), log=True)
        if priced := self.find_boxes(dialog, match=PRICE):
            self.log_info(f'{label}: the confirmation shows a real-money price ({priced[0].name}), backing out without buying', notify=True)
            self.back(after_sleep=1)
            return False
        if not self.wait_click_ocr(match=PURCHASE_CONFIRM, box=self.box.bottom_right, time_out=5, after_sleep=2):
            self.log_info(f'{label}: no confirm button on the Purchase Details dialog, backing out.', notify=True)
            self.back(after_sleep=1)
            return False
        self.log_info(f'{label}: bought what was on the Wishlist')
        self.wait_pop_up(time_out=5, count=2)
        return True

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Event Supply

    def run_event_supply(self):
        """Auto-battle the current event's last Supply stage.

        Every event has the same shape behind a differently-named banner, so nothing here matches the event's own title.
        """
        self.info_set('current_task', 'run_event_supply')
        # None of the clicks through this flow sleep afterwards. Each is followed by a wait for whatever it
        # is meant to bring up, and those waits return the moment it appears - a fixed sleep in front of one
        # is time spent whether or not the game needed it. The two clicks that do still sleep are the ones
        # whose effect no wait covers: the stage list is read outright, and Max only changes a number on a
        # dialog that is already up.
        self.click_relative(*EVENT_BANNER)
        if not self.wait_ocr(match=EVENT_PAGE, box=self.box.bottom_right, time_out=SCREEN_SETTLE_TIME_OUT, log=True):
            return self.stop_flow('No event banner on the home screen, skipping.')
        # Checked here, before anything is navigated to or spent. Without tickets the stage cannot be run
        # at all, so the whole trip through the map and the auto dialog would be for nothing.
        if self.event_tickets() == 0:
            return self.stop_flow('No event tickets left, so there is nothing to run.')
        if not self.wait_click_ocr(match=SUPPLY, box=self.box.bottom_right, time_out=5, after_sleep=3):
            return self.stop_flow('This event has no Supply mode, skipping.')
        stage = self.last_supply_stage()
        if not stage:
            return self.stop_flow('Found no Supply stages on the map, skipping.')
        self.log_info(f'running event supply stage {stage.name}')
        self.click(stage)
        if not self.wait_click_ocr(match=AUTO, box=self.box.bottom_right, time_out=5):
            return self.stop_flow('Found no Auto button on the stage panel, skipping.')
        if not self.wait_ocr(match=AUTO_DIALOG, box=self.box.center, time_out=5):
            return self.stop_flow('The Auto Mode dialog did not open, skipping.')
        # Take the maximum the remaining Expenditure allows. Missing this button costs a smaller run,
        # not a wrong one, so it is not worth failing over.
        self.click_relative(*MAX_BATTLES, after_sleep=1)
        if not self.wait_click_ocr(match=CONFIRM, box=self.box.center, time_out=5):
            return self.stop_flow('Could not confirm the auto battles, skipping.')
        # Whole frame rather than a region: the summary title sits at the top and the overlay prompt at
        # the bottom, and either can be the thing on screen when the battles end.
        if self.poll_ocr(BATTLES_DONE, time_out=EVENT_BATTLE_TIME_OUT, interval=5):
            self.log_info('auto battles finished, clearing the reward screens')
            self.wait_pop_up(time_out=20, count=4)
        else:
            self.log_info(f'Auto battles did not finish within {EVENT_BATTLE_TIME_OUT}s.', notify=True)
        self.go_home()

    def event_tickets(self):
        """How many event tickets are left, read off the top-right corner of the event page.

        Returns:
            The count, or None when it could not be read - in which case the caller should go ahead, since an unreadable count is not evidence of an empty
            one.
        """
        band = self.box_of_screen(*TICKETS_BAND)
        names = self.read_enlarged(band, TICKETS_ZOOM)
        tickets = parse_tickets(names)
        if tickets is None:
            # Second chance by a different route. A whole frame finds this glyph about half the time, which
            # is no use alone but is worth having behind a method that does not depend on the same luck.
            names += [box.name for box in self.find_boxes(self.ocr(log=True), boundary=band)]
            tickets = parse_tickets(names)
        if tickets is None:
            self.log_info(f'could not read the event ticket count from {names}, so going ahead')
            # Saved so the corner can be looked at directly. Guessing at coordinates for something that
            # reads as nothing at all is how the first attempt at this band went.
            self.dump_screen('event_tickets_unreadable')
        else:
            self.log_info(f'{tickets} event ticket(s) left')
        return tickets

    def last_supply_stage(self):
        """Scroll the Supply map to its right end and return the furthest-right stage node.

        The map opens part way along, and the last stage is the one worth running. Swiping stops early once a scroll reveals nothing new, so a short map
        costs no extra passes.

        Returns:
            The rightmost stage `Box`, or None when the map showed no stage codes.
        """
        band = self.box_of_screen(*STAGE_BAND)
        previous = stages = None
        for _ in range(STAGE_SWIPES):
            stages = self.ocr(match=map_re, box=band)
            names = tuple(sorted(box.name for box in stages))
            if names and names == previous:
                break
            previous = names
            self.swipe_relative(0.8, 0.5, 0.2, 0.5, duration=0.5, settle_time=1)
            self.next_frame()
            # Only the swipe invalidates what was read. Leaving the loop on unchanged names means the
            # last read still describes what is on screen, so it is kept rather than taken again.
            stages = None
        if stages is None:
            stages = self.ocr(match=map_re, box=band, log=True)
        return max(stages, key=lambda box: box.x) if stages else None

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Boundary Push

    def claim_boundary_push(self):
        """Collect the Breakthrough rewards under Regular Commissions -> Boundary Push."""
        self.info_set('current_task', 'claim_boundary_push')
        if not self.open_regular_commissions():
            return self.stop_flow('Could not open Regular Commissions, skipping Boundary Push.')
        # Searched across the whole frame rather than a measured corner. The label is distinctive enough
        # that a wider search cannot match the wrong thing, and one less guessed-at box is one less way
        # for this to fail silently. Clicked by word in case OCR merges it with the entry beside it.
        if not self.click_ocr_word(BOUNDARY_PUSH, time_out=5, after_sleep=3):
            return self.stop_flow('Boundary Push is not available, skipping.', dump='boundary_push_missing')
        # Checked before opening the card. Everything past this point is navigation towards a Claim All
        # that will not be there, and the card says so up front.
        # One read of the card, used by both checks below. Nothing is clicked between them, so it is the
        # same pixels either way.
        card = self.ocr(log=True)
        progress = self.read_counter_under(REWARD_PROGRESS, boxes=card)
        if progress is None:
            # Said out loud rather than passed over. Going on from here reaches a Crystal Collection that
            # is not there and reports nothing to collect, which reads as a game state rather than as the
            # failed read it actually is.
            self.log_info('Could not read the Breakthrough reward progress, so going on to look.')
            self.dump_screen('boundary_push_progress_unreadable')
        elif progress[0] >= progress[1]:
            return self.stop_flow(f'Breakthrough rewards are already at {progress[0]}/{progress[1]}, nothing to collect.')
        # No sleep: `open_crystal_collection` waits for the button this opens, and its budget covers the load.
        if not self.click_card_button(BREAKTHROUGH, PROCEED, after_sleep=0, boxes=card):
            return self.stop_flow('Found no Breakthrough card to open, skipping.', dump='boundary_push_no_breakthrough')
        if not self.open_crystal_collection():
            return self.stop_flow('Could not open Crystal Collection, skipping.', dump='boundary_push_no_crystal')
        if self.wait_click_ocr(match=CLAIM_ALL, box=self.box.bottom_right, time_out=5, after_sleep=2):
            self.wait_pop_up(time_out=5, count=2)
        self.dispatch_crystals()
        self.go_home()

    def open_crystal_collection(self):
        """Open Crystal Collection from the Breakthrough card, pressing again while the press does not take.

        At the start of a season the card plays an animation lasting a few seconds, and the button is drawn throughout it without yet being live, so the
        press is accepted by nothing and the screen stays where it was. One press is therefore not proof of arrival.

        Arrival is read off Claim All, which the collection screen carries whether or not there is anything to claim, so it says the screen is up without
        also saying something about what is on it.

        Returns:
            True once the collection screen is up, False when it was never reached.
        """
        for _ in range(CRYSTAL_OPEN_ATTEMPTS):
            if not self.wait_click_ocr(match=CRYSTAL_COLLECTION, box=self.box.bottom_right, time_out=CRYSTAL_BUTTON_TIME_OUT, after_sleep=2):
                return False
            if self.wait_ocr(match=CLAIM_ALL, box=self.box.bottom_right, time_out=CRYSTAL_ARRIVAL_TIME_OUT):
                return True
            self.log_info('the Crystal Collection press did not take, the card is probably still animating in')
        return False

    def dispatch_crystals(self):
        """Send dolls out to any empty collection slot.

        The button is only on screen while a slot is empty, so nothing here has to work out how many are, and a run that finds no button has nothing to
        send rather than a problem. Claiming does not free the slots up again in the same visit, so this normally acts on the visit after a claim.

        Returns:
            True when dolls were dispatched.
        """
        if not self.wait_click_ocr(match=DISPATCH, box=self.box.bottom_right, time_out=3, after_sleep=2):
            return False
        self.log_info('dispatched dolls to the empty collection slots')
        self.wait_pop_up(time_out=5, count=2)
        return True

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Crew Deck

    def crew_deck(self):
        """Visit each Crew Deck station in turn."""
        self.info_set('current_task', 'crew_deck')
        for station in STATIONS:
            try:
                times = walk_times(self.config.get(station.config_key), len(station.keys))
            except ValueError:
                self.log_info(f'The {station.config_key} setting is not a list of numbers, skipping {station.label}.', notify=True)
                continue
            if not self.enter_crew_deck():
                self.log_info('Could not get into the Crew Deck, skipping the rest.', notify=True)
                self.leave_crew_deck()
                return
            self.log_info(f'walking to {station.label}, holding {list(zip(station.keys, times))}')
            self.press_keys_sequence(station.keys, times, sleep_between=station.sleep_between)
            self.sleep(1)
            self.open_station(station)
            # Back to the entrance between stations, so the next walk starts where its timings were measured.
            self.leave_crew_deck()

    def in_walkable_deck(self):
        """Whether the walkable Crew Deck is on screen, in one look.

        Returns:
            True when enough of the movement key hints are up to mean the deck is back.
        """
        hints = self.find_boxes(self.ocr(box=self.box.top), match=DECK_KEY_HINTS)
        return len(hints) >= DECK_KEYS_NEEDED

    def leave_crew_deck(self):
        """Back out to the home screen with Escape.

        Deliberately not `go_home`. The station screens have no home button - the spot it clicks holds an info button instead, so pressing it there opens a
        panel rather than going anywhere. Backing out unwinds these screens reliably, and `is_main` answers the leave-the-deck confirmation on the way.

        A scene is skipped first if one is still playing. Escape does not exit a scene, so backing out of one means pressing it at a screen that cannot
        answer until the scene ends by itself, which reads in the log as the bot hanging. Skipped when the deck is already walkable, because a scene and
        the walkable deck cannot both be on screen.
        """
        if not self.in_walkable_deck():
            self.skip_scene('leaving the Crew Deck', time_out=SCENE_RECHECK_TIME_OUT)
        self.ensure_main(time_out=60)

    def enter_crew_deck(self):
        """Open the Crew Deck from the home screen and wait for it to become walkable.

        Returns:
            True once the walkable deck is up, False when it was not reached.
        """
        # No sleep: `is_free_layer` below waits for the movement key hints, which appear only once the deck
        # has finished loading, so it already covers everything this sleep was covering.
        if not self.wait_click_ocr(match=CREW_DECK, box=self.box.right, time_out=5):
            self.log_info('No Crew Deck entry on the home screen.')
            return False
        # Confirmed by the movement key hints along the top, which read the same in every language. Waiting
        # on those rather than on a title also means the deck is not merely open but finished loading.
        if not self.is_free_layer(time_out=CREW_DECK_LOAD_ATTEMPTS):
            self.log_info('The Crew Deck did not finish loading into its walkable view.')
            return False
        return True

    def open_station(self, station):
        """Interact with one station and run its activity, unless it is already spent for the day.

        Args:
            station: The `Station` being visited.

        Returns:
            True when the station was handled, whether the activity ran or was correctly skipped. False when it was never reached or could not start.
        """
        entry = self.wait_ocr(match=station.prompt, time_out=STATION_PROMPT_TIME_OUT, log=True)
        if not entry:
            self.log_info(f'{station.label}: no prompt after walking, so the walk did not end within reach. Adjust the walk setting.', notify=True)
            self.dump_screen(f'crew_deck_{station.label}_no_prompt')
            return False
        if self.uses_left(entry) == 0:
            self.log_info(f'{station.label}: already done today, skipping it.', notify=True)
            return True
        # Alt has to be held while clicking, because the Crew Deck hides the cursor until it is pressed.
        self.click_with_key('alt', entry, after_sleep=2)
        return getattr(self, station.action)()

    def active_dishes(self):
        """How many experimental dishes are already in effect.

        Read off the line along the bottom of the dish screen rather than the counter on any one tile. The whole bottom is OCR'd and joined, because the
        sentence is long enough that OCR sometimes breaks it in two.

        Returns:
            The number in effect, or None when the line could not be read.
        """
        text = ' '.join(box.name for box in self.ocr(box=self.box.bottom, log=True))
        active = parse_active_dishes(text)
        if active is None:
            self.log_info('could not read how many dishes are in effect, so going ahead')
        return active

    def uses_left(self, entry):
        """Read how many times a station can still be used today, off its interaction prompt.

        OCR returns the label and the counter as separate boxes often enough that this reads the whole line the prompt sits on rather than the matched box
        alone.

        Args:
            entry: The boxes that matched the station prompt.

        Returns:
            How many uses are left, or None when no counter could be read.
        """
        line = Box(x=entry[0].x, y=entry[0].y, to_x=self.width, to_y=entry[0].y + entry[0].height)
        text = ' '.join(box.name for box in self.ocr(box=line, log=True))
        left = parse_uses_left(text)
        if left is None:
            self.log_info(f'no daily counter on the prompt ("{text}"), so going ahead')
        else:
            self.log_info(f'prompt "{text}" leaves {left} use(s) today')
        return left

    def make_drink(self):
        """Make the drink Tea Time opens with already selected.

        Every drink grants a bonus and the screen preselects one, so there is nothing to choose - pressing Make takes whatever is highlighted.

        Returns:
            True when the drink was confirmed, False when either step was missing.
        """
        if not self.wait_click_ocr(match=MAKE, box=self.box.bottom_right, time_out=5, after_sleep=2):
            self.log_info('Tea Time: no Make button on the drink screen.', notify=True)
            return False
        # Make raises a Caution dialog - "Do you wish to make X? N time(s) remaining today" - with Cancel
        # sitting beside Confirm. Matched by name rather than clicked by position, so the wrong one of the
        # two can never be hit. Nothing is made until this lands.
        if not self.wait_click_ocr(match=CONFIRM, box=self.box.bottom, time_out=6, settle_time=CONFIRM_SETTLE, after_sleep=2):
            self.log_info('Tea Time: the Make confirmation never appeared, so no drink was made.', notify=True)
            self.dump_screen('crew_deck_Tea_Time_no_confirm')
            return False
        self.finish_activity('Tea Time')
        return True

    def cook_dish(self):
        """Cook a dish from the first two ingredients, then invite whichever doll is preselected.

        Neither choice matters here - the dish is wanted for the buff it grants, not for itself - so this takes the first two ingredients and the doll the
        screen already highlights. The ingredient tiles carry counts rather than names, so they are clicked by position.

        Returns:
            True when the invite was confirmed or there was nothing to cook, False when a step was missing.
        """
        if active := self.active_dishes():
            self.log_info(f'Delicious Cuisine: {active} dish(es) already in effect, so nothing to cook.', notify=True)
            return True
        for spot in INGREDIENT_SPOTS:
            self.click_relative(*spot, after_sleep=0.6)
        if not self.wait_click_ocr(match=NEXT, box=self.box.bottom_right, time_out=5, after_sleep=2):
            self.log_info('Delicious Cuisine: no Next button, so the ingredients probably did not take.', notify=True)
            self.dump_screen('crew_deck_Delicious_Cuisine_no_next')
            return False
        # Next opens the Invite Doll step, which already has a doll selected. Matching the single word
        # rather than "Confirm Invite" survives OCR splitting the label, and within the bottom right of
        # this screen that word belongs to no other button.
        if not self.wait_click_ocr(match=INVITE, box=self.box.bottom_right, time_out=6, after_sleep=2):
            self.log_info('Delicious Cuisine: no Confirm Invite button on the Invite Doll step.', notify=True)
            self.dump_screen('crew_deck_Delicious_Cuisine_no_invite')
            return False
        self.finish_activity('Delicious Cuisine')
        return True

    def finish_activity(self, label):
        """Clear the scenes and summaries that follow an activity, and record anything left unrecognised.

        Committing an activity plays one or more scenes, each offering Skip in the top right, and ends on a reward summary behind a Confirm. The drink plays
        one scene and the dish two, and skipping can raise a confirmation of its own, so this alternates between the two buttons until neither is on screen
        rather than assuming a fixed number of either.

        The loop ends on the walkable deck coming back, which is positive proof the activity is over and costs one look. Falling out of the bottom instead -
        finding neither button - is the unexplained ending, and that one is dumped so a run says what was left on screen rather than leaving it assumed.

        The dish's closing screen puts `To Battle!` next to Confirm, so the Confirm is matched by name. Clicking either by position would be a coin flip
        between finishing and starting a battle.

        Args:
            label: The station name, for the log and the screenshot filename.
        """
        # The scene does not start the instant the activity is committed - the game plays a transition
        # first, and a loop that looks during it finds nothing and concludes the activity is already over.
        # Waited on Skip alone rather than on Skip or Confirm, because the Caution dialog's own Confirm can
        # still be fading when this is reached and would satisfy the wait without the scene having started.
        if not self.wait_ocr(match=SKIP, box=self.box.top_right, time_out=ACTIVITY_START_TIME_OUT):
            self.log_info(f'{label}: no scene started, clearing whatever is on screen instead')
        for _ in range(MAX_ACTIVITY_SCREENS):
            # Asked first, and before anything is waited for. Every other ending here has to be established
            # by failing to find something, which costs that look's whole budget each time it is asked.
            if self.in_walkable_deck():
                self.log_info(f'{label}: back in the Crew Deck, so the activity is done')
                return
            skipped = self.skip_scene(label)
            # A skip pass that found nothing has already waited out its own budget at a screen that did not
            # change, so the summary check does not need to be patient as well - a Confirm worth clicking
            # would have been there throughout. Only a pass that skipped something is followed by a screen
            # still in motion, and that one keeps the full budget.
            confirm_time_out = SUMMARY_CONFIRM_TIME_OUT if skipped else QUIET_CONFIRM_TIME_OUT
            confirmed = self.confirm_summary(label, time_out=confirm_time_out)
            if not skipped and not confirmed:
                break
        self.wait_pop_up(time_out=10, count=3)
        self.dump_screen(f'crew_deck_{label}_after')

    def skip_scene(self, label, time_out=SCENE_SKIP_TIME_OUT):
        """Press Skip until it stops appearing.

        One press is not always enough. The dish ends on a line of dialogue, where Skip advances rather than exits, so it takes a press per line. Each look
        is short, so the passes that find nothing cost little and the loop ends as soon as the scene does.

        Args:
            label: The station name, for the log.
            time_out: How long each look waits for Skip. Callers checking a screen that should already be settled pass a shorter one, since a scene that is
                playing offers Skip straight away and only a scene mid-transition needs waiting for.

        Returns:
            How many times Skip was pressed.
        """
        presses = 0
        for _ in range(MAX_SCENE_SKIPS):
            if not self.wait_click_ocr(match=SKIP, box=self.box.top_right, time_out=time_out, after_sleep=2):
                break
            presses += 1
        if presses:
            self.log_info(f'{label}: pressed Skip {presses} time(s)')
        return presses

    def confirm_summary(self, label, time_out=SUMMARY_CONFIRM_TIME_OUT):
        """Press Confirm until it stops appearing.

        One press is not proof it took. The button animates in, and a click landing before it has settled is swallowed, leaving the summary up with nothing
        having happened. Pressing until the button is gone covers that without the loop above having to spend a whole extra pass discovering it.

        Re-read and matched by name every time rather than simply clicked twice. The dish's closing screen puts `To Battle!` beside Confirm, so a second
        click at the same spot once the summary has closed would be a coin flip between doing nothing and starting a battle.

        Args:
            label: The station name, for the log.
            time_out: How long the first look waits for Confirm. Later looks are always brief, since by then the screen has been clicked and waited on and
                a button still there is there to stay.

        Returns:
            How many times Confirm was pressed.
        """
        presses = 0
        for _ in range(MAX_SUMMARY_CONFIRMS):
            if not self.wait_click_ocr(match=CONFIRM, box=self.box.bottom, time_out=time_out, settle_time=CONFIRM_SETTLE, after_sleep=2):
                break
            presses += 1
            time_out = QUIET_CONFIRM_TIME_OUT
        if presses:
            self.log_info(f'{label}: pressed Confirm {presses} time(s)')
        return presses
