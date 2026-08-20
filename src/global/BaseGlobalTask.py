import re
import time

from ok import Box
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

# Walking out of the Crew Deck raises a confirmation, and Escape does not dismiss it - it has to be
# answered or the way home is blocked. Deliberately loose, because the exact wording is unconfirmed and
# OCR splits long sentences; `is_main` only acts on it when a Confirm button is on screen too.
LEAVE_PROMPT = re.compile(r'leave|exit|quit', re.I)

# Vertical extent of the bottom navigation bar, as a fraction of frame height.
NAV_STRIP_TOP = 0.86

# Most screens carry a home button in the top-left, immediately right of the Back arrow. It jumps
# straight to the home screen, where backing out has to unwind one screen at a time. Unlabelled, so it
# has to be clicked by position. On the home screen itself that spot is empty, so a stray press is safe.
HOME_BUTTON = (0.076, 0.048)


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
    # Clicking

    @property
    def nav_strip(self):
        """Full-width box covering just the bottom navigation bar.

        Kept full width on purpose. OCR often returns two adjacent nav buttons as a single box (`Voyage Formation`), and clipping horizontally would cut the
        merged label that `click_ocr_word` needs in order to aim. Trimming vertically is free and drops most of the pixels.

        Returns:
            A `Box` spanning the frame width across the nav bar's height.
        """
        return Box(x=0, y=int(self.height * NAV_STRIP_TOP), to_x=self.width, to_y=self.height)

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
        while time.time() < deadline:
            if found := self.ocr(match=match, box=box):
                return found
            self.sleep(min(interval, max(0, deadline - time.time())))
            self.next_frame()
        return None

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Navigation

    def open_regular_commissions(self):
        """Navigate home -> Commissions -> Regular Commissions.

        Commissions is a bottom-nav entry, so it is clicked with `click_ocr_word` - OCR frequently merges it with Platoon next to it. The screen opens on the
        Daily Quests tab, so Regular Commissions has to be selected explicitly.

        Returns:
            True when the Regular Commissions tab opened, False when it could not be reached.
        """
        self.click_ocr_word(COMMISSIONS, box=self.nav_strip, after_sleep=2, raise_if_not_found=True)
        return bool(self.wait_click_ocr(match=REGULAR_COMMISSIONS, box=self.box.top, time_out=10, after_sleep=2))

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
        boxes = self.ocr(match=MAIN_SCREEN_LABELS, box='right', log=True)
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
        if self.wait_until(lambda: self.is_main(esc=False), time_out=6):
            return
        self.log_info('home button did not land on the home screen, backing out instead')
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
            remaining = int(deadline - time.time())
            if remaining <= 0:
                break
            found = self.wait_ocr(match=check, box=box, settle_time=2, time_out=remaining, raise_if_not_found=False)
            if not found:
                break
            # Overlays that say "click anywhere to exit" mean it. Clicking the instruction itself is the
            # dismissal the screen advertises, and more reliable than Escape, which some of them ignore.
            if clickable := [detected for detected in found if CLICK_ANYWHERE.search(detected.name)]:
                self.click(clickable[0], after_sleep=3)
            else:
                self.back(after_sleep=3)

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
