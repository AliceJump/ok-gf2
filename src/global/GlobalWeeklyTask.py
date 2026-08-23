import re

from .BaseGlobalTask import CLAIM_ALL, BaseGlobalTask

# Left rail of Regular Commissions. Peak Value Assessment wraps onto two lines there, so it is matched
# on the distinctive first two words rather than the full name.
PEAK_VALUE = re.compile(r'Peak Value', re.I)

# The flows this task performs: (config key, method, settings text). See `GlobalDailyTask.FLOWS`.
FLOWS = (
    ('Claim Peak Value Rewards', 'claim_peak_value',
     'Collects the rewards from Peak Value Assessment. Does not fight anything.'),
)


class GlobalWeeklyTask(BaseGlobalTask):
    """Weekly modes on the Global client that the in-game Loop does not cover.

    Only the claim side of Peak Value Assessment so far. Boss Fight and Expansion Drills need an English `auto_battle`, which does not exist yet.
    """

    def __init__(self, *args, **kwargs):
        """Build the task and describe it for the sidebar.

        Args:
            *args: Passed to the framework task.
            **kwargs: Passed to the framework task.
        """
        super().__init__(*args, **kwargs)
        self.name = 'Global Weekly'
        self.description = 'Collects the Peak Value Assessment rewards.'
        self.support_schedule_task = True
        self.register_flows(FLOWS)

    def run(self):
        """Run every enabled weekly flow, in the order `FLOWS` lists them."""
        self.run_flows(FLOWS, 'Global Weekly complete.')

    def claim_peak_value(self):
        """Collect the Peak Value Assessment rewards.

        The route in is confirmed, but the reward panel itself has not been captured yet, so the claim is a single best-effort press of a Claim button rather
        than a specific sequence. Running the Extreme Peak stages needs combat handling and is deliberately left out.
        """
        self.info_set('current_task', 'claim_peak_value')
        if not self.open_regular_commissions():
            self.log_info('Could not open Regular Commissions, skipping Peak Value.', notify=True)
            self.go_home()
            return
        if not self.wait_click_ocr(match=PEAK_VALUE, box=self.box.left, time_out=5, after_sleep=2):
            self.log_info('Peak Value Assessment is not available, skipping.', notify=True)
            self.go_home()
            return
        if self.wait_click_ocr(match=CLAIM_ALL, box=self.box.bottom_right, time_out=5, after_sleep=2):
            self.wait_pop_up(time_out=5, count=2)
        else:
            self.log_info('Found no claim button on the Peak Value panel.', notify=True)
        self.go_home()
