import re

from src.tasks.BaseGfTask import map_re

from .BaseGlobalTask import CONFIRM, SHOP, BaseGlobalTask

# Event. The banner sits at a fixed spot in the top-left of the home screen. When a second event is
# running its banner appears directly below this one - not supported, since two at once is rare.
EVENT_BANNER = (0.104, 0.157)
EVENT_PAGE = re.compile(r'Challenge|Supply|Story', re.I)
SUPPLY = re.compile(r'\bSupply\b', re.I)
# Anchored so it cannot match the "Auto Mode Preparation" dialog title that follows it.
AUTO = re.compile(r'^Auto$', re.I)
AUTO_DIALOG = re.compile(r'Number of Auto Battles', re.I)
ITEMS_OBTAINED = re.compile(r'Items Obtained', re.I)

# Sets the battle count to the most the remaining Expenditure allows. Unlabelled, so clicked by position.
MAX_BATTLES = (0.653, 0.518)

# Stage nodes sit in a horizontal band across the middle of the Supply map. Scanning a band rather than
# the whole frame keeps the repeated scroll-and-look cheap.
STAGE_BAND = (0.0, 0.38, 1.0, 0.62)
STAGE_SWIPES = 5
EVENT_BATTLE_TIME_OUT = 900

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

# Shop. The supply boxes sit along the bottom-right of the landing page, each with its price where a
# button would be - the claimable ones read "Free". Matching on the price rather than on a box name
# covers the daily and the weekly box without hardcoding either, and a box on cooldown shows a timer
# instead, so it simply stops matching once claimed.
FREE = re.compile(r'^Free$', re.I)
PURCHASE = re.compile(r'Purchase', re.I)

# Upper bound on free boxes to claim in one run. The loop normally ends when nothing reads Free any
# more; this only stops it spinning if a dialog ever leaves "Free" on screen.
MAX_FREE_BOXES = 3

# Regular Commissions -> Boundary Push, which opens on its Breakthrough tab. The rewards sit behind
# the Crystal Collection button in the bottom-right. Matched on the first word alone because the
# button wraps onto two lines, which OCR usually returns as two separate boxes.
BOUNDARY_PUSH = re.compile(r'Boundary Push', re.I)
CRYSTAL_COLLECTION = re.compile(r'Crystal', re.I)
CLAIM_ALL = re.compile(r'Claim All', re.I)


