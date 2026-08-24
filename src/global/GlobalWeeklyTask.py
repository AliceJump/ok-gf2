import re

from .BaseGlobalTask import CLAIM_ALL, PROCEED, BaseGlobalTask

# Left rail of Regular Commissions. Peak Value Assessment wraps onto two lines there, so it is matched
# on the distinctive first two words rather than the full name.
PEAK_VALUE = re.compile(r'Peak Value', re.I)

# The card's reward tally, "Rewards" over an "n of m". Anchored to the whole word because the same card
# carries "Rewards Reset In 6 days 11 hours" in its top-right corner - an unanchored pattern matches that
# heading just as well, and whichever OCR returned first would decide which numbers got read.
REWARDS = re.compile(r'^Rewards$', re.I)

# The reward popup on the Peak Value screen. It opens by itself the first time the screen is reached each
# week, so this is normally only needed when that has already happened and the popup was closed without
# claiming - after which it does not open itself again. The button wraps onto two lines that OCR splits, so
# it is matched on its first word, and looked for in the bottom left, where the popup's own centred title
# of the same name cannot be mistaken for it.
PERIODIC_RETURNS = re.compile(r'Periodic', re.I)
# How long to let the popup open on its own before going to the button for it.
PERIODIC_POPUP_TIME_OUT = 5

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

        Selecting the mode in the left rail only brings up its card - the rewards are two screens further in, behind the card's own Proceed and the popup
        that follows it. An earlier version looked for a Claim All on the card itself and reported finding none, which read as there being nothing to claim
        rather than as never having gone to look.

        Running the Extreme Peak stages needs combat handling and is deliberately left out.
        """
        self.info_set('current_task', 'claim_peak_value')
        if not self.open_regular_commissions():
            return self.stop_flow('Could not open Regular Commissions, skipping Peak Value.')
        if not self.wait_click_ocr(match=PEAK_VALUE, box=self.box.left, time_out=5, after_sleep=2):
            return self.stop_flow('Peak Value Assessment is not available, skipping.')
        # One read of the card, used for both the tally and the Proceed below it. Nothing is clicked
        # between them, so it is the same pixels either way.
        card = self.ocr(log=True)
        rewards = self.read_counter_under(REWARDS, boxes=card)
        if rewards is None:
            # Said out loud rather than passed over, so a failed read does not get reported as a game state.
            self.log_info('Could not read the Peak Value reward tally, so going on to look.')
            self.dump_screen('peak_value_rewards_unreadable')
        elif rewards[0] >= rewards[1]:
            return self.stop_flow(f'Peak Value rewards are already at {rewards[0]}/{rewards[1]}, nothing to collect.')
        # Extreme Peak sits directly below with an identical Proceed, so the card is named rather than the
        # button clicked by whichever OCR returned first.
        if not self.click_card_button(PEAK_VALUE, PROCEED, after_sleep=3, boxes=card):
            return self.stop_flow('Found no Peak Value card to open, skipping.', dump='peak_value_no_card')
        if not self.open_periodic_returns():
            return self.stop_flow('No Periodic Returns rewards to claim.', dump='peak_value_no_returns')
        if self.wait_click_ocr(match=CLAIM_ALL, box=self.box.bottom_right, time_out=5, after_sleep=2):
            self.wait_pop_up(time_out=5, count=2)
        else:
            self.log_info('The Periodic Returns popup is open but carries no Claim All.', notify=True)
        self.go_home()

    def open_periodic_returns(self):
        """Get the Periodic Returns popup on screen.

        It opens by itself the first time the Peak Value screen is reached in a week. Once that has happened it does not open itself again, even when the
        rewards were never claimed, so a run that finds no popup goes to the button in the bottom left for it rather than concluding there is nothing there.

        Returns:
            True once the popup is up.
        """
        if self.wait_ocr(match=CLAIM_ALL, box=self.box.bottom_right, time_out=PERIODIC_POPUP_TIME_OUT):
            return True
        self.log_info('The Periodic Returns popup did not open itself, opening it from the button.')
        if not self.wait_click_ocr(match=PERIODIC_RETURNS, box=self.box.bottom_left, time_out=5, after_sleep=2):
            return False
        return bool(self.wait_ocr(match=CLAIM_ALL, box=self.box.bottom_right, time_out=PERIODIC_POPUP_TIME_OUT))
