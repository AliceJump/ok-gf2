import re

from ok import Logger

from .BaseGlobalTask import BaseGlobalTask

logger = Logger.get_logger(__name__)

# Campaign -> Combat Simulations is the hub all three weekly modes hang off.
CAMPAIGN = re.compile(r'Campaign', re.I)
COMBAT_SIMULATIONS = re.compile(r'Combat Simulations|Combat Sim', re.I)

BOSS_FIGHT = re.compile(r'Boss Fight', re.I)
PEAK_VALUE = re.compile(r'Peak Value', re.I)
EXPANSION_DRILLS = re.compile(r'Expansion Drills', re.I)

# Peak Value Assessment reward panel.
REGULAR_PEAK = re.compile(r'Regular Peak|Regular', re.I)
PERIODIC_REWARD = re.compile(r'Periodic Rewards?|Cycle Rewards?', re.I)
CLAIM_ALL = re.compile(r'Claim All', re.I)


class GlobalWeeklyTask(BaseGlobalTask):
    """Weekly modes on the Global client that the in-game Loop does not cover."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = 'Global Weekly'
        self.description = 'Claims Peak Value Assessment rewards. Boss Fight and Expansion Drills need the combat layer.'
        self.support_schedule_task = True
        self.default_config.update({
            'Claim Peak Value Rewards': True,
            'Boss Fight': False,
            'Expansion Drills': False,
        })
        self.config_description.update({
            'Claim Peak Value Rewards': 'Collects the periodic rewards from Peak Value Assessment. Does not fight anything.',
            'Boss Fight': 'Not usable yet. Needs the English combat handling, which is still being built.',
            'Expansion Drills': 'Not usable yet. Needs the English combat handling, which is still being built.',
        })

    def run(self):
        self.ensure_main(recheck_time=2, time_out=90)
        steps = [
            ('Claim Peak Value Rewards', self.claim_peak_value),
            ('Boss Fight', self.boss_fight),
            ('Expansion Drills', self.expansion_drills),
        ]
        for key, func in steps:
            if self.config.get(key):
                func()
        self.log_info('Global Weekly complete.', notify=True)

    def open_combat_simulations(self):
        """Navigate home -> Campaign -> Combat Simulations.

        Returns:
            True when Combat Simulations opened, False when it could not be reached.
        """
        self.wait_click_ocr(match=CAMPAIGN, box=self.box.top_right, after_sleep=1, raise_if_not_found=True)
        return bool(self.wait_click_ocr(match=COMBAT_SIMULATIONS, box=self.box.top_right, time_out=10, after_sleep=2))

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Peak Value Assessment

    def claim_peak_value(self):
        """Collect the Peak Value Assessment periodic rewards.

        This is the claim half of the mode only. Running the Extreme Peak stages needs combat handling and is deliberately left out.
        """
        self.info_set('current_task', 'claim_peak_value')
        if not self.open_combat_simulations():
            self.log_info('Could not open Combat Simulations, skipping Peak Value.', notify=True)
            self.ensure_main()
            return
        if not self.wait_click_ocr(match=PEAK_VALUE, time_out=10, after_sleep=2):
            self.log_info('Peak Value Assessment is not available, skipping.', notify=True)
            self.ensure_main()
            return
        self.wait_click_ocr(match=REGULAR_PEAK, box=self.box.bottom_right, time_out=3, after_sleep=2)
        if reward := self.wait_ocr(match=PERIODIC_REWARD, box=self.box.bottom_left, time_out=3):
            self.click(reward[0], after_sleep=2)
            if self.wait_click_ocr(match=CLAIM_ALL, time_out=3, after_sleep=2):
                self.wait_pop_up(count=1)
                self.back(after_sleep=1)
        self.ensure_main()

    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # //////////////////////////////////////////////////////////////////////////////////////////////////
    # Modes still waiting on the English combat layer

    def boss_fight(self):
        """Placeholder. Boss Fight needs an English `fast_combat`, which is not written yet."""
        self.log_info('Boss Fight is not implemented for the Global client yet.', notify=True)

    def expansion_drills(self):
        """Placeholder. Expansion Drills needs an English `auto_battle`, which is not written yet."""
        self.log_info('Expansion Drills is not implemented for the Global client yet.', notify=True)
