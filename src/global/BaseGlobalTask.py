import os
import re
import time

import cv2
import pywintypes
import win32api

from src.data.FeatureList import FeatureList as fL
from src.tasks.BaseGfTask import BaseGfTask

# Shared on-screen vocabulary. Every pattern here is compiled with re.I, so no pattern needs its own
# character classes for case. Anything referenced by more than one module in this package belongs here
# rather than being restated, because the Global client does rename labels - Public Area became Crew Deck.
CONFIRM = re.compile(r'Confirm', re.I)
CANCEL = re.compile(r'Cancel', re.I)
CLICK_ANYWHERE = re.compile(r'(Click|Tap) anywhere', re.I)
CAMPAIGN = re.compile(r'Campaign', re.I)
CREW_DECK = re.compile(r'Public Area|Crew Deck', re.I)
SHOP = re.compile(r'\bShop\b', re.I)
COMMISSIONS = re.compile(r'Commissions', re.I)
# Commissions opens on Daily Quests. Regular Commissions is the tab beside it, and is the hub for
# Expansion Drills, Boss Fight, Peak Value Assessment and Boundary Push.
REGULAR_COMMISSIONS = re.compile(r'Regular Commissions', re.I)
SKIP = re.compile(r'Skip', re.I)
DO_NOT_REMIND = re.compile(r'not remind|remind me', re.I)

# Dismissable overlays that sit on top of whatever screen we actually want.
POP_UPS = [
    CLICK_ANYWHERE,
    re.compile(r'anywhere to (exit|close|continue)', re.I),
    re.compile(r'New Cycle', re.I),
]

# Labels down the right edge of the home screen. Anchored on single distinctive words because English OCR splits multi-word labels into separate boxes far
# more often than Chinese does.
MAIN_SCREEN_LABELS = [
    CAMPAIGN,
    re.compile(r'Refitting', re.I),
    CREW_DECK,
    re.compile(r'Recruitment', re.I),
    SHOP,
]

# Buttons that clear a blocking dialog on the way back to the home screen.
MAIN_SCREEN_BLOCKERS = [
    re.compile(r'Click to Start', re.I),
    CLICK_ANYWHERE,
    CANCEL,
]

# Walking out of the Crew Deck raises a confirmation ("Do you wish to leave the Crew Deck?") that
# Escape does not dismiss - it has to be answered or the way home is blocked. Kept loose because OCR
# splits long sentences; `is_main` only acts on it when a Confirm button is on screen too.
LEAVE_PROMPT = re.compile(r'leave|exit|quit', re.I)

# Longest a home-screen menu entry can be. Loading screens describe the ship in prose that names the very
# same places - "...Engine Room, Refitting Room, a Crew Deck, Lounge and other..." - which otherwise
# satisfies the home-screen check and makes the bot think it has arrived. Menu entries are short and
# standalone; sentences are neither.
MAX_MENU_LABEL = 16


# An "n of m" counter. The game uses this shape everywhere - a station's daily uses, a card's reward
# progress, a stage's clear count - so it lives here rather than being restated per screen.
COUNTER = re.compile(r'(\d+)\s*/\s*(\d+)')

# How far below a heading to look for the counters belonging to it, as a fraction of frame height. Small
# on purpose: cards stack their own headings only a little further down, and reading the next one's
# numbers would answer a different question than the one asked.
COUNTER_BAND = 0.06

# How far left of its heading a counter may start, as a fraction of frame width. A row belongs to the
# heading above it and lines up with it, while the screen's own sidebar sits further left at the same
# height - "Attempts: 3/3" is level with the Breakthrough card's reward row - and would otherwise win
# on being leftmost.
COUNTER_LEFT_TOLERANCE = 0.02

# Vertical extent of the bottom navigation bar, as a fraction of frame height.
NAV_STRIP_TOP = 0.86

