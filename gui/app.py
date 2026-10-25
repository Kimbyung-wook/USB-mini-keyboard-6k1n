"""PySide6 main window for the 6-key + knob macro keyboard configurator."""
from __future__ import annotations

import argparse
import sys
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from . import backup, macro
from . import protocol as p
from .device import DeviceClient, DeviceError, NotConnectedError
from .transport import HidTransport, MockDevice, Transport, TransportError
from .widgets import DeviceView, MacroEditor

APP_TITLE = "매크로 키보드 설정 (6키 + 노브)"
DEFAULT_CAPACITY = 4096
POLL_INTERVAL_MS = 2000
TEST_COUNTDOWN_S = 3

SAMPLE_SLOTS = [
    "Hello world{ENTER}", "{CTRL+C}", "{CTRL+V}",
    "{WIN+R}{DELAY:300}notepad{ENTER}", "{ALT+TAB}", "{CTRL+SHIFT+ESC}",
    "{RIGHT}", "{LEFT}", "{ENTER}",
]


class MainWindow(QMainWindow):
    def __init__(self, connect_fn: Callable[[], Transport], *, auto_reconnect: bool = True,
                 mock_label: str = ""):
        super().__init__()
        self.setWindowTitle(APP_TITLE + (f" — {mock_label}" if mock_label else ""))
        self.resize(900, 680)

        self._connect_fn = connect_fn
        self.client: DeviceClient | None = None
        self.slots: list[str] = [""] * p.SLOT_COUNT
        self.baseline: list[str] = [""] * p.SLOT_COUNT   # what the device holds
        self.current = 0
        self._countdown = 0

        self._build_ui()
        self._refresh_all()

        self._poll = QTimer(self)
        self._poll.setInterval(POLL_INTERVAL_MS)
        self._poll.timeout.connect(self._poll_device)
        if auto_reconnect:
            self._poll.start()

        self._test_timer = QTimer(self)
        self._test_timer.setInterval(1000)
        self._test_timer.timeout.connect(self._test_tick)

    # ------------------------------------------------------------ layout
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)

        # Connection bar
        conn = QHBoxLayout()
        self.conn_label = QLabel()
        self.conn_label.setStyleSheet("font-weight: bold;")
        self.connect_btn = QPushButton("연결")
        self.connect_btn.clicked.connect(self.toggle_connection)
        self.refresh_btn = QPushButton("새로고침")
        self.refresh_btn.setToolTip("장치 상태를 다시 확인합니다")
        self.refresh_btn.clicked.connect(self.refresh_status)
        self.flash_btn = QPushButton("펌웨어 업데이트")
        self.flash_btn.setEnabled(False)
        self.flash_btn.setToolTip("준비 중인 기능입니다")
        conn.addWidget(self.conn_label, 1)
        conn.addWidget(self.connect_btn)
        conn.addWidget(self.refresh_btn)
        conn.addWidget(self.flash_btn)
        root.addLayout(conn)

        # Device picture
        dev_box = QGroupBox("키 / 노브 선택")
        dev_lay = QVBoxLayout(dev_box)
        self.device_view = DeviceView()
        self.device_view.slotSelected.connect(self.select_slot)
        dev_lay.addWidget(self.device_view)
        root.addWidget(dev_box)

        # Editor
        self.editor = MacroEditor()
        self.editor.textEdited.connect(self._on_text_edited)
        root.addWidget(self.editor, 1)

        # Capacity meter
        cap = QHBoxLayout()
        cap.addWidget(QLabel("저장 용량:"))
        self.capacity_bar = QProgressBar()
        self.capacity_bar.setTextVisible(True)
        cap.addWidget(self.capacity_bar, 1)
        root.addLayout(cap)

        # Actions
        actions = QHBoxLayout()
        self.read_btn = QPushButton("장치에서 읽기")
        self.read_btn.clicked.connect(self.read_from_device)
        self.save_btn = QPushButton("장치에 저장")
        self.save_btn.clicked.connect(self.save_to_device)
        self.test_btn = QPushButton("테스트 입력")
        self.test_btn.clicked.connect(self.start_test)
        self.export_btn = QPushButton("JSON 내보내기")
        self.export_btn.clicked.connect(self.export_json)
        self.import_btn = QPushButton("JSON 불러오기")
        self.import_btn.clicked.connect(self.import_json)
        for b in (self.read_btn, self.save_btn, self.test_btn):
            actions.addWidget(b)
        actions.addStretch(1)
        actions.addWidget(self.export_btn)
        actions.addWidget(self.import_btn)
        root.addLayout(actions)

        self.setCentralWidget(central)
        self.statusBar()
        self.editor.set_slot(0, self.slots[0])

    # ------------------------------------------------------------ dialogs (overridable in tests)
    def ask(self, title: str, text: str) -> bool:
        return QMessageBox.question(self, title, text) == QMessageBox.Yes

    def inform(self, title: str, text: str) -> None:
        QMessageBox.information(self, title, text)

    def error(self, title: str, text: str) -> None:
        QMessageBox.warning(self, title, text)

    def choose_save_path(self) -> str:
        path, _ = QFileDialog.getSaveFileName(self, "JSON 내보내기", "macro-keyboard.json",
                                              "JSON 파일 (*.json)")
        return path

    def choose_open_path(self) -> str:
        path, _ = QFileDialog.getOpenFileName(self, "JSON 불러오기", "", "JSON 파일 (*.json)")
        return path

    # ------------------------------------------------------------ state helpers
    @property
    def connected(self) -> bool:
        return self.client is not None and self.client.info is not None

    @property
    def capacity(self) -> int:
        return self.client.info.capacity if self.connected else DEFAULT_CAPACITY

    def is_modified(self, slot: int) -> bool:
        return self.slots[slot] != self.baseline[slot]

    def has_unsaved(self) -> bool:
        return any(self.is_modified(i) for i in range(p.SLOT_COUNT))

    def blob_size(self) -> int:
        return p.blob_size(self.slots)

    def invalid_slots(self) -> list[int]:
        return [i for i, s in enumerate(self.slots) if not macro.parse(s).ok]

    def _refresh_all(self) -> None:
        for i in range(p.SLOT_COUNT):
            self._refresh_slot(i)
        self._refresh_capacity()
        self._refresh_connection()

    def _refresh_slot(self, slot: int) -> None:
        self.device_view.update_slot(slot, self.slots[slot], self.is_modified(slot),
                                     not macro.parse(self.slots[slot]).ok)

    def _refresh_capacity(self) -> None:
        used, cap = self.blob_size(), self.capacity
        self.capacity_bar.setMaximum(cap)
        self.capacity_bar.setValue(min(used, cap))
        suffix = "" if self.connected else " (장치 미연결, 기본값 기준)"
        if used > cap:
            self.capacity_bar.setFormat(f"{used} / {cap} 바이트 — 용량 초과!{suffix}")
            self.capacity_bar.setStyleSheet("QProgressBar::chunk { background: #c62828; }")
        else:
            self.capacity_bar.setFormat(f"{used} / {cap} 바이트 ({used * 100 // cap}%){suffix}")
            self.capacity_bar.setStyleSheet("")
        self._refresh_buttons()

    def _refresh_connection(self) -> None:
        if self.connected:
            info = self.client.info
            src = self.client.transport.description if self.client.transport else ""
            self.conn_label.setText(
                f"● 연결됨 ({src}) · 펌웨어 v{info.fw_version} · 용량 {info.capacity}바이트")
            self.conn_label.setStyleSheet("font-weight: bold; color: #2e7d32;")
            self.connect_btn.setText("연결 끊기")
        else:
            self.conn_label.setText("○ 연결 안 됨")
            self.conn_label.setStyleSheet("font-weight: bold; color: #757575;")
            self.connect_btn.setText("연결")
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        on = self.connected
        self.read_btn.setEnabled(on)
        self.save_btn.setEnabled(on and self.blob_size() <= self.capacity)
        self.test_btn.setEnabled(on and self._countdown == 0)
        self.refresh_btn.setEnabled(True)

    def _update_title(self) -> None:
        base = self.windowTitle().lstrip("* ")
        self.setWindowTitle(("* " if self.has_unsaved() else "") + base)

    # ------------------------------------------------------------ slot editing
    def select_slot(self, slot: int) -> None:
        self.current = slot
        self.device_view.select(slot)
        self.editor.set_slot(slot, self.slots[slot])

    def _on_text_edited(self, text: str) -> None:
        self.set_slot_text(self.current, text, update_editor=False)

    def set_slot_text(self, slot: int, text: str, update_editor: bool = True) -> None:
        self.slots[slot] = macro.normalize_newlines(text)
        if update_editor and slot == self.current:
            self.editor.set_slot(slot, self.slots[slot])
        self._refresh_slot(slot)
        self._refresh_capacity()
        self._update_title()

    def _load_slots(self, slots: list[str], *, from_device: bool) -> None:
        self.slots = list(slots)
        if from_device:
            self.baseline = list(slots)
        self.editor.set_slot(self.current, self.slots[self.current])
        self._refresh_all()
        self._update_title()

    # ------------------------------------------------------------ connection
    def toggle_connection(self) -> None:
        if self.connected:
            self.disconnect_device()
        else:
            self.connect_device()

    def connect_device(self, quiet: bool = False) -> bool:
        try:
            transport = self._connect_fn()
        except TransportError as e:
            if not quiet:
                self.error("연결 실패", str(e))
            return False
        client = DeviceClient(transport)
        try:
            client.hello()
        except DeviceError as e:
            client.close()
            if not quiet:
                self.error("연결 실패", str(e))
            return False
        self.client = client
        self._refresh_all()
        self.statusBar().showMessage("장치에 연결했습니다", 3000)
        if not self.has_unsaved():
            self.read_from_device(confirm=False)
        else:
            self.statusBar().showMessage("편집 중인 내용이 있어 자동으로 읽지 않았습니다", 5000)
        return True

    def disconnect_device(self) -> None:
        if self.client:
            self.client.close()
        self.client = None
        self._refresh_all()

    def refresh_status(self) -> None:
        if not self.connected:
            self.connect_device()
            return
        try:
            self.client.hello()
            self.statusBar().showMessage("장치 상태를 확인했습니다", 3000)
        except DeviceError as e:
            self._handle_device_error("새로고침 실패", e)
        self._refresh_all()

    def _poll_device(self) -> None:
        """Auto-reconnect when a keyboard appears; notice when it is unplugged."""
        if self._countdown:
            return
        if not self.connected:
            self.connect_device(quiet=True)
        elif isinstance(self.client.transport, HidTransport):
            try:
                present = bool(HidTransport.find_paths())
            except TransportError:
                present = True
            if not present:
                self.disconnect_device()
                self.statusBar().showMessage("장치 연결이 끊겼습니다", 5000)

    def _handle_device_error(self, title: str, e: Exception) -> None:
        if isinstance(e, NotConnectedError):
            self.disconnect_device()
        self.error(title, str(e))

    # ------------------------------------------------------------ device actions
    def read_from_device(self, confirm: bool = True) -> bool:
        if not self.connected:
            self.error("읽기", "장치가 연결되어 있지 않습니다")
            return False
        if confirm and self.has_unsaved() and not self.ask(
                "장치에서 읽기", "저장하지 않은 편집 내용이 있습니다.\n장치의 내용으로 덮어쓸까요?"):
            return False
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            cfg = self.client.read_config()
        except DeviceError as e:
            QApplication.restoreOverrideCursor()
            self._handle_device_error("읽기 실패", e)
            return False
        QApplication.restoreOverrideCursor()
        self._load_slots(cfg.slots, from_device=True)
        if cfg.valid:
            self.statusBar().showMessage("장치에서 설정을 읽었습니다", 3000)
        else:
            self.statusBar().showMessage(f"장치에 저장된 설정 없음 — 빈 슬롯으로 시작합니다 ({cfg.reason})", 8000)
        return True

    def save_to_device(self, confirm: bool = True) -> bool:
        if not self.connected:
            self.error("저장", "장치가 연결되어 있지 않습니다")
            return False
        bad = self.invalid_slots()
        if bad:
            names = ", ".join(p.SLOT_LABELS_KO[i] for i in bad)
            self.error("저장할 수 없음", f"문법 오류가 있는 슬롯이 있습니다: {names}\n오류를 고친 뒤 다시 저장하세요.")
            self.select_slot(bad[0])
            return False
        size, cap = self.blob_size(), self.capacity
        if size > cap:
            self.error("저장할 수 없음", f"설정 크기({size}바이트)가 장치 용량({cap}바이트)을 넘습니다.")
            return False
        if confirm and not self.ask("장치에 저장", f"9개 슬롯 전체({size}바이트)를 장치에 저장할까요?"):
            return False
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.client.write_config(self.slots)
        except DeviceError as e:
            QApplication.restoreOverrideCursor()
            self._handle_device_error("저장 실패", e)
            return False
        QApplication.restoreOverrideCursor()
        self.baseline = list(self.slots)
        self._refresh_all()
        self._update_title()
        self.statusBar().showMessage(f"장치에 저장했습니다 ({size}바이트)", 5000)
        if confirm:
            self.inform("저장 완료", f"장치에 저장했습니다 ({size}바이트).")
        return True

    def start_test(self, confirm: bool = True) -> bool:
        if not self.connected:
            self.error("테스트 입력", "장치가 연결되어 있지 않습니다")
            return False
        slot = self.current
        msg = (f"{p.SLOT_LABELS_KO[slot]}의 문자열을 장치가 실제로 타이핑합니다.\n"
               f"{TEST_COUNTDOWN_S}초 안에 입력받을 창(예: 메모장)을 클릭해 포커스를 옮기세요.")
        if self.is_modified(slot):
            msg += "\n\n주의: 이 슬롯은 아직 저장하지 않았습니다. 장치에 저장된 내용이 입력됩니다."
        if confirm and not self.ask("테스트 입력", msg + "\n\n계속할까요?"):
            return False
        self._test_slot = slot
        self._countdown = TEST_COUNTDOWN_S
        self._show_countdown()
        self._test_timer.start()
        self._refresh_buttons()
        return True

    def _show_countdown(self) -> None:
        self.test_btn.setText(f"{self._countdown}초 후 입력…")
        self.statusBar().showMessage(f"{self._countdown}초 후 입력을 시작합니다. 입력받을 창을 클릭하세요.")

    def _test_tick(self) -> None:
        self._countdown -= 1
        if self._countdown > 0:
            self._show_countdown()
            return
        self._test_timer.stop()
        self.test_btn.setText("테스트 입력")
        self.send_test(self._test_slot)
        self._refresh_buttons()

    def send_test(self, slot: int) -> bool:
        if not self.connected:
            self.error("테스트 입력 실패", "장치 연결이 끊겼습니다")
            return False
        try:
            self.client.test(slot)
        except DeviceError as e:
            self._handle_device_error("테스트 입력 실패", e)
            return False
        self.statusBar().showMessage(f"{p.SLOT_LABELS_KO[slot]} 테스트 입력을 보냈습니다", 4000)
        return True

    # ------------------------------------------------------------ JSON backup
    def export_json(self, path: str | None = None) -> bool:
        path = path or self.choose_save_path()
        if not path:
            return False
        try:
            backup.save(path, self.slots)
        except OSError as e:
            self.error("내보내기 실패", str(e))
            return False
        self.statusBar().showMessage(f"내보냈습니다: {path}", 5000)
        return True

    def import_json(self, path: str | None = None) -> bool:
        path = path or self.choose_open_path()
        if not path:
            return False
        try:
            slots = backup.load(path)
        except backup.BackupError as e:
            self.error("불러오기 실패", str(e))
            return False
        self._load_slots(slots, from_device=False)
        self.statusBar().showMessage("불러왔습니다. 장치에 반영하려면 [장치에 저장]을 누르세요", 6000)
        return True

    # ------------------------------------------------------------ closing
    def closeEvent(self, event: QCloseEvent) -> None:
        if self.has_unsaved() and not self.ask(
                "종료", "장치에 저장하지 않은 편집 내용이 있습니다.\n저장하지 않고 종료할까요?"):
            event.ignore()
            return
        self._poll.stop()
        self._test_timer.stop()
        if self.client:
            self.client.close()
        event.accept()


def make_mock_connector(mock: MockDevice) -> Callable[[], Transport]:
    def connect() -> Transport:
        if mock.in_bootloader:
            raise TransportError("모의 장치가 부트로더 모드입니다")
        mock.reconnect()
        return mock
    return connect


def build_window(use_mock: bool) -> MainWindow:
    if use_mock:
        mock = MockDevice(storage=p.encode_blob(SAMPLE_SLOTS))
        return MainWindow(make_mock_connector(mock), auto_reconnect=False, mock_label="모의 장치")
    return MainWindow(HidTransport.open_first, auto_reconnect=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--mock", action="store_true", help="실제 장치 대신 모의 장치 사용")
    args, qt_args = parser.parse_known_args(argv)
    app = QApplication([sys.argv[0], *qt_args])
    win = build_window(args.mock)
    win.show()
    if args.mock:
        QTimer.singleShot(0, win.connect_device)
    else:
        QTimer.singleShot(0, lambda: win.connect_device(quiet=True))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
