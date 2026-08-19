import re

from .BaseGlobalTask import CAMPAIGN, BaseGlobalTask

COMBAT_SIMULATIONS = re.compile(r'Combat Simulations|Combat Sim', re.I)
PEAK_VALUE = re.compile(r'Peak Value', re.I)

# Peak Value Assessment reward panel.
REGULAR_PEAK = re.compile(r'Regular Peak|Regular', re.I)
PERIODIC_REWARD = re.compile(r'Periodic Rewards?|Cycle Rewards?', re.I)
CLAIM_ALL = re.compile(r'Claim All', re.I)


class GlobalWeeklyTask(BaseGlobalTask):
    """Weekly modes on the Global client that the in-game Loop does not cover.

    Only the claim-side of Peak Value Assessment so far. Boss Fight and Expansion Drills need an English `auto_battle`, which does not exist yet.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = 'Global Weekly'
        self.description = 'Collects the Peak Value Assessment periodic rewards.'
        self.support_schedule_task = True
        self.default_config.update({
            'Claim Peak Value Rewards': True,
        })
        self.config_description.update({
            'Claim Peak Value Rewards': 'Collects the periodic rewards from Peak Value Assessment. Does not fight anything.',
        })

    def run(self):
        self.ensure_main(recheck_time=2, time_out=90)
        steps = [
            ('Claim Peak Value Rewards', self.claim_peak_value),
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

    def claim_peak_value(self):
        """Collect the Peak Value Assessment periodic rewards.

        This is the claim half of the mode only. Running the Extreme Peak stages needs combat handling and is deliberately left out.
        """
        self.info_set('current_task', 'claim_peak_value')
        if not self.open_combat_simulations():
            self.log_info('Could not open Combat Simulations, skipping Peak Value.', notify=True)
            self.ensure_main()
            return
        if not self.wait_click_ocr(match=PEAK_VALUE, box=self.box.center, time_out=10, after_sleep=2):
            self.log_info('Peak Value Assessment is not available, skipping.', notify=True)
            self.ensure_main()
            return
        self.wait_click_ocr(match=REGULAR_PEAK, box=self.box.bottom_right, time_out=3, after_sleep=2)
        if reward := self.wait_ocr(match=PERIODIC_REWARD, box=self.box.bottom_left, time_out=3):
            self.click(reward[0], after_sleep=2)
            if self.wait_click_ocr(match=CLAIM_ALL, box=self.box.center, time_out=3, after_sleep=2):
                self.wait_pop_up(time_out=5, count=1)
                self.back(after_sleep=1)
        self.ensure_main()
