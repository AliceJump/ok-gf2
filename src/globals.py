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


class Globals(QObject):

    def __init__(self, exit_event):
        super().__init__()
        widen_settings_text_column()
        # ok.og.executor.ocr_lib.add_text_fix({"a": "b"})


if __name__ == "__main__":
    glbs = Globals(exit_event=None)
