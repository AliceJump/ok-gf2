import re

from ok import Logger

from .BaseGlobalTask import BaseGlobalTask

logger = Logger.get_logger(__name__)

# Home screen entry points. Scoped to a screen region at each call site rather than anchored, so a label OCR merged with its neighbour still
# matches and click_ocr_word can aim inside the merged box.
CREW_DECK = re.compile(r'Public Area|Crew Deck', re.I)
SHOP = re.compile(r'\bShop\b', re.I)
COMMISSIONS = re.compile(r'Commissions', re.I)

# In-game Loop automation. The client runs the dailies itself once this is started, which is why the
# Global task set is so much smaller than the CN one.
AUTO_LOOP = re.compile(r'Auto\s*Loop', re.I)
START_LOOP = re.compile(r'Start\s*Loop', re.I)
LOOP_ENDED = re.compile(r'Loop\s*(Ended|Complete|Finished)|End of Loop', re.I)
CONFIRM = re.compile(r'Confirm', re.I)

# Shop. Free packs live under the quality tab, split across a periodic and a standing list.
QUALITY = re.compile(r'Quality', re.I)
PACK_TABS = [re.compile(r'Periodic Pack', re.I), re.compile(r'Standard Package', re.I)]
PREMIUM_TABS = [re.compile(r'Time-Limited Package', re.I), re.compile(r'Premium Pack', re.I)]
FREE = re.compile(r'^Free$', re.I)
PURCHASE = re.compile(r'Purchase|Buy', re.I)

# Wishlist sub-shops, in the order they appear down the shop's left rail.
WISHLIST_SHOPS = [
    re.compile(r'Furniture', re.I),
    re.compile(r'Platoon Shop', re.I),
    re.compile(r'Dispatch', re.I),
    re.compile(r'Battlelog', re.I),
    re.compile(r'Neural Integration', re.I),
    re.compile(r'Growth Stack', re.I),
]

# Commissions -> Boundary Push -> Breakthrough.
BOUNDARY_PUSH = re.compile(r'Boundary Push', re.I)
BREAKTHROUGH = re.compile(r'Breakthrough', re.I)
COLLECT = re.compile(r'Collect|Claim', re.I)
DISPATCH = re.compile(r'Dispatch', re.I)


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
            'Buy Wishlist Items': False,
            'Claim Boundary Push Rewards': True,
        })
        self.config_description.update({
            'Start Loop': 'Opens the Crew Deck and starts the in-game Loop automation, then waits for it to finish.',
            'Claim Free Packs': 'Claims the free periodic and time-limited shop packs.',
            'Buy Wishlist Items': 'Runs the bulk-buy button in each sub-shop that has one.',
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
        """Open the Crew Deck, start the in-game Loop, and wait for it to report back.

        The Loop can run for a long time, so the wait is generous. Anything it covers is deliberately not automated here.
        """
        self.info_set('current_task', 'start_loop')
        self.click_ocr_word(CREW_DECK, box=self.box.right, after_sleep=3, raise_if_not_found=True)
        if not self.wait_click_ocr(match=AUTO_LOOP, box=self.box.bottom_left, time_out=10, after_sleep=2):
            self.log_info('Could not find the Loop entry point, skipping.', notify=True)
            self.ensure_main()
            return
        if not self.wait_click_ocr(match=START_LOOP, box=self.box.bottom_left, time_out=10, after_sleep=2):
            self.log_info('Could not find the Start Loop button, skipping.', notify=True)
            self.ensure_main()
            return
        self.wait_click_ocr(match=CONFIRM, box=self.box.center, time_out=10, settle_time=2, after_sleep=2)
        self.log_info('Loop started, waiting for it to finish.', notify=True)
        if not self.wait_click_ocr(match=LOOP_ENDED, box=self.box.top, time_out=600, after_sleep=2, log=True):
            self.log_info('Loop did not report finishing within 10 minutes.', notify=True)
            self.ensure_main()
            return
        self.wait_click_ocr(match=CONFIRM, box=self.box.bottom, time_out=10, settle_time=2, after_sleep=2)
        self.ensure_main()

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Shop

    def shopping(self):
        """Claim the free packs, and optionally run each sub-shop's bulk-buy button."""
        self.info_set('current_task', 'shopping')
        self.click_ocr_word(SHOP, box=self.box.right, after_sleep=1.5, raise_if_not_found=True)
        self.wait_click_ocr(match=QUALITY, box=self.box.top_left, after_sleep=1, raise_if_not_found=True)
        self.claim_free_pack(PACK_TABS)
        self.claim_free_pack(PREMIUM_TABS)
        if self.config.get('Buy Wishlist Items'):
            self.buy_wishlist()
        self.ensure_main()

    def claim_free_pack(self, tabs):
        """Open a pack tab and take whatever is free on it.

        Args:
            tabs: Match patterns for the tab to open. The first one present wins.
        """
        if not self.wait_click_ocr(match=tabs, box=self.box.top, time_out=3, after_sleep=1):
            return
        if not self.wait_click_ocr(match=FREE, time_out=2, after_sleep=0.5):
            return
        self.log_info('found a free pack to claim')
        if self.wait_click_ocr(match=PURCHASE, box=self.box.bottom, time_out=5, after_sleep=1.5):
            self.wait_pop_up(time_out=5, count=1)
            self.back(after_sleep=1)

    def buy_wishlist(self):
        """Run the bulk-buy button in each sub-shop that offers one. Sub-shops without one are skipped."""
        self.info_set('current_task', 'buy_wishlist')
        for shop in WISHLIST_SHOPS:
            if not self.wait_click_ocr(match=shop, time_out=2, after_sleep=1):
                continue
            if not self.wait_click_ocr(match=PURCHASE, box=self.box.bottom_right, time_out=2, after_sleep=1):
                continue
            if self.wait_click_ocr(match=CONFIRM, time_out=2, after_sleep=1):
                self.wait_pop_up(time_out=5, count=1)

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Boundary Push

    def claim_boundary_push(self):
        """Collect the Breakthrough rewards under Commissions -> Boundary Push."""
        self.info_set('current_task', 'claim_boundary_push')
        self.click_ocr_word(COMMISSIONS, box=self.box.bottom, after_sleep=2, raise_if_not_found=True)
        if not self.wait_click_ocr(match=BOUNDARY_PUSH, box=self.box.top_right, time_out=5, after_sleep=3):
            self.log_info('Boundary Push is not available, skipping.', notify=True)
            self.ensure_main()
            return
        self.wait_click_ocr(match=BREAKTHROUGH, box=self.box.top, time_out=5, after_sleep=2)
        for match in (COLLECT, DISPATCH):
            if self.wait_click_ocr(match=match, box=self.box.bottom_right, time_out=3, after_sleep=2):
                self.wait_pop_up(time_out=5, count=1)
        self.ensure_main()
