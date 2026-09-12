"""One explicit update lookup with Qt networking; no polling or installation."""

from __future__ import annotations

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout

from app.i18n import tr
from app.utils.updates import LATEST_RELEASE_API, parse_release
from app.version import __version__


class UpdateDialog(QDialog):
    """Network activity exists only during this user-opened dialog's lifetime."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Check for Updates...")
        self.resize(520, 180)
        layout = QVBoxLayout(self)
        self.message = QLabel(tr("正在连接 GitHub 检查更新…", "Connecting to GitHub to check for updates…"))
        self.message.setWordWrap(True)
        self.message.setTextFormat(Qt.TextFormat.PlainText)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.message)
        self.download = QPushButton(tr("打开该版本下载页面", "Open Release Download Page"))
        self.download.hide()
        layout.addWidget(self.download)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._closing = False
        self._timed_out = False
        self._manager = QNetworkAccessManager(self)
        request = QNetworkRequest(QUrl(LATEST_RELEASE_API))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", b"SolarTimeDistanceExplorer-Manual-Update-Check")
        self._reply = self._manager.get(request)
        self._reply.finished.connect(self._finished)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._on_timeout)
        self._timeout.start(10000)

    def _on_timeout(self) -> None:
        self._timed_out = True
        self._reply.abort()

    def _finished(self) -> None:
        self._timeout.stop()
        if self._closing:
            return
        if self._reply.error() != QNetworkReply.NetworkError.NoError:
            reason = tr("连接超时", "Connection timed out") if self._timed_out else self._reply.errorString()
            self.message.setText(tr("网络错误：无法检查更新。\n", "Network error: could not check for updates.\n") + reason)
            return
        try:
            release = parse_release(bytes(self._reply.readAll()))
        except ValueError as exc:
            self.message.setText(tr("检查失败：服务器返回的信息无效。\n", "Update check failed: invalid server response.\n") + str(exc))
            return
        if release.is_newer_than(__version__):
            self.message.setText(tr(
                f"发现新版本 {release.tag}（当前版本 {__version__}）。\n请打开 Release 页面选择适合系统的下载包。",
                f"New version {release.tag} is available (current: {__version__}).\nOpen its Release page to choose a package for your system.",
            ))
            self.download.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(release.url)))
            self.download.show()
        else:
            self.message.setText(tr(f"当前已是最新版（{__version__}）。", f"You are up to date ({__version__})."))

    def done(self, result: int) -> None:
        self._closing = True
        self._timeout.stop()
        if self._reply.isRunning():
            self._reply.abort()
        super().done(result)
