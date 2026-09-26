"""Important notices shown at startup and available from the navigation tab."""

from ok.gui.tasks.ConfigCard import og
from ok.gui.widget.CustomTab import CustomTab
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    FluentIcon,
    MessageBoxBase,
    NavigationItemPosition,
    PushButton,
    SubtitleLabel,
)

from src.notices import NOTICES, unread_notices
from src.notices.store import load_read_ids, mark_read


class ImportantNoticesTab(CustomTab):
    def __init__(self):
        super().__init__()
        self._prompted = False
        for notice in NOTICES:
            if not notice.active:
                continue
            content = QWidget(self)
            layout = QVBoxLayout(content)
            task = BodyLabel(og.app.tr("受影响任务：{task}").format(task=og.app.tr(notice.task)), content)
            solution = BodyLabel(og.app.tr("解决方法：{solution}").format(solution=og.app.tr(notice.solution)), content)
            solution.setWordWrap(True)
            layout.addWidget(task)
            layout.addWidget(solution)
            link_button = PushButton(og.app.tr("打开链接"), content)
            link_button.clicked.connect(lambda checked=False, url=notice.url: QDesktopServices.openUrl(QUrl(url)))
            layout.addWidget(link_button)
            self.add_card(og.app.tr(notice.title), content)
        QTimer.singleShot(4500, self, self._show_unread_notices)

    @property
    def name(self):
        # MainWindow 会对 tab 的 name 统一调用 self.app.tr(name)（ok-script 2.0.5
        # ok/ui/qt/MainWindow.py L136/L179），这里必须返回源 key（"重要提醒"）而非已翻译文本，
        # 否则会对翻译结果二次 tr()，把翻译值当作待翻译字符串收集进 ok.po。
        return "重要提醒"

    @property
    def position(self):
        return NavigationItemPosition.TOP

    @property
    def add_after_default_tabs(self):
        return False

    @property
    def icon(self):
        return FluentIcon.INFO

    def _show_unread_notices(self):
        if self._prompted:
            return
        self._prompted = True
        notices = unread_notices(load_read_ids())
        if not notices:
            return
        dialog = MessageBoxBase(self.window())
        dialog.viewLayout.addWidget(SubtitleLabel(og.app.tr("重要提醒"), dialog))
        for notice in notices:
            content = BodyLabel(
                og.app.tr(notice.title) + "\n"
                + og.app.tr("受影响任务：{task}").format(task=og.app.tr(notice.task)) + "\n"
                + og.app.tr("解决方法：{solution}").format(solution=og.app.tr(notice.solution)), dialog
            )
            content.setWordWrap(True)
            dialog.viewLayout.addWidget(content)
            details_button = PushButton(og.app.tr("查看详情"), dialog)
            details_button.clicked.connect(
                lambda checked=False, url=notice.url: QDesktopServices.openUrl(QUrl(url))
            )
            dialog.viewLayout.addWidget(details_button)
        dialog.yesButton.setText(og.app.tr("不再提示"))
        dialog.cancelButton.setText(og.app.tr("关闭"))
        dialog.accepted.connect(lambda: self._acknowledge(notices))
        dialog.exec()

    def _acknowledge(self, notices):
        for notice in notices:
            mark_read(notice.id)
