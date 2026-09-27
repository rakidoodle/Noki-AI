"""Noki AI: a small native desktop home for the existing agent."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QFont, QFontDatabase, QIcon, QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

from .attachments import Attachment, load_attachment
from .settings import AppPreferences, DEFAULT_MODEL, SettingsError, SettingsStore
from .worker import ApprovalRequest, ChatWorker

ASSETS = Path(__file__).parent / "assets"
DONATION_URL = "https://www.paypal.com/paypalme/ruffytrinidad"

STYLE = """
QMainWindow, QDialog, QWidget#root { background: #f6f3eb; color: #283d3a; }
QWidget { font-family: 'Bricolage Grotesque'; font-size: 14px; color: #283d3a; }
QFrame#sidebar { background: #e6ebe2; border-right: 1px solid #d5ded1; }
QFrame#messageAssistant { background: #fffdf8; border: 1px solid #e7e1d4; border-radius: 17px; }
QFrame#messageUser { background: #e0eaf0; border: 1px solid #cbdbe3; border-radius: 17px; }
QFrame#composer { background: #fffdf8; border: 1px solid #d7d1c5; border-radius: 18px; }
QFrame#attachmentChip { background: #e6ebe2; border: 1px solid #cbd8ca; border-radius: 10px; }
QFrame#photoCard { background: #fffdf8; border: 1px solid #e7e1d4; border-radius: 18px; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QPlainTextEdit { border: none; background: transparent; selection-background-color: #b8d3ee; }
QLineEdit, QComboBox { background: #fffdf8; border: 1px solid #cfcabd; border-radius: 9px; padding: 9px 11px; min-height: 21px; }
QComboBox { padding-right: 36px; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 32px; border: none; background: transparent; border-top-right-radius: 9px; border-bottom-right-radius: 9px; }
QComboBox::down-arrow { image: url('__ASSETS__/chevron.svg'); width: 12px; height: 8px; }
QComboBox QAbstractItemView { background: #fffdf8; color: #283d3a; selection-background-color: #dce7dc; selection-color: #244a42; border: 1px solid #cfcabd; outline: none; }
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus { border-color: #36647a; }
QPushButton { background: #fffdf8; border: 1px solid #cdc8bd; border-radius: 10px; padding: 10px 14px; font-weight: 600; }
QPushButton:hover { background: #f3efe5; border-color: #9c9b91; }
QPushButton:disabled { color: #8b918e; background: #eeece6; border-color: #e0ddd4; }
QPushButton#primary { background: #36647a; color: white; border-color: #36647a; }
QPushButton#primary:hover { background: #284e62; }
QPushButton#primary:disabled { background: #a5b9c8; border-color: #a5b9c8; }
QPushButton#quiet { background: transparent; border-color: transparent; text-align: left; }
QPushButton#quiet:hover { background: #d8e1d5; }
QPushButton#donate { background: #f1ddca; border-color: #e2c6aa; text-align: left; }
QPushButton#donate:hover { background: #ead0b8; }
QPushButton#attach { background: #edf2e9; border: 1px solid #d5dfd3; border-radius: 18px; padding: 0; font-size: 22px; }
QPushButton#attach:hover { background: #dce8d9; }
QPushButton#removeAttachment { background: transparent; border: none; padding: 0; font-size: 18px; }
QLabel#eyebrow { color: #61736f; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#muted { color: #65736f; }
QLabel#modelTag { color: #365d51; background: #dce7dc; border-radius: 8px; padding: 6px 9px; font-size: 12px; }
QLabel#title { font-size: 32px; font-weight: 700; color: #244a42; }
QLabel#sectionTitle { font-size: 25px; font-weight: 700; color: #244a42; }
QLabel#role { color: #527068; font-size: 11px; font-weight: 700; letter-spacing: 0.8px; }
""".replace("__ASSETS__", ASSETS.as_posix())


def label(text: str, name: str = "", *, wrap: bool = False) -> QLabel:
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if name:
        widget.setObjectName(name)
    return widget


class Composer(QPlainTextEdit):
    def __init__(self, on_send) -> None:
        super().__init__()
        self.on_send = on_send
        self.setPlaceholderText("Ask a question, work through an idea, or use a tool…")
        self.setFixedHeight(86)
        self.setTabChangesFocus(True)
        self.setAccessibleName("Message")

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            self.on_send()
            event.accept()
            return
        super().keyPressEvent(event)


class SettingsDialog(QDialog):
    def __init__(self, store: SettingsStore, current: AppPreferences, parent=None) -> None:
        super().__init__(parent)
        self.store = store
        self.preferences = AppPreferences(
            api_key=current.api_key, models=list(current.models),
            selected_model=current.selected_model, workspace_path=current.workspace_path,
        )
        self.setWindowTitle("Noki AI · Settings")
        self.setMinimumWidth(490)
        main = QVBoxLayout(self)
        main.setSpacing(14)
        main.setContentsMargins(28, 28, 28, 28)
        main.addWidget(label("Settings", "sectionTitle"))

        main.addWidget(label("OPENROUTER API KEY", "eyebrow"))
        key_row = QHBoxLayout()
        self.key_field = QLineEdit(self.preferences.api_key)
        self.key_field.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_field.setPlaceholderText("Paste your OpenRouter API key")
        self.key_field.setAccessibleName("OpenRouter API key")
        key_row.addWidget(self.key_field, 1)
        reveal = QPushButton("Show")
        reveal.setCheckable(True)
        reveal.toggled.connect(lambda on: self._toggle_key(reveal, on))
        key_row.addWidget(reveal)
        main.addLayout(key_row)
        remove_key = QPushButton("Remove saved key")
        remove_key.clicked.connect(self._remove_key)
        main.addWidget(remove_key, alignment=Qt.AlignmentFlag.AlignLeft)
        note = label("Saved only in Noki AI’s local app settings. Anyone with access to your macOS account can read that file.", "muted", wrap=True)
        main.addWidget(note)

        main.addSpacing(8)
        main.addWidget(label("MODEL", "eyebrow"))
        self.model_combo = QComboBox()
        self.model_combo.setAccessibleName("Selected model")
        self._refresh_models()
        main.addWidget(self.model_combo)
        model_row = QHBoxLayout()
        self.model_field = QLineEdit()
        self.model_field.setPlaceholderText("provider/model-name, for example anthropic/claude…")
        self.model_field.setAccessibleName("Custom model ID")
        self.model_field.returnPressed.connect(self._add_model)
        model_row.addWidget(self.model_field, 1)
        add_model = QPushButton("Add model")
        add_model.clicked.connect(self._add_model)
        model_row.addWidget(add_model)
        main.addLayout(model_row)
        remove_model = QPushButton("Remove selected model")
        remove_model.clicked.connect(self._remove_model)
        main.addWidget(remove_model, alignment=Qt.AlignmentFlag.AlignLeft)
        main.addWidget(label("Model IDs are saved here and sent to OpenRouter when selected.", "muted", wrap=True))

        main.addSpacing(8)
        main.addWidget(label("WORKSPACE", "eyebrow"))
        workspace_row = QHBoxLayout()
        self.workspace_field = QLineEdit(self.preferences.workspace_path)
        self.workspace_field.setReadOnly(True)
        self.workspace_field.setAccessibleName("Workspace folder")
        workspace_row.addWidget(self.workspace_field, 1)
        browse = QPushButton("Choose…")
        browse.clicked.connect(self._choose_workspace)
        workspace_row.addWidget(browse)
        main.addLayout(workspace_row)
        main.addWidget(label("The file tools can read and write only inside this folder.", "muted", wrap=True))

        main.addSpacing(16)
        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        save = QPushButton("Save settings")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        actions.addWidget(save)
        main.addLayout(actions)

    def _toggle_key(self, button: QPushButton, on: bool) -> None:
        self.key_field.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password)
        button.setText("Hide" if on else "Show")

    def _refresh_models(self) -> None:
        self.model_combo.clear()
        self.model_combo.addItems(self.preferences.models)
        self.model_combo.setCurrentText(self.preferences.selected_model)

    def _add_model(self) -> None:
        try:
            self.preferences.add_model(self.model_field.text())
        except ValueError as exc:
            QMessageBox.warning(self, "Model ID", str(exc))
            return
        self.model_field.clear()
        self._refresh_models()

    def _remove_model(self) -> None:
        selected = self.model_combo.currentText()
        try:
            self.preferences.remove_model(selected)
        except ValueError as exc:
            QMessageBox.information(self, "Models", str(exc))
            return
        self._refresh_models()

    def _choose_workspace(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "Choose workspace", self.workspace_field.text())
        if selected:
            self.workspace_field.setText(selected)

    def _remove_key(self) -> None:
        self.preferences.api_key = ""
        try:
            self.store.save(self.preferences)
        except SettingsError as exc:
            QMessageBox.warning(self, "Settings", str(exc))
            return
        self.key_field.clear()
        QMessageBox.information(self, "API key removed", "The saved API key was removed from Noki AI’s settings.")

    def _save(self) -> None:
        self.preferences.api_key = self.key_field.text().strip()
        self.preferences.selected_model = self.model_combo.currentText()
        self.preferences.workspace_path = self.workspace_field.text()
        try:
            self.store.save(self.preferences)
        except (SettingsError, ValueError) as exc:
            QMessageBox.warning(self, "Settings", str(exc))
            return
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, store: SettingsStore | None = None) -> None:
        super().__init__()
        self.store = store or SettingsStore()
        try:
            self.preferences = self.store.load()
        except SettingsError:
            self.preferences = AppPreferences()
            QTimer.singleShot(0, lambda: QMessageBox.warning(
                self, "Settings", "Noki AI could not read its saved settings. Open Settings to save a new configuration."
            ))
        self.history: list[dict] = []
        self.busy = False
        self._thread: QThread | None = None
        self._worker: ChatWorker | None = None
        self.attachment: Attachment | None = None
        self._scroll_pending = False
        self._scroll_settle_timer = QTimer(self)
        self._scroll_settle_timer.setSingleShot(True)
        self._scroll_settle_timer.timeout.connect(self._finish_scroll)
        self._build_ui()
        self._update_model()
        if not self.preferences.api_key:
            QTimer.singleShot(250, self.open_settings)

    def _build_ui(self) -> None:
        self.setWindowTitle("Noki AI")
        self.resize(1120, 760)
        self.setMinimumSize(790, 560)
        self.setWindowIcon(QIcon(str(ASSETS / "app-icon.png")))
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(252)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(25, 30, 25, 26)
        side.setSpacing(16)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QPixmap(str(ASSETS / "logo.png")).scaled(
            54, 54, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        logo.setFixedSize(54, 54)
        logo.setAccessibleName("Noki AI baby logo")
        brand.addWidget(logo)
        brand.addSpacing(8)
        brand.addWidget(label("Noki AI", "sectionTitle"))
        brand.addStretch(1)
        side.addLayout(brand)
        side.addWidget(label("A place to think and make.", "muted", wrap=True))
        side.addSpacing(22)
        self.new_chat_button = QPushButton("＋   New chat")
        self.new_chat_button.setObjectName("primary")
        self.new_chat_button.clicked.connect(self.new_chat)
        side.addWidget(self.new_chat_button)
        self.settings_button = QPushButton("⚙   Settings")
        self.settings_button.setObjectName("quiet")
        self.settings_button.clicked.connect(self.open_settings)
        side.addWidget(self.settings_button)
        side.addSpacing(24)
        side.addWidget(label("ACTIVE MODEL", "eyebrow"))
        self.sidebar_model = label("", "modelTag", wrap=True)
        side.addWidget(self.sidebar_model)
        side.addWidget(label("Your chats stay in this session. File tools use your chosen workspace.", "muted", wrap=True))
        side.addStretch(1)
        donate = QPushButton("♡   Buy me milk  ↗")
        donate.setObjectName("donate")
        donate.setAccessibleName("Buy me milk on PayPal")
        donate.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(DONATION_URL)))
        side.addWidget(donate)
        outer.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(40, 27, 40, 28)
        content_layout.setSpacing(18)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(3)
        heading.addWidget(label("YOUR SPACE", "eyebrow"))
        heading.addWidget(label("Conversation", "title"))
        header.addLayout(heading)
        header.addStretch(1)
        self.header_model = label("", "modelTag")
        header.addWidget(self.header_model, alignment=Qt.AlignmentFlag.AlignBottom)
        content_layout.addLayout(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.messages = QWidget()
        self.message_layout = QVBoxLayout(self.messages)
        self.message_layout.setContentsMargins(0, 14, 0, 15)
        self.message_layout.setSpacing(14)
        self.message_layout.addStretch(1)
        self.scroll.setWidget(self.messages)
        self.scroll.verticalScrollBar().rangeChanged.connect(self._on_scroll_range_changed)
        content_layout.addWidget(self.scroll, 1)
        self._show_empty()

        content_layout.addSpacing(12)
        self.attachment_chip = QFrame()
        self.attachment_chip.setObjectName("attachmentChip")
        chip_layout = QHBoxLayout(self.attachment_chip)
        chip_layout.setContentsMargins(12, 5, 6, 5)
        chip_layout.setSpacing(8)
        self.attachment_name = label("")
        chip_layout.addWidget(self.attachment_name)
        remove_attachment = QPushButton("×")
        remove_attachment.setObjectName("removeAttachment")
        remove_attachment.setAccessibleName("Remove attached file")
        remove_attachment.setFixedSize(28, 28)
        remove_attachment.clicked.connect(self._remove_attachment)
        chip_layout.addWidget(remove_attachment)
        content_layout.addWidget(self.attachment_chip, alignment=Qt.AlignmentFlag.AlignLeft)
        self.attachment_chip.hide()

        composer_frame = QFrame()
        composer_frame.setObjectName("composer")
        composer_layout = QHBoxLayout(composer_frame)
        composer_layout.setContentsMargins(15, 10, 12, 10)
        composer_layout.setSpacing(10)
        self.attach_button = QPushButton("+")
        self.attach_button.setObjectName("attach")
        self.attach_button.setAccessibleName("Attach a file")
        self.attach_button.setToolTip("Attach a text file or text-based PDF")
        self.attach_button.setFixedSize(36, 36)
        self.attach_button.clicked.connect(self._choose_attachment)
        composer_layout.addWidget(self.attach_button, alignment=Qt.AlignmentFlag.AlignBottom)
        self.composer = Composer(self.send)
        composer_layout.addWidget(self.composer, 1)
        self.send_button = QPushButton("Send  ↗")
        self.send_button.setObjectName("primary")
        self.send_button.setMinimumWidth(95)
        self.send_button.clicked.connect(self.send)
        composer_layout.addWidget(self.send_button, alignment=Qt.AlignmentFlag.AlignBottom)
        content_layout.addWidget(composer_frame)
        self.status = label("Enter to send · Shift+Enter for a new line", "muted")
        content_layout.addWidget(self.status)
        outer.addWidget(content, 1)

    def _show_empty(self) -> None:
        self.empty = QFrame()
        self.empty.setObjectName("photoCard")
        self.empty.setMaximumWidth(610)
        box = QHBoxLayout(self.empty)
        box.setContentsMargins(24, 24, 30, 24)
        box.setSpacing(24)
        portrait = QLabel()
        portrait.setPixmap(QPixmap(str(ASSETS / "portrait.png")).scaled(
            132, 173, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation))
        portrait.setFixedSize(132, 173)
        portrait.setAccessibleName("Noki AI portrait logo")
        box.addWidget(portrait)
        text_box = QVBoxLayout()
        text_box.setSpacing(10)
        text_box.addWidget(label("START ANYWHERE", "eyebrow"))
        text_box.addWidget(label("What are we working on?", "sectionTitle", wrap=True))
        text_box.addWidget(label(
            "Ask a question, run a calculation, or work with files in your workspace.",
            "muted", wrap=True))
        text_box.addStretch(1)
        box.addLayout(text_box, 1)
        self.message_layout.insertWidget(0, self.empty, alignment=Qt.AlignmentFlag.AlignHCenter)

    def _add_message(self, role: str, body: str, extra: str = "") -> None:
        if self.empty:
            self.message_layout.removeWidget(self.empty)
            self.empty.hide()
            self.empty.deleteLater()
            self.empty = None
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        bubble = QFrame()
        bubble.setObjectName("messageUser" if role == "You" else "messageAssistant")
        bubble.setMaximumWidth(720)
        bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        box = QVBoxLayout(bubble)
        box.setContentsMargins(18, 15, 18, 15)
        box.setSpacing(8)
        box.addWidget(label(role.upper(), "role"))
        box.addWidget(label(body, wrap=True))
        if extra:
            box.addWidget(label(extra, "muted", wrap=True))
        if role == "You":
            line.addStretch(1)
            line.addWidget(bubble)
        else:
            line.addWidget(bubble)
            line.addStretch(1)
        self.message_layout.insertWidget(self.message_layout.count() - 1, row)
        self._scroll_pending = True
        QTimer.singleShot(0, self._scroll_to_bottom)
        self._scroll_settle_timer.start(150)

    def _on_scroll_range_changed(self, _minimum: int, _maximum: int) -> None:
        if self._scroll_pending:
            self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        scrollbar = self.scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _finish_scroll(self) -> None:
        if self._scroll_pending:
            self._scroll_to_bottom()
            self._scroll_pending = False

    def _choose_attachment(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Attach a file", str(Path.home() / "Documents"),
            "Text and PDF files (*.txt *.md *.markdown *.csv *.tsv *.json *.yaml *.yml *.xml *.html *.css *.js *.ts *.py *.sh *.log *.rst *.pdf)",
        )
        if not path:
            return
        try:
            attachment = load_attachment(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Could not attach file", str(exc))
            return
        self.attachment = attachment
        self.attachment_name.setText(f"📎  {attachment.name}" + (" · first 20,000 characters" if attachment.truncated else ""))
        self.attachment_chip.show()
        self.composer.setFocus()

    def _remove_attachment(self) -> None:
        self.attachment = None
        self.attachment_chip.hide()
        self.composer.setFocus()

    def _update_model(self) -> None:
        self.sidebar_model.setText(self.preferences.selected_model)
        self.header_model.setText(self.preferences.selected_model)

    def open_settings(self) -> None:
        if self.busy:
            return
        dialog = SettingsDialog(self.store, self.preferences, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.preferences = dialog.preferences
            self._update_model()
            self.status.setText("Settings saved. Enter to send · Shift+Enter for a new line")
        else:
            # Remove saved key acts immediately, even if the dialog is later cancelled.
            try:
                self.preferences = self.store.load()
            except SettingsError:
                pass

    def new_chat(self) -> None:
        if self.busy:
            return
        self.history.clear()
        self._remove_attachment()
        while self.message_layout.count() > 1:
            item = self.message_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.empty = None
        self._show_empty()
        self.status.setText("New chat. Enter to send · Shift+Enter for a new line")
        self.composer.setFocus()

    def send(self) -> None:
        if self.busy:
            return
        prompt = self.composer.toPlainText().strip()
        if not prompt and not self.attachment:
            return
        if not self.preferences.api_key.strip():
            QMessageBox.information(self, "API key needed", "Add your OpenRouter API key in Settings to start a chat.")
            self.open_settings()
            return
        attachment = self.attachment
        request_prompt = attachment.add_to_prompt(prompt) if attachment else prompt
        self.composer.clear()
        if attachment:
            self._remove_attachment()
        self._add_message("You", prompt or "Please help me with the attached file.",
                          f"📎 {attachment.name}" if attachment else "")
        self.busy = True
        self.send_button.setEnabled(False)
        self.attach_button.setEnabled(False)
        self.new_chat_button.setEnabled(False)
        self.settings_button.setEnabled(False)
        self.status.setText("Noki AI is thinking…")
        self._thread = QThread(self)
        self._worker = ChatWorker(
            api_key=self.preferences.api_key,
            model=self.preferences.selected_model,
            workspace=self.preferences.workspace_path,
            prompt=request_prompt,
            history=list(self.history),
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.approval_requested.connect(self._show_approval)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.done.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._worker_finished)
        self._thread.start()

    def _show_approval(self, request: ApprovalRequest) -> None:
        args = request.arguments
        content = str(args.get("content", ""))
        preview = content[:300] + ("…" if len(content) > 300 else "")
        message = QMessageBox(self)
        message.setWindowTitle("Approve file write")
        message.setIcon(QMessageBox.Icon.Question)
        message.setText("Allow Noki AI to write a workspace file?")
        message.setInformativeText(
            f"Path: {args.get('path', '')}\n"
            f"Size: {len(content.encode('utf-8')):,} bytes\n"
            f"Overwrite: {'Yes' if args.get('overwrite') else 'No'}\n\n"
            f"Preview:\n{preview or '(empty file)'}"
        )
        message.setDetailedText(preview or "(empty file)")
        message.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        message.setDefaultButton(QMessageBox.StandardButton.No)
        request.answer(message.exec() == QMessageBox.StandardButton.Yes)

    def _on_completed(self, result) -> None:
        if result.stop_reason == "final_answer":
            self.history = result.messages[1:]
        notices = " · ".join(result.tool_notices)
        self._add_message("Noki AI", result.final_text or "(No response)", notices)
        self.status.setText("Ready")

    def _on_failed(self, message: str) -> None:
        self._add_message("Noki AI", f"Request failed: {message}")
        self.status.setText("Request failed. Check Settings or try again.")

    def _worker_finished(self) -> None:
        self.busy = False
        self.send_button.setEnabled(True)
        self.attach_button.setEnabled(True)
        self.new_chat_button.setEnabled(True)
        self.settings_button.setEnabled(True)
        self._thread = None
        self._worker = None
        self.composer.setFocus()

    def closeEvent(self, event) -> None:
        if self.busy:
            QMessageBox.information(self, "Request in progress", "Please wait for the current request to finish.")
            event.ignore()
            return
        super().closeEvent(event)


def main() -> int:
    QApplication.setOrganizationName("Noki")
    QApplication.setApplicationName("Noki AI")
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    QFontDatabase.addApplicationFont(str(ASSETS / "BricolageGrotesque.ttf"))
    app.setFont(QFont("Bricolage Grotesque", 13))
    app.setWindowIcon(QIcon(str(ASSETS / "app-icon.png")))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
