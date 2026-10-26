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
from .device import DeviceClient, DeviceError, DeviceStatusError, NotConnectedError
from .transport import HidTransport, MockDevice, Transport, TransportError
from .version import VERSION, version_text
from .widgets import DeviceView, LockPatternEditor, MacroEditor

APP_TITLE = "매크로 키보드 설정 (6키 + 노브)"
DEFAULT_CAPACITY = 128  # firmware v1.0 stores the blob in the 128-byte DataFlash
POLL_INTERVAL_MS = 2000
TEST_COUNTDOWN_S = 3

# Fits in 128 bytes (125 with header and slot lengths)
SAMPLE_SLOTS = [
    "Hello{ENTER}", "{CTRL+C}", "{CTRL+V}",
    "{WIN+R}{DELAY:300}calc{ENTER}", "{ALT+TAB}", "{CTRL+SHIFT+ESC}",
    "{UP}", "{DOWN}", "{ENTER}",
]


class MainWindow(QMainWindow):
    def __init__(self, connect_fn: Callable[[], Transport], *, auto_reconnect: bool = True,
                 mock_label: str = ""):
        super().__init__()
        self.setWindowTitle(f"{APP_TITLE} v{VERSION}" + (f" — {mock_label}" if mock_label else ""))
        self.resize(900, 780)

        self._connect_fn = connect_fn
        self.client: DeviceClient | None = None
        self.slots: list[str] = [""] * p.SLOT_COUNT
        self.baseline: list[str] = [""] * p.SLOT_COUNT   # what the device holds
        self.lock: list[int] = []
        self.lock_baseline: list[int] = []
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

        # Lock pattern
        self.lock_editor = LockPatternEditor()
        self.lock_editor.patternChanged.connect(self.set_lock)
        root.addWidget(self.lock_editor)

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
        # Version and build date stay at the right end of the status bar
        self.version_label = QLabel(version_text())
        self.version_label.setStyleSheet("color: palette(mid);")
        self.statusBar().addPermanentWidget(self.version_label)
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
    def device_locked(self) -> bool:
        return self.connected and self.client.info.locked

    @property
    def capacity(self) -> int:
        return self.client.info.capacity if self.connected else DEFAULT_CAPACITY

    def is_modified(self, slot: int) -> bool:
        return self.slots[slot] != self.baseline[slot]

    def lock_modified(self) -> bool:
        return self.lock != self.lock_baseline

    def has_unsaved(self) -> bool:
        return self.lock_modified() or any(self.is_modified(i) for i in range(p.SLOT_COUNT))

    def blob_size(self) -> int:
        return p.blob_size(self.slots, self.lock)

    def invalid_slots(self) -> list[int]:
        return [i for i, s in enumerate(self.slots) if not macro.parse(s).ok]

    def _refresh_all(self) -> None:
        for i in range(p.SLOT_COUNT):
            self._refresh_slot(i)
        self.lock_editor.set_pattern(self.lock)
        self.lock_editor.set_modified(self.lock_modified())
        self._refresh_capacity()
        self._refresh_connection()

    def _refresh_slot(self, slot: int) -> None:
        self.device_view.update_slot(slot, self.slots[slot], self.is_modified(slot),
                                     not macro.parse(self.slots[slot]).ok)

    def _refresh_capacity(self) -> None:
        used, cap = self.blob_size(), self.capacity
        # Every stored character costs one byte (macro text like {ENTER} counts as typed);
        # the rest of the blob is the fixed header and slot lengths.
        chars = p.blob_size(self.slots) - p.blob_size([""] * p.SLOT_COUNT)
        self.capacity_bar.setMaximum(cap)
        self.capacity_bar.setValue(min(used, cap))
        suffix = "" if self.connected else " (장치 미연결, 기본값 기준)"
        if used > cap:
            self.capacity_bar.setFormat(
                f"{chars}자 입력 · {used - cap}자 초과! ({used} / {cap} 바이트){suffix}")
            self.capacity_bar.setStyleSheet("QProgressBar::chunk { background: #c62828; }")
        else:
            self.capacity_bar.setFormat(
                f"{chars}자 입력 · {cap - used}자 더 입력 가능 ({used} / {cap} 바이트){suffix}")
            self.capacity_bar.setStyleSheet("")
        self.capacity_bar.setToolTip(
            "9개 슬롯 전체의 글자 수입니다. {ENTER} 같은 매크로 표기도 쓴 글자 수만큼 차지합니다.\n"
            f"헤더와 슬롯 길이 정보로 {p.blob_size([''] * p.SLOT_COUNT)}바이트가 고정으로 쓰입니다."
            + (f"\n잠금 패턴이 {used - chars - p.blob_size([''] * p.SLOT_COUNT)}바이트를 씁니다."
               if self.lock else ""))
        self._refresh_buttons()

    def _refresh_connection(self) -> None:
        if self.connected:
            info = self.client.info
            src = self.client.transport.description if self.client.transport else ""
            head = f"({src}) · {info.fw_text} · 용량 {info.capacity}바이트"
            if info.blocked:
                self.conn_label.setText(f"🔒 잠김 {head} — 5번 틀려서 입력을 막았습니다. 키보드를 다시 꽂으세요")
                self.conn_label.setStyleSheet("font-weight: bold; color: #c62828;")
            elif info.locked:
                self.conn_label.setText(f"🔒 잠김 {head} — 키보드에서 잠금 패턴을 입력하세요")
                self.conn_label.setStyleSheet("font-weight: bold; color: #e65100;")
            else:
                self.conn_label.setText(f"● 연결됨 {head}")
                self.conn_label.setStyleSheet("font-weight: bold; color: #2e7d32;")
            self.connect_btn.setText("연결 끊기")
        else:
            self.conn_label.setText("○ 연결 안 됨")
            self.conn_label.setStyleSheet("font-weight: bold; color: #757575;")
            self.connect_btn.setText("연결")
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        on = self.connected
        unlocked = on and not self.device_locked
        self.read_btn.setEnabled(unlocked)
        self.save_btn.setEnabled(on and self.blob_size() <= self.capacity
                                 and p.lock_error(self.lock) is None)
        self.test_btn.setEnabled(unlocked and self._countdown == 0)
        self.refresh_btn.setEnabled(True)
        supported = not on or self.client.info.supports_lock
        self.lock_editor.setEnabled(supported or bool(self.lock))  # still lets a pattern be cleared
        self.lock_editor.setToolTip("" if supported else
                                    "이 펌웨어는 잠금을 지원하지 않습니다 (펌웨어 v1.1 이상 필요)")

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

    def set_lock(self, steps: list[int]) -> None:
        self.lock = list(steps)
        self.lock_editor.set_pattern(self.lock)
        self.lock_editor.set_modified(self.lock_modified())
        self._refresh_capacity()
        self._update_title()

    def _load_slots(self, slots: list[str], lock: list[int] | None = None, *,
                    from_device: bool) -> None:
        """Load slot texts; lock None keeps the current pattern (JSON has none)."""
        self.slots = list(slots)
        if lock is not None:
            self.lock = list(lock)
        if from_device:
            self.baseline = list(slots)
            self.lock_baseline = list(self.lock)
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
        if client.info.locked:
            self.statusBar().showMessage(
                "장치가 잠겨 있습니다. 키보드에서 잠금 패턴을 입력하면 설정을 읽어옵니다", 8000)
        elif not self.has_unsaved():
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
            self.check_lock()
            self.statusBar().showMessage("장치 상태를 확인했습니다", 3000)
        except DeviceError as e:
            self._handle_device_error("새로고침 실패", e)
        self._refresh_all()

    def check_lock(self) -> None:
        """HELLO again; when the keyboard was just unlocked, read its config."""
        was_locked = self.device_locked
        self.client.hello()
        self._refresh_connection()
        if was_locked and not self.device_locked:
            self.statusBar().showMessage("잠금이 풀렸습니다", 3000)
            if not self.has_unsaved():
                self.read_from_device(confirm=False)

    def _poll_device(self) -> None:
        """Auto-reconnect when a keyboard appears; notice when it is unplugged
        or unlocked."""
        if self._countdown:
            return
        if not self.connected:
            self.connect_device(quiet=True)
        elif self.device_locked:
            try:
                self.check_lock()
            except DeviceError:
                self.disconnect_device()
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
        elif isinstance(e, DeviceStatusError) and e.status == p.Status.LOCKED:
            try:
                self.client.hello()   # show the lock in the connection bar
            except DeviceError:
                pass
            self._refresh_connection()
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
        self._load_slots(cfg.slots, cfg.lock, from_device=True)
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
        lock_err = p.lock_error(self.lock)
        if lock_err:
            self.error("저장할 수 없음", f"{lock_err}.\n패턴을 고치거나 모두 지운 뒤 다시 저장하세요.")
            return False
        size, cap = self.blob_size(), self.capacity
        if size > cap:
            self.error("저장할 수 없음", f"설정 크기({size}바이트)가 장치 용량({cap}바이트)을 넘습니다.")
            return False
        was_locked = self.device_locked
        if was_locked:
            question = ("장치가 잠겨 있어 저장된 설정을 읽지 못했습니다.\n"
                        "저장하면 장치의 기존 문자열과 잠금 패턴을 모두 지우고 지금 화면의 내용으로 바꿉니다.\n\n"
                        f"9개 슬롯 전체({size}바이트)를 저장할까요?")
        else:
            question = f"9개 슬롯 전체({size}바이트)를 장치에 저장할까요?"
        lock_note = f"\n잠금 패턴: {p.lock_text(self.lock)}" if self.lock else "\n잠금 패턴: 없음"
        if confirm and not self.ask("장치에 저장", question + lock_note):
            return False
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.client.write_config(self.slots, lock=self.lock)
            self.client.hello()   # lock flags may have changed
        except DeviceError as e:
            QApplication.restoreOverrideCursor()
            self._handle_device_error("저장 실패", e)
            return False
        QApplication.restoreOverrideCursor()
        self.baseline = list(self.slots)
        self.lock_baseline = list(self.lock)
        self._refresh_all()
        self._update_title()
        self.statusBar().showMessage(f"장치에 저장했습니다 ({size}바이트)", 5000)
        if confirm:
            msg = f"장치에 저장했습니다 ({size}바이트)."
            if self.lock and not self.device_locked:
                msg += "\n잠금 패턴은 키보드를 다시 꽂을 때부터 적용됩니다."
            self.inform("저장 완료", msg)
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
        mock = MockDevice(capacity=DEFAULT_CAPACITY, storage=p.encode_blob(SAMPLE_SLOTS))
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
