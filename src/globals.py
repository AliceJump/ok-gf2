import os

from PySide6.QtCore import QObject

from ok import Logger

logger = Logger.get_logger(__name__)

_settings_layout_patched = False


def widen_settings_text_column():
    """Let option labels and descriptions use the full width of a settings row.

    ok-script lays each row out as `[text column][stretch spacer][control]` but gives the text column
    no stretch, so the empty spacer absorbs every spare pixel. Descriptions then wrap far earlier than
    they need to while most of the row sits empty. Removing the spacer and stretching the text column
    instead gives it roughly 60% more width. This matters much more in English than in Chinese, which
    is dense enough that the early wrapping is hard to notice.

    The controls are unaffected because they set their own fixed width via `control_width`.

    This reaches into framework internals, so it is written to fail quietly. If a future ok-script
    release fixes the layout, no spacer is found and the patch does nothing.
    """
    global _settings_layout_patched
    if _settings_layout_patched:
        return
    if os.environ.get('OK_GF2_NO_LAYOUT_PATCH'):
        logger.info('OK_GF2_NO_LAYOUT_PATCH set, leaving the stock layout alone')
        return
    try:
        from ok.gui.tasks.LabelAndWidget import LabelAndWidget
    except ImportError:
        logger.warning('could not import LabelAndWidget, skipping settings layout patch')
        return

    original_init = LabelAndWidget.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            for i in reversed(range(self.layout.count())):
                if self.layout.itemAt(i).spacerItem() is not None:
                    self.layout.takeAt(i)
                    break
            self.layout.setStretch(0, 1)
        except Exception as e:
            logger.warning(f'settings layout patch failed for this row: {e}')

    LabelAndWidget.__init__ = patched_init
    _settings_layout_patched = True
    logger.info('settings text column widened')


def _content_height(card):
    """Measure a card's content at the width it is actually laid out at.

    Word-wrapped labels report height through `heightForWidth`, not `sizeHint`, so a layout holding
    them cannot describe its own height with `sizeHint` alone. Asking at the real width is what stops
    a card reserving space its content never uses.

    Args:
        card: The `ExpandSettingCard` being measured.

    Returns:
        The content height in pixels, falling back to the size hint when no sensible width is known.
    """
    layout = card.viewLayout
    width = card.view.width()
    if width > 200 and layout.hasHeightForWidth():
        height = layout.heightForWidth(width)
        if height > 0:
            return height
    return layout.sizeHint().height()


def size_cards_by_height_for_width():
    """Size expandable cards from real content height rather than the size hint.

    qfluentwidgets derives both the expanded height and the collapse arithmetic from
    `viewLayout.sizeHint().height()`. Once the text column is widened that estimate no longer matches
    the laid-out height, so the card reserves too much and leaves a gap under its last row.

    The width guard matters: during early layout the view briefly reports a nonsense width, and
    asking `heightForWidth` there returns a wildly inflated height.
    """
    if os.environ.get('OK_GF2_NO_LAYOUT_PATCH'):
        return
    try:
        from qfluentwidgets import ExpandSettingCard
    except ImportError:
        logger.warning('could not import ExpandSettingCard, skipping height-for-width sizing')
        return

    def adjust_view_size(self):
        height = _content_height(self)
        self.spaceWidget.setFixedHeight(height)
        if self.isExpand:
            self.setFixedHeight(self.card.height() + height)

    def on_expand_value_changed(self):
        content = _content_height(self)
        top = self.viewportMargins().top()
        self.setFixedHeight(max(top + content - self.verticalScrollBar().value(), top))

    ExpandSettingCard._adjustViewSize = adjust_view_size
    ExpandSettingCard._onExpandValueChanged = on_expand_value_changed
    logger.info('expandable cards sized by height-for-width')


def fix_collapsed_card_height():
    """Snap an expandable card back to its header height once the collapse animation ends.

    qfluentwidgets collapses a card by animating its scroll position and deriving the height from
    `header + content - scrollValue`. That only lands on the header height when the content size hint
    matches the laid-out size. Widening the text column breaks that assumption, so a card collapsed
    after scrolling keeps several hundred pixels of dead space below it.

    Forcing the height when the animation finishes leaves the animation itself intact and makes the
    end state correct regardless of what the arithmetic produced.
    """
    if os.environ.get('OK_GF2_NO_LAYOUT_PATCH'):
        return
    try:
        from qfluentwidgets import ExpandSettingCard
    except ImportError:
        logger.warning('could not import ExpandSettingCard, skipping collapse height fix')
        return

    original_init = ExpandSettingCard.__init__

    def patched_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        try:
            self.expandAni.finished.connect(lambda: _snap_collapsed(self))
        except Exception as e:
            logger.warning(f'could not hook collapse animation: {e}')

    ExpandSettingCard.__init__ = patched_init


def _snap_collapsed(card):
    """Force a collapsed card down to its header height.

    Args:
        card: The `ExpandSettingCard` whose expand animation just finished.
    """
    try:
        if not card.isExpand:
            card.setFixedHeight(card.card.height())
    except Exception as e:
        logger.warning(f'collapse height fix failed: {e}')


class Globals(QObject):

    def __init__(self, exit_event):
        super().__init__()
        widen_settings_text_column()
        size_cards_by_height_for_width()
        fix_collapsed_card_height()
        # ok.og.executor.ocr_lib.add_text_fix({"a": "b"})


if __name__ == "__main__":
    glbs = Globals(exit_event=None)
