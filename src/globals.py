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

    Must be paired with `size_cards_by_height_for_width`, otherwise cards keep reserving height for
    the wrapping that no longer happens and leave a gap under their last row.

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

    original_add_widget = LabelAndWidget.add_widget

    def patched_add_widget(self, widget, stretch=1):
        # Subclasses add their control after __init__ returns, most of them with the default
        # stretch=1, which would split the row evenly and undo the widening. Controls already size
        # themselves through control_width, so they never need stretch.
        original_add_widget(self, widget, 0)

    LabelAndWidget.__init__ = patched_init
    LabelAndWidget.add_widget = patched_add_widget
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


class Globals(QObject):

    def __init__(self, exit_event):
        super().__init__()
        widen_settings_text_column()
        size_cards_by_height_for_width()
        # ok.og.executor.ocr_lib.add_text_fix({"a": "b"})


if __name__ == "__main__":
    glbs = Globals(exit_event=None)
