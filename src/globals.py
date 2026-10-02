from ok import Logger
from PySide6.QtCore import QObject

logger = Logger.get_logger(__name__)


class Globals(QObject):
    def __init__(self, exit_event):
        super().__init__()
        # ok.og.executor.ocr_lib.add_text_fix({"a": "b"})


if __name__ == "__main__":
    glbs = Globals(exit_event=None)