# Most screens carry a home button in the top-left, immediately right of the Back arrow. It jumps
# straight to the home screen, where backing out has to unwind one screen at a time. Unlabelled, so it
# has to be clicked by position. On the home screen itself that spot is empty, so a stray press is safe.
HOME_BUTTON = (0.076, 0.048)

# How long to give the home button before falling back to backing out with Escape, and how often to look.
# The timeout is short on purpose: when the button does not take, waiting on it just looks like the bot
# has hung. The interval matters because every look costs up to three OCR passes - polling flat out
# spends the whole window re-reading a screen that is not going to change until something is pressed.
HOME_BUTTON_TIME_OUT = 3
HOME_BUTTON_CHECK_INTERVAL = 1

# Per-look timeout when clearing overlays, and how long a match must hold before it is acted on. Both
# small: overlays appear immediately once the screen they belong to is up, so a longer wait only delays
# the discovery that there are none left.
POP_UP_CHECK_TIME_OUT = 2
POP_UP_SETTLE = 1
POP_UP_AFTER_CLICK = 1.5

# Where a poll starts before backing off toward its caller's interval.
POLL_MIN_INTERVAL = 1

# How long to keep trying to put the cursor back after Windows refused, and how often. Bounded, because
# by the time this is reached the action it belonged to has already happened - only the cursor is owed.
CURSOR_RESTORE_SECONDS = 15
CURSOR_RESTORE_INTERVAL = 0.5

# Where `dump_screen` keeps its frames. Deliberately not the screenshots folder, which the framework
# empties on every start - a frame saved to diagnose a problem is worthless if the next run deletes it
# before it can be looked at, which is exactly what happened to the first one saved here.
DUMP_FOLDER = 'debug_frames'


def first_counter(name):
    """Read the first "n of m" counter out of a piece of text.

    Deliberately not a whole-string match. OCR merges a row of counters into a single box - the Breakthrough card's three come back as
    "24/24 112/112 m168/168", complete with a stray character where an icon was - so the first counter has to be picked out of the text rather than the text
    being a counter on its own. Callers keep the wrong counters out by position, not by being strict here.

    Args:
        name: The detected text.

    Returns:
        A (done, total) pair, or None when there is no counter in the text.
    """
    match = COUNTER.search(name)
    return (int(match.group(1)), int(match.group(2))) if match else None


def is_menu_label(name):
    """Whether an OCR result looks like a menu entry rather than a sentence mentioning one.

    Args:
        name: The detected text.

    Returns:
        True when the text is short and free of sentence punctuation.
    """
    return len(name) <= MAX_MENU_LABEL and not any(character in name for character in ',.')