class GlobalDailyTask(BaseGlobalTask):
    """Daily upkeep on the Global client.

    Global ships its own Loop automation, so this task mostly starts that and then picks up the handful of things Loop does not cover.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = 'Global Daily'
        self.description = 'Starts the in-game Loop, claims free shop packs, and collects Boundary Push rewards.'
        self.support_schedule_task = True
        self.default_config.update({
            'Start Loop': True,
            'Claim Free Packs': True,
            'Run Event Supply': True,
            'Claim Boundary Push Rewards': True,
        })
        self.config_description.update({
            'Start Loop': 'Opens the Dispatch Room and starts the in-game Loop automation, then waits for it to finish.',
            'Claim Free Packs': 'Claims the shop supply boxes that are currently free.',
            'Run Event Supply': 'Auto-battles the last Supply stage of the current event, spending as much Expenditure as it can.',
            'Claim Boundary Push Rewards': 'Collects the Breakthrough rewards under Commissions.',
        })

    def run(self):
        self.ensure_main(recheck_time=2, time_out=90)
        steps = [
            ('Start Loop', self.start_loop),
            ('Claim Free Packs', self.shopping),
            ('Run Event Supply', self.run_event_supply),
            ('Claim Boundary Push Rewards', self.claim_boundary_push),
        ]
        for key, func in steps:
            if self.config.get(key):
                func()
        self.log_info('Global Daily complete.', notify=True)

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Loop automation

    def start_loop(self):
        """Open the Dispatch Room, start the in-game Loop, and wait for it to report back.

        The Loop runs for minutes at a time against a static screen, so the wait is a throttled poll rather than a tight one. Anything the Loop covers is
        deliberately not automated here.
        """
        self.info_set('current_task', 'start_loop')
        self.click_relative(*LOOP_ICON, after_sleep=3)
        if not self.wait_ocr(match=LOOP_SCREEN, box=self.box.left, time_out=10, log=True):
            self.log_info('Clicking the Loop icon did not open the Dispatch Room, skipping.', notify=True)
            self.go_home()
            return
        if not self.wait_click_ocr(match=START_LOOP, box=self.box.bottom_left, time_out=10, after_sleep=2):
            self.log_info('Could not find the Start Loop button, skipping.', notify=True)
            self.go_home()
            return
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
        """Open the shop and claim every supply box that is currently free."""
        self.info_set('current_task', 'shopping')
        self.click_ocr_word(SHOP, box=self.box.right, after_sleep=2, raise_if_not_found=True)
        claimed = 0
        for _ in range(MAX_FREE_BOXES):
            if not self.claim_free_box():
                break
            claimed += 1
        self.log_info(f'claimed {claimed} free supply box(es)')
        self.go_home()

    def claim_free_box(self):
        """Claim one supply box priced Free, if there is one.

        Returns:
            True when a box was claimed, False when none was free or the purchase did not go through.
        """
        free = self.wait_ocr(match=FREE, box=self.box.bottom_right, time_out=3)
        if not free:
            return False
        self.click(free[0], after_sleep=1.5)
        if not self.wait_click_ocr(match=PURCHASE, box=self.box.bottom, time_out=5, after_sleep=1.5):
            self.log_info('opened a free supply box but found no Purchase button, backing out.')
            self.back(after_sleep=1)
            return False
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
        self.click_relative(*EVENT_BANNER, after_sleep=3)
        if not self.wait_ocr(match=EVENT_PAGE, box=self.box.bottom_right, time_out=10, log=True):
            self.log_info('No event banner on the home screen, skipping.', notify=True)
            self.go_home()
            return
        if not self.wait_click_ocr(match=SUPPLY, box=self.box.bottom_right, time_out=5, after_sleep=3):
            self.log_info('This event has no Supply mode, skipping.', notify=True)
            self.go_home()
            return
        stage = self.last_supply_stage()
        if not stage:
            self.log_info('Found no Supply stages on the map, skipping.', notify=True)
            self.go_home()
            return
        self.log_info(f'running event supply stage {stage.name}')
        self.click(stage, after_sleep=2)
        if not self.wait_click_ocr(match=AUTO, box=self.box.bottom_right, time_out=5, after_sleep=2):
            self.log_info('Found no Auto button on the stage panel, skipping.', notify=True)
            self.go_home()
            return
        if not self.wait_ocr(match=AUTO_DIALOG, box=self.box.center, time_out=5):
            self.log_info('The Auto Mode dialog did not open, skipping.', notify=True)
            self.go_home()
            return
        # Take the maximum the remaining Expenditure allows. Missing this button costs a smaller run,
        # not a wrong one, so it is not worth failing over.
        self.click_relative(*MAX_BATTLES, after_sleep=1)
        if not self.wait_click_ocr(match=CONFIRM, box=self.box.center, time_out=5, after_sleep=3):
            self.log_info('Could not confirm the auto battles, skipping.', notify=True)
            self.go_home()
            return
        if self.poll_ocr(ITEMS_OBTAINED, box=self.box.top, time_out=EVENT_BATTLE_TIME_OUT, interval=5):
            self.wait_pop_up(time_out=10, count=2)
        else:
            self.log_info(f'Auto battles did not finish within {EVENT_BATTLE_TIME_OUT}s.', notify=True)
        self.go_home()

    def last_supply_stage(self):
        """Scroll the Supply map to its right end and return the furthest-right stage node.

        The map opens part way along, and the last stage is the one worth running. Swiping stops early once a scroll reveals nothing new, so a short map
        costs no extra passes.

        Returns:
            The rightmost stage `Box`, or None when the map showed no stage codes.
        """
        band = self.box_of_screen(*STAGE_BAND)
        previous = None
        for _ in range(STAGE_SWIPES):
            stages = self.ocr(match=map_re, box=band)
            names = tuple(sorted(box.name for box in stages))
            if names and names == previous:
                break
            previous = names
            self.swipe_relative(0.8, 0.5, 0.2, 0.5, duration=0.5, settle_time=1)
            self.next_frame()
        stages = self.ocr(match=map_re, box=band, log=True)
        return max(stages, key=lambda box: box.x) if stages else None

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Boundary Push

    def claim_boundary_push(self):
        """Collect the Breakthrough rewards under Regular Commissions -> Boundary Push."""
        self.info_set('current_task', 'claim_boundary_push')
        if not self.open_regular_commissions():
            self.log_info('Could not open Regular Commissions, skipping Boundary Push.', notify=True)
            self.go_home()
            return
        if not self.wait_click_ocr(match=BOUNDARY_PUSH, box=self.box.left, time_out=5, after_sleep=3):
            self.log_info('Boundary Push is not available, skipping.', notify=True)
            self.go_home()
            return
        if not self.wait_click_ocr(match=CRYSTAL_COLLECTION, box=self.box.bottom_right, time_out=5, after_sleep=2):
            self.log_info('Nothing to collect in Crystal Collection, skipping.', notify=True)
            self.go_home()
            return
        if self.wait_click_ocr(match=CLAIM_ALL, box=self.box.bottom_right, time_out=5, after_sleep=2):
            self.wait_pop_up(time_out=5, count=2)
        self.go_home()
