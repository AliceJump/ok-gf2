import re

from .BaseGlobalTask import CONFIRM, SHOP, BaseGlobalTask

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
            'Claim Boundary Push Rewards': True,
        })
        self.config_description.update({
            'Start Loop': 'Opens the Dispatch Room and starts the in-game Loop automation, then waits for it to finish.',
            'Claim Free Packs': 'Claims the shop supply boxes that are currently free.',
            'Claim Boundary Push Rewards': 'Collects the Breakthrough rewards under Commissions.',
        })

    def run(self):
        self.ensure_main(recheck_time=2, time_out=90)
        steps = [
            ('Start Loop', self.start_loop),
            ('Claim Free Packs', self.shopping),
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