class BaseGlobalTask(BaseGfTask):
    """Base for tasks that drive the Global (English) client.

    Inherits the language-independent machinery from `BaseGfTask` - HSV isolation, the numeric regexes, screenshot and debug plumbing - and replaces every
    method that compares against hardcoded Simplified Chinese with one that matches English on-screen text directly.
    """

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Opting out of the reverse OCR translation

    def fix_texts(self, detected_boxes):
        """Normalise OCR results without rewriting them into Chinese.

        The `i18n/*/ocr.po` catalogs map English game text back onto the Chinese literals the CN tasks compare against. Global tasks match English directly,
        so that rewrite has to not happen here. The framework calls this through `self`, so overriding it opts this task out without touching global state -
        the CN tasks, `DiagnosisTask` and the existing tests all keep their translation. Runtime `add_text_fix` entries still apply.

        Args:
            detected_boxes: Boxes straight off the OCR engine, modified in place.
        """
        for detected_box in detected_boxes:
            detected_box.name = detected_box.name.strip()
            if fix := self.executor.text_fix.get(detected_box.name):
                detected_box.name = fix

    def fix_match_regex(self, match):
        """Pass match patterns through untouched.

        The base implementation translates regex patterns through the same reverse catalog, which would corrupt the English patterns used here.

        Args:
            match: Whatever was passed as `match=`.

        Returns:
            `match`, unchanged.
        """
        return match

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Surviving the cursor being fought over

    def despite_cursor_error(self, action, label, /, *args, **kwargs):
        """Run an interaction, surviving Windows refusing to move the cursor.

        The Genshin interaction warps the real cursor onto the game before each action and puts it back afterwards. `SetCursorPos` fails when something else
        holds the input queue, which is exactly what happens when the mouse is in use while the bot runs, and the whole task dies on an error that has
        nothing to do with the game.

        The action itself is not repeated. The failing restore runs after it, and the framework already swallows exceptions from the action, so by the time
        this is reached the key, click or swipe has landed. Doing it again would press twice - a walk that goes too far, or a stage clicked when it was not
        meant to be - while letting it through at worst loses one, which shows up as a step that did not take and says so.

        Args:
            action: The bound superclass method to call.
            label: What to call it in the log. Positional-only, along with `action`, because the wrapped methods take arguments of their own that would
                otherwise bind to these - `click` has its own `name`, and passing it used to raise instead of clicking.
            *args: Positional arguments for `action`.
            **kwargs: Keyword arguments for `action`.

        Returns:
            Whatever `action` returned, or None when the cursor move was refused.
        """
        try:
            return action(*args, **kwargs)
        except pywintypes.error as error:
            self.log_info(f'{label}: Windows would not move the cursor ({error.funcname}), recovering')
            self.recover_cursor(label)
            return None

    def recover_cursor(self, label):
        """Undo what a refused cursor move left behind.

        Two things are owed. First, input may still be blocked: the framework blocks it for the length of a click and unblocks it only after putting the
        cursor back, so when putting it back throws, the unblock never runs and the keyboard and mouse stay frozen for as long as the app lives. That is
        released first and unconditionally, since unblocking input that is not blocked does nothing.

        Second, the cursor is wherever the bot left it rather than where its owner left it. That is retried rather than given up on, because the reason it
        failed - the mouse being in use - passes on its own. It is not retried forever, and failing to restore it is not raised: the action it belonged to
        already happened, so there is nothing to abort.

        Args:
            label: What to call the interaction in the log.
        """
        interaction = self.executor.interaction
        if unblock := getattr(interaction, 'unblock_input', None):
            unblock()
        position = getattr(interaction, 'cursor_position', None)
        if not position:
            return
        deadline = time.time() + CURSOR_RESTORE_SECONDS
        while time.time() < deadline:
            try:
                win32api.SetCursorPos(position)
                return
            except pywintypes.error:
                self.sleep(CURSOR_RESTORE_INTERVAL)
        self.log_info(f'{label}: the cursor could not be put back within {CURSOR_RESTORE_SECONDS}s, leaving it where it is')

    def send_key(self, *args, **kwargs):
        """Send a key, surviving the cursor being fought over.

        Args:
            *args: Passed through.
            **kwargs: Passed through.

        Returns:
            Whatever the base implementation returned, or None when the cursor move was refused.
        """
        return self.despite_cursor_error(super().send_key, 'send_key', *args, **kwargs)

    def click(self, *args, **kwargs):
        """Click, surviving the cursor being fought over.

        Args:
            *args: Passed through.
            **kwargs: Passed through.

        Returns:
            Whatever the base implementation returned, or None when the cursor move was refused.
        """
        return self.despite_cursor_error(super().click, 'click', *args, **kwargs)

    def swipe(self, *args, **kwargs):
        """Swipe, surviving the cursor being fought over.

        `swipe_relative` goes through here too, so scrolling a map is covered as well.

        A swipe needs more than the cursor put back. It presses the button, moves, and releases, each through the same call that can be refused, and a
        refusal on the way in unwinds past the release - leaving the button held, which turns every later click into a drag. The release is reissued here
        rather than in `recover_cursor`, because a click that failed the same way has already released and would not survive a second one.

        Args:
            *args: Passed through.
            **kwargs: Passed through.

        Returns:
            Whatever the base implementation returned, or None when the cursor move was refused.
        """
        try:
            return super().swipe(*args, **kwargs)
        except pywintypes.error as error:
            self.log_info(f'swipe: Windows would not move the cursor ({error.funcname}), releasing the button and recovering')
            self.release_mouse()
            self.recover_cursor('swipe')
            return None

    def release_mouse(self):
        """Let go of the mouse button after a swipe was interrupted part way through."""
        release = getattr(self.executor.interaction, 'mouse_up', None)
        if not release:
            return
        try:
            release()
        except pywintypes.error as error:
            self.log_info(f'the mouse button could not be released ({error.funcname})')

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Clicking

    @property
    def nav_strip(self):
        """Full-width box covering just the bottom navigation bar.

        Kept full width on purpose. OCR often returns two adjacent nav buttons as a single box (`Voyage Formation`), and clipping horizontally would cut the
        merged label that `click_ocr_word` needs in order to aim. Trimming vertically is free and drops most of the pixels.

        Returns:
            A `Box` spanning the frame width across the nav bar's height.
        """
        return self.box_of_screen(0, NAV_STRIP_TOP)

    def click_ocr_word(self, match, box=None, time_out=5, after_sleep=0, raise_if_not_found=False):
        """Click a word, even when OCR merged it into a box with its neighbour.

        English labels sit close together on the bottom nav, and OCR regularly returns two adjacent buttons as one box - `Voyage Formation`, or
        `Commissions Platoon`. The usual `wait_click_ocr` clicks the centre of such a box, which lands between the two buttons and hits neither. This aims at
        the matched word's own share of the box instead. Use it for anything on the bottom nav.

        Args:
            match: Pattern to look for.
            box: Region to search in.
            time_out: Seconds to wait for the text to appear.
            after_sleep: Seconds to wait after clicking.
            raise_if_not_found: Raise instead of returning None when the text never appears.

        Returns:
            The box that was clicked, or None when nothing matched.
        """
        result = self.wait_ocr(match=match, box=box, time_out=time_out, raise_if_not_found=raise_if_not_found)
        if not result:
            return None
        self.click_box_by_match_position(result, match, after_sleep=after_sleep)
        return result[0]

    def poll_ocr(self, match, box=None, time_out=60, interval=5):
        """Watch for text over a long stretch without pinning the CPU.

        `wait_ocr` re-captures and re-OCRs with no gap between attempts, which is right for a button that should already be there and wasteful for something
        minutes away - the in-game Loop finishing, for instance. This trades a little latency for roughly two orders of magnitude fewer OCR calls.

        Args:
            match: Pattern to look for.
            box: Region to search in.
            time_out: Seconds to keep watching.
            interval: Seconds between checks.

        Returns:
            The matching boxes, or None if the text never appeared.
        """
        deadline = time.time() + time_out
        checks = 0
        # Start responsive and back off. Some of these waits end almost immediately - an auto battle
        # sweep resolves in seconds - and a fixed long interval would sit through that for no reason,
        # while a fixed short one would be wasteful across the ten minutes a Loop can take.
        wait = POLL_MIN_INTERVAL
        while time.time() < deadline:
            if found := self.ocr(match=match, box=box):
                return found
            checks += 1
            # Logged because a silent wait is indistinguishable from a hang.
            if checks % 6 == 0:
                self.log_info(f'still waiting, {int(deadline - time.time())}s left')
            self.sleep(min(wait, max(0, deadline - time.time())))
            wait = min(wait * 2, interval)
            self.next_frame()
        return None

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Navigation

    def dump_screen(self, label):
        """Log every line of text on screen and save the frame beside it.

        For screens whose wording is not yet known. A run's log then carries the exact strings to match on, rather than them being guessed at from the
        Chinese. Left in the code afterwards, because the next unknown screen needs the same thing.

        Args:
            label: Name for the screenshot file, and the prefix on each logged line.
        """
        self.screenshot(label)
        self.keep_frame(label)
        try:
            boxes = self.ocr(log=True)
        except AttributeError:
            self.log_info(f'{label}: capture returned an empty frame, nothing to read')
            return
        self.log_info(f'{label}: {len(boxes)} line(s) on screen')
        for box in boxes:
            self.log_info(f'{label}: "{box.name}" at ({box.x}, {box.y}) {box.width}x{box.height}')

    def click_card_button(self, title, button, box=None, after_sleep=2):
        """Click the button belonging to one card in a stacked list.

        Regular Commissions lists its modes as full-width cards, each with its own identically-labelled button - Boundary Push shows a `Proceed` on both the
        Breakthrough card and the Phase Clash card below it. Matching on the button alone picks whichever OCR happened to return first, which is a coin flip
        between the mode we want and one we do not. A card's title always sits above its own button, and the next card's title sits below it, so the first
        button under the title is that title's button.

        Args:
            title: Pattern identifying the card.
            button: Pattern identifying the button, which repeats on every card.
            box: Region to search in, defaulting to the whole frame.
            after_sleep: Seconds to wait after clicking.

        Returns:
            The button box that was clicked, or None when the card or its button was not found.
        """
        boxes = self.ocr(box=box, log=True)
        found = self.find_boxes(boxes, match=title)
        if not found:
            return None
        below = sorted([candidate for candidate in self.find_boxes(boxes, match=button) if candidate.y > found[0].y], key=lambda candidate: candidate.y)
        if not below:
            return None
        self.click(below[0], after_sleep=after_sleep)
        return below[0]

    def read_counter_under(self, label, box=None, band=COUNTER_BAND):
        """Read the leftmost "n of m" counter sitting just below a heading.

        Cards put a row of counters under a heading and only the first of them says whether anything is left. OCR returns them in no dependable order, so
        they are picked by position - on the line below the heading, leftmost first - the same way `click_card_button` picks a button.

        Args:
            label: Pattern identifying the heading.
            box: Region to search in, defaulting to the whole frame.
            band: How far below the heading to look, as a fraction of frame height.

        Returns:
            A (done, total) pair, or None when the heading or any counter under it was not found.
        """
        boxes = self.ocr(box=box, log=True)
        found = self.find_boxes(boxes, match=label)
        if not found:
            return None
        heading = found[0]
        limit = heading.y + self.height * band
        left = heading.x - self.width * COUNTER_LEFT_TOLERANCE
        under = [candidate for candidate in boxes
                 if heading.y < candidate.y <= limit and candidate.x >= left and first_counter(candidate.name)]
        if not under:
            return None
        return first_counter(min(under, key=lambda candidate: candidate.x).name)

    def keep_frame(self, label):
        """Save the current frame somewhere a restart will not delete it.

        Args:
            label: Used in the filename.
        """
        frame = self.frame
        if frame is None:
            return
        os.makedirs(DUMP_FOLDER, exist_ok=True)
        path = os.path.join(DUMP_FOLDER, f'{label}_{int(time.time())}.png')
        try:
            cv2.imwrite(path, frame)
            self.log_info(f'{label}: frame kept at {path}')
        except Exception as error:
            self.log_info(f'{label}: could not keep the frame ({error})')

    def read_enlarged(self, band, zoom):
        """OCR a region after enlarging it, for text too small to be detected at its own size.

        The detector looks for lines of text, and a glyph only a few pixels across does not look like one. It is missed outright in a crop, because a crop
        is resized down before detection, and found only about half the time in a whole frame. Enlarging the region first and handing that over as the frame
        gives the detector something the size of ordinary on-screen text.

        Args:
            band: The `Box` to read.
            zoom: How much to enlarge it by.

        Returns:
            The text found, or an empty list.
        """
        frame = self.frame
        if frame is None:
            return []
        crop = frame[band.y:band.y + band.height, band.x:band.x + band.width]
        if not crop.size:
            return []
        enlarged = cv2.resize(crop, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_CUBIC)
        return [box.name for box in self.ocr(frame=enlarged, log=True)]

    def open_regular_commissions(self):
        """Navigate home -> Commissions -> Regular Commissions.

        Both clicks go through `click_ocr_word`, because OCR merges neighbours on both screens. The bottom nav comes back as `Commissions Platoon`, and the
        tab row along the top comes back as one box reading `Regular Commissions Journey Witness Journey Milestone` - clicking its centre opens Journey
        Witness, the middle tab. The screen opens on Daily Quests, so the tab has to be selected explicitly.

        Returns:
            True when the Regular Commissions tab opened, False when it could not be reached.
        """
        self.click_ocr_word(COMMISSIONS, box=self.nav_strip, after_sleep=2, raise_if_not_found=True)
        return bool(self.click_ocr_word(REGULAR_COMMISSIONS, box=self.box.top, time_out=10, after_sleep=2))

    def is_main(self, recheck_time=0.0, esc=True):
        """Decide whether the home screen is showing.

        Two independent signals are pooled: the right-hand menu labels, and the two home-only icons. Requiring a quorum of two keeps a single OCR misread or
        a partly faded label from flipping the answer.

        Args:
            recheck_time: Unused here, kept for signature parity with the CN base.
            esc: Send Escape when the screen is unrecognised, to back out of wherever we are.

        Returns:
            True on the home screen, False when a blocking dialog was cleared, None when the screen is simply not recognised.
        """
        boxes = [box for box in self.ocr(match=MAIN_SCREEN_LABELS, box='right', log=True) if is_menu_label(box.name)]
        feature_boxes = []
        for feature in [fL.dog_icon, fL.message_icon]:
            if result := self.find_one(feature, vertical_variance=0.002, horizontal_variance=0.002):
                feature_boxes.append(result)
        total = len(boxes) + len(feature_boxes)
        self.log_info(f'is main ocr={len(boxes)} features={len(feature_boxes)} total={total}')
        if total >= 2:
            return True
        # Answer the leave-the-Crew-Deck confirmation rather than pressing Escape at it forever. Both the
        # prompt and a Confirm button have to be present, so an ordinary screen that happens to contain
        # the word "exit" is not mistaken for a dialog. One OCR pass, matched twice in memory.
        centre = self.ocr(box=self.box.center, log=True)
        if self.find_boxes(centre, match=LEAVE_PROMPT) and (confirm := self.find_boxes(centre, match=CONFIRM)):
            self.log_info('answering a leave-screen confirmation')
            self.click(confirm[0], after_sleep=2)
            return False
        if box := self.ocr(box=self.box.bottom, match=MAIN_SCREEN_BLOCKERS, log=True):
            self.click(box, after_sleep=2)
            return False
        if esc:
            self.back(after_sleep=2)
        self.next_frame()
        return None

    def go_home(self, time_out=30):
        """Return to the home screen, preferring the in-game home button.

        One press gets there from anywhere that has the button, instead of unwinding screen by screen with Escape. Falls back to `ensure_main` when the
        button is missing or did not take, so this is never worse than backing out.

        Args:
            time_out: Seconds the fallback gets to reach the home screen.

        Raises:
            Exception: The home screen was not reached, raised by the fallback.
        """
        self.info_set('current_task', 'go_home')
        self.click_relative(*HOME_BUTTON, after_sleep=2)
        # Polled by hand rather than with `wait_until`, which has no gap between checks and would spend the
        # whole window hammering OCR at a screen that cannot change until the next press.
        deadline = time.time() + HOME_BUTTON_TIME_OUT
        while True:
            if self.is_main(esc=False):
                self.log_info('home button worked')
                return
            if time.time() >= deadline:
                break
            self.sleep(HOME_BUTTON_CHECK_INTERVAL)
        # Not an error - the button is not on every screen, and backing out always works. Logged so a
        # run makes it obvious which route was taken rather than leaving the button's usefulness assumed.
        self.log_info('home button did not reach the home screen, backing out with Escape instead')
        self.ensure_main(time_out=time_out)

    def ensure_main(self, recheck_time=1, time_out=30, esc=True):
        """Back out until the home screen is showing.

        Args:
            recheck_time: Passed through to `is_main`.
            time_out: Seconds to keep trying before giving up.
            esc: Send Escape on unrecognised screens.

        Raises:
            Exception: The home screen was not reached within `time_out`.
        """
        self.info_set('current_task', 'go_to_main')
        if not self.wait_until(lambda: self.is_main(recheck_time=recheck_time, esc=esc), time_out=time_out):
            raise Exception('Could not reach the game home screen. Start the bot from the home screen.')

    def wait_pop_up(self, time_out=15, other=None, box=None, count=100):
        """Dismiss reward and notice overlays until none are left.

        Args:
            time_out: Total seconds to keep dismissing.
            other: Extra match patterns to treat as dismissable.
            box: Region to search. Defaults to the bottom half.
            count: Maximum number of overlays to dismiss.
        """
        if box is None:
            box = self.box.bottom
        check = list(POP_UPS)
        if other:
            check += other if isinstance(other, list) else [other]
        deadline = time.time() + time_out
        for _ in range(count):
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            # Each look gets a short timeout of its own rather than the whole remaining budget. Spending
            # the entire budget establishing that no overlay is left is what made this appear to hang for
            # fifteen seconds after the last one was already gone. `time_out` still caps the total.
            found = self.wait_ocr(match=check, box=box, settle_time=POP_UP_SETTLE,
                                  time_out=min(POP_UP_CHECK_TIME_OUT, remaining), raise_if_not_found=False)
            if not found:
                break
            # Overlays that say "click anywhere to exit" mean it. Clicking the instruction itself is the
            # dismissal the screen advertises, and more reliable than Escape, which some of them ignore.
            if clickable := [detected for detected in found if CLICK_ANYWHERE.search(detected.name)]:
                self.click(clickable[0], after_sleep=POP_UP_AFTER_CLICK)
            else:
                self.back(after_sleep=POP_UP_AFTER_CLICK)

    def skip_dialogs(self, end_match, end_box=None, time_out=120, has_dialog=True, raise_if_not_found=True):
        """Click through story dialogue until one of `end_match` appears.

        Args:
            end_match: Patterns that mean the dialogue is over.
            end_box: Region to look for `end_match` in.
            time_out: Seconds to keep skipping.
            has_dialog: Tap the top-right skip affordance when nothing else matched.
            raise_if_not_found: Raise instead of returning when `time_out` is hit.

        Returns:
            The boxes that matched `end_match`, or None when it timed out and `raise_if_not_found` is False.

        Raises:
            Exception: Timed out while `raise_if_not_found` is True.
        """
        self.info_set('current_task', 'skip_dialogs')
        start = time.time()
        while time.time() - start < time_out:
            try:
                boxes = self.ocr()
            except AttributeError:
                self.log_info('capture returned an empty frame, retrying in 3s', notify=False)
                self.sleep(3)
                self.next_frame()
                continue
            if skip := self.find_boxes(boxes, match=SKIP):
                self.click(skip, after_sleep=2)
            elif no_alert := self.find_boxes(boxes, match=DO_NOT_REMIND):
                self.click(no_alert)
                self.sleep(0.2)
                self.click(self.find_boxes(boxes, match=CONFIRM), after_sleep=2)
            elif result := self.find_boxes(boxes, match=end_match, boundary=end_box):
                self.sleep(1)
                return result
            elif self.find_boxes(boxes, match=POP_UPS):
                self.back()
                self.sleep(1)
            else:
                if has_dialog:
                    self.click_relative(0.95, 0.04)
                self.sleep(2)
            self.next_frame()
        if raise_if_not_found:
            raise Exception('Timed out skipping dialogue.')
        return None
