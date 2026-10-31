"""PySide6 main window for the 6-key + knob macro keyboard configurator."""
from __future__ import annotations

import argparse
import html
import sys
from typing import Callable

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from . import backup, boards, macro
from . import protocol as p
from .device import DeviceClient, DeviceError, DeviceStatusError, NotConnectedError
from .transport import HidTransport, MockDevice, Transport, TransportError
from .version import VERSION, version_text
from .flash_dialog import FirmwareDialog
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
        self.board = p.DEFAULT_BOARD     # layout of the connected (or last) keyboard
        self.board_identified = False    # that keyboard sent its board info (HELLO)
        self.slots: list[str] = [""] * self.board.slot_count
        self.baseline: list[str] = [""] * self.board.slot_count   # what the device holds
        self.lock: list[int] = []
        self.lock_baseline: list[int] = []
        self.autolock = 0                 # auto-lock minutes, 0 = never
        self.autolock_baseline = 0
        self.current = 0
        self._countdown = 0
        self._flashing = False
        self._mock = bool(mock_label)
        self.flash_command_fn = None   # uploader command override (tests)

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
        self.conn_label.setTextFormat(Qt.RichText)
        self.conn_label.setWordWrap(True)
        self.connect_btn = QPushButton("연결")
        self.connect_btn.clicked.connect(self.toggle_connection)
        self.refresh_btn = QPushButton("새로고침")
        self.refresh_btn.setToolTip("장치 상태를 다시 확인합니다")
        self.refresh_btn.clicked.connect(self.refresh_status)
        self.flash_btn = QPushButton("펌웨어 업데이트")
        self.flash_btn.setToolTip("새 펌웨어(.hex)를 키보드에 올립니다")
        self.flash_btn.clicked.connect(self.update_firmware)
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
        self.lock_editor.autolockChanged.connect(self.set_autolock)
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
        return self.lock != self.lock_baseline or self.autolock != self.autolock_baseline

    def has_unsaved(self) -> bool:
        return self.lock_modified() or any(self.is_modified(i) for i in range(len(self.slots)))

    def blob_size(self) -> int:
        return p.blob_size(self.slots, self.lock, self.autolock)

    def invalid_slots(self) -> list[int]:
        return [i for i, s in enumerate(self.slots) if not macro.parse(s).ok]

    def _refresh_all(self) -> None:
        for i in range(len(self.slots)):
            self._refresh_slot(i)
        self.lock_editor.set_pattern(self.lock)
        self.lock_editor.set_autolock(self.autolock)
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
        fixed = p.blob_size([""] * len(self.slots))
        chars = p.blob_size(self.slots) - fixed
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
            f"{len(self.slots)}개 슬롯 전체의 글자 수입니다. {{ENTER}} 같은 매크로 표기도 쓴 글자 수만큼 차지합니다.\n"
            f"헤더와 슬롯 길이 정보로 {fixed}바이트가 고정으로 쓰입니다."
            + (f"\n패턴 암호가 {used - chars - fixed}바이트를 씁니다."
               if self.lock else ""))
        self._refresh_buttons()

    def _refresh_connection(self) -> None:
        # Three short lines instead of one long one: state - what to do,
        # board / capacity, firmware
        if self.connected:
            info = self.client.info
            if info.blocked:
                state, color = "🔒 잠김 - 5번 틀려서 입력을 막았습니다. 키보드를 다시 꽂으세요", "#c62828"
            elif info.locked:
                state, color = "🔒 잠김 - 키보드에서 노브를 2초 누른 뒤 패턴 암호를 입력하세요", "#e65100"
            elif info.lock_flags & p.LOCK_FLAG_SET:
                state, color = "● 연결됨 - 잠금 풀림", "#2e7d32"
            else:
                state, color = "● 연결됨 - 잠금 안 씀", "#2e7d32"
            board = f"{info.board.name} ({info.board.summary})"
            if info.board_info is None:
                board += " · 보드 정보 없음"
            lines = [state, f"{board} / 용량 {info.capacity}바이트", info.fw_text]
            self.conn_label.setToolTip(self.client.transport.description if self.client.transport else "")
            self.connect_btn.setText("연결 끊기")
        else:
            lines, color = ["○ 연결 안 됨"], "#757575"
            self.conn_label.setToolTip("")
            self.connect_btn.setText("연결")
        head, *rest = (html.escape(line) for line in lines)
        self.conn_label.setText("<br>".join([f'<b style="color: {color};">{head}</b>'] + rest))
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        on = self.connected
        unlocked = on and not self.device_locked
        self.read_btn.setEnabled(unlocked)
        self.save_btn.setEnabled(on and self.blob_size() <= self.capacity
                                 and p.lock_error(self.lock, self.board) is None)
        self.test_btn.setEnabled(unlocked and self._countdown == 0)
        self.refresh_btn.setEnabled(True)
        # Nothing to show or edit without a keyboard (see clear_config)
        for w in (self.device_view, self.editor, self.export_btn, self.import_btn):
            w.setEnabled(on)
        supported = not on or self.client.info.supports_lock
        self.lock_editor.setEnabled(on and (supported or bool(self.lock)))  # still lets a pattern be cleared
        self.lock_editor.setToolTip("" if supported else
                                    "이 펌웨어는 잠금을 지원하지 않습니다 (펌웨어 v1.1 이상 필요)")
        self.lock_editor.set_autolock_supported(not on or self.client.info.supports_autolock)

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
        if not self.lock:
            self.autolock = 0      # nothing to lock without a pattern
            self.lock_editor.set_autolock(0)
        self.lock_editor.set_pattern(self.lock)
        self.lock_editor.set_modified(self.lock_modified())
        self._refresh_capacity()
        self._update_title()

    def set_autolock(self, minutes: int) -> None:
        self.autolock = minutes
        self.lock_editor.set_autolock(minutes)
        self.lock_editor.set_modified(self.lock_modified())
        self._refresh_capacity()
        self._update_title()

    def set_board(self, board: p.Board) -> None:
        """Rebuild the key/knob picture and the pattern buttons for another
        keyboard; the slots on screen are emptied (they belong to the old one)."""
        if board == self.board:
            return
        self.board = board
        self.device_view.set_board(board)
        self.lock_editor.set_board(board)
        self.editor.board = board
        self.current = 0
        self.slots = [""] * board.slot_count
        self.baseline = [""] * board.slot_count
        self.lock = []
        self.lock_baseline = []
        self.autolock = self.autolock_baseline = 0
        self.editor.set_slot(0, "")
        self._refresh_all()
        self._update_title()

    def _load_slots(self, slots: list[str], lock: list[int] | None = None, *,
                    from_device: bool, autolock: int | None = None) -> None:
        """Load slot texts; lock/autolock None keep the current ones (JSON has none)."""
        self.slots = list(slots)
        if lock is not None:
            self.lock = list(lock)
        if autolock is not None:
            self.autolock = autolock
        if from_device:
            self.baseline = list(slots)
            self.lock_baseline = list(self.lock)
            self.autolock_baseline = self.autolock
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
        if client.info.board != self.board and self.has_unsaved() and not self.ask(
                "다른 키보드", f"배치가 다른 키보드({client.info.board.summary})가 연결되었습니다.\n"
                "화면의 저장하지 않은 편집 내용을 지우고 이 키보드로 바꿀까요?"):
            client.close()
            return False
        self.client = client
        self.board_identified = client.info.board_info is not None
        self.set_board(client.info.board)
        self._refresh_all()
        self.statusBar().showMessage("장치에 연결했습니다", 3000)
        if client.info.locked:
            self.statusBar().showMessage(
                "장치가 잠겨 있습니다. 키보드에서 노브를 2초 누른 뒤 패턴 암호를 입력하면 설정을 읽어옵니다", 8000)
        elif not self.has_unsaved():
            self.read_from_device(confirm=False)
        else:
            self.statusBar().showMessage("편집 중인 내용이 있어 자동으로 읽지 않았습니다", 5000)
        return True

    def disconnect_device(self) -> None:
        if self.client:
            self.client.close()
        self.client = None
        self.clear_config()

    def clear_config(self) -> None:
        """Forget the slot texts and the lock pattern on screen.

        They are only shown while a keyboard is connected and open: they are
        cleared when it is disconnected or locks again, and read from the
        device again afterwards.
        """
        self.slots = [""] * self.board.slot_count
        self.baseline = [""] * self.board.slot_count
        self.lock = []
        self.lock_baseline = []
        self.autolock = self.autolock_baseline = 0
        self.editor.set_slot(self.current, "")
        self._refresh_all()
        self._update_title()

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
        if not was_locked and self.device_locked:
            self.clear_config()
            self.statusBar().showMessage("키보드가 다시 잠겨서 화면의 설정을 지웠습니다", 5000)
        elif was_locked and not self.device_locked:
            self.statusBar().showMessage("잠금이 풀렸습니다", 3000)
            if not self.has_unsaved():
                self.read_from_device(confirm=False)

    def _poll_device(self) -> None:
        """Auto-reconnect when a keyboard appears; notice when it is unplugged,
        unlocked or locked again (holding the knob on the keyboard)."""
        if self._countdown or self._flashing:
            return
        if not self.connected:
            self.connect_device(quiet=True)
            return
        if isinstance(self.client.transport, HidTransport):
            try:
                present = bool(HidTransport.find_paths())
            except TransportError:
                present = True
            if not present:
                self.disconnect_device()
                self.statusBar().showMessage("장치 연결이 끊겼습니다", 5000)
                return
        if self.client.info.supports_lock:
            try:
                self.check_lock()
            except DeviceError:
                self.disconnect_device()

    def _handle_device_error(self, title: str, e: Exception) -> None:
        if isinstance(e, NotConnectedError):
            self.disconnect_device()
        elif isinstance(e, DeviceStatusError) and e.status == p.Status.LOCKED:
            try:
                self.check_lock()     # show the lock, clear the screen
            except DeviceError:
                pass
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
        self._load_slots(cfg.slots, cfg.lock, from_device=True, autolock=cfg.autolock)
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
            names = ", ".join(self.board.slot_label(i) for i in bad)
            self.error("저장할 수 없음", f"문법 오류가 있는 슬롯이 있습니다: {names}\n오류를 고친 뒤 다시 저장하세요.")
            self.select_slot(bad[0])
            return False
        lock_err = p.lock_error(self.lock, self.board)
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
                        "저장하면 장치의 기존 문자열과 패턴 암호를 모두 지우고 지금 화면의 내용으로 바꿉니다.\n\n"
                        f"{len(self.slots)}개 슬롯 전체({size}바이트)를 저장할까요?")
        else:
            question = f"{len(self.slots)}개 슬롯 전체({size}바이트)를 장치에 저장할까요?"
        lock_note = (f"\n패턴 암호: {p.lock_text(self.lock, self.board)}" if self.lock
                     else "\n패턴 암호: 없음")
        if self.lock:
            minutes = f"{self.autolock}분" if self.autolock else "끔"
            lock_note += f"\n자동 잠금: {minutes}"
        if confirm and not self.ask("장치에 저장", question + lock_note):
            return False
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.client.write_config(self.slots, lock=self.lock, autolock=self.autolock)
            self.client.hello()   # lock flags may have changed
        except DeviceError as e:
            QApplication.restoreOverrideCursor()
            self._handle_device_error("저장 실패", e)
            return False
        QApplication.restoreOverrideCursor()
        self.baseline = list(self.slots)
        self.lock_baseline = list(self.lock)
        self.autolock_baseline = self.autolock
        self._refresh_all()
        self._update_title()
        self.statusBar().showMessage(f"장치에 저장했습니다 ({size}바이트)", 5000)
        if confirm:
            msg = f"장치에 저장했습니다 ({size}바이트)."
            if self.lock and not self.device_locked:
                msg += "\n패턴 암호는 키보드를 다시 꽂을 때부터 적용됩니다."
            self.inform("저장 완료", msg)
        return True

    def start_test(self, confirm: bool = True) -> bool:
        if not self.connected:
            self.error("테스트 입력", "장치가 연결되어 있지 않습니다")
            return False
        slot = self.current
        msg = (f"{self.board.slot_label(slot)}의 문자열을 장치가 실제로 타이핑합니다.\n"
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
        self.statusBar().showMessage(f"{self.board.slot_label(slot)} 테스트 입력을 보냈습니다", 4000)
        return True

    # ------------------------------------------------------------ JSON backup
    def export_json(self, path: str | None = None) -> bool:
        if not self.connected:
            self.error("내보내기", "장치를 연결한 뒤에 내보낼 수 있습니다")
            return False
        path = path or self.choose_save_path()
        if not path:
            return False
        try:
            backup.save(path, self.slots, self.board)
        except OSError as e:
            self.error("내보내기 실패", str(e))
            return False
        self.statusBar().showMessage(f"내보냈습니다: {path}", 5000)
        return True

    def import_json(self, path: str | None = None) -> bool:
        if not self.connected:
            self.error("불러오기", "장치를 연결한 뒤에 불러올 수 있습니다")
            return False
        path = path or self.choose_open_path()
        if not path:
            return False
        try:
            slots, skipped = backup.load(path, self.board)
        except backup.BackupError as e:
            self.error("불러오기 실패", str(e))
            return False
        self._load_slots(slots, from_device=False)
        if skipped:
            self.inform("불러오기", "이 키보드에 없는 슬롯은 건너뛰었습니다: " + ", ".join(skipped))
        self.statusBar().showMessage("불러왔습니다. 장치에 반영하려면 [장치에 저장]을 누르세요", 6000)
        return True

    # ------------------------------------------------------------ firmware update
    def prepare_bootloader(self) -> str:
        """Put the keyboard in the bootloader if the GUI can; return what to tell the user."""
        if self.connected and not self.device_locked:
            try:
                self.client.reboot_to_bootloader()   # closes the client
            except DeviceError as e:
                self.disconnect_device()
                return (f"업데이트 모드로 바꾸지 못했습니다 ({e}). "
                        f"키보드를 뽑았다가 {self.boot_hint} 다시 꽂으세요")
            self.client = None
            self.clear_config()
            return "키보드를 업데이트 모드로 바꿨습니다. 잠시 기다리세요 (보라색 LED)"
        reason = "잠겨 있어서" if self.connected else "연결되어 있지 않아서"
        if self.connected:
            self.disconnect_device()
        return (f"키보드가 {reason} 자동으로 업데이트 모드로 바꿀 수 없습니다. "
                f"키보드를 뽑았다가 {self.boot_hint} 다시 꽂으세요")

    @property
    def boot_hint(self) -> str:
        """How to plug this keyboard in to reach the bootloader (board list)."""
        spec = boards.find(self.board.name)
        return spec.boot_hint if spec else "업데이트 모드 진입 방법대로"

    def make_firmware_dialog(self) -> FirmwareDialog:
        return FirmwareDialog(self.prepare_bootloader, self.flash_command_fn, self,
                              keyboard=self.board, identified=self.board_identified)

    def update_firmware(self) -> bool:
        if self._mock:
            self.inform("펌웨어 업데이트", "모의 장치에서는 펌웨어를 올릴 수 없습니다.")
            return False
        if self.has_unsaved() and not self.ask(
                "펌웨어 업데이트",
                "저장하지 않은 편집 내용이 있습니다. 펌웨어를 올리면 화면의 편집 내용이 지워집니다.\n계속할까요?"):
            return False
        self._flashing = True
        try:
            dlg = self.make_firmware_dialog()
            dlg.exec()
            ok = dlg.succeeded
        finally:
            self._flashing = False
        if ok:
            self.statusBar().showMessage("펌웨어를 올렸습니다. 키보드에 다시 연결합니다", 5000)
            QTimer.singleShot(2000, lambda: self.connect_device(quiet=True))
        elif not self.connected:
            self._refresh_all()
        return ok

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


def parse_board(text: str) -> p.Board:
    """'12x2' (keys x knobs) or '12x2x3' (… x rows) for --mock-board."""
    parts = [int(x) for x in text.lower().split("x")]
    keys, knobs = parts[0], parts[1] if len(parts) > 1 else 1
    rows = parts[2] if len(parts) > 2 else (1 if keys <= 4 else 2 if keys <= 8 else 3)
    return p.Board(keys=keys, knobs=knobs, rows=rows, name=f"MOCK{keys}K{knobs}N",
                   features=MOCK_FEATURES)


# The mock acts like the newest firmware
MOCK_FEATURES = p.BOARD_FEATURE_RGB_LED | p.BOARD_FEATURE_LOCK | p.BOARD_FEATURE_AUTO_LOCK
MOCK_FW = p.SHORT_LOCK_FIRMWARE      # takes 2-step patterns


def build_window(use_mock: bool, mock_board: p.Board | None = None) -> MainWindow:
    if use_mock:
        if mock_board is None:
            mock = MockDevice(capacity=DEFAULT_CAPACITY, fw=MOCK_FW, storage=p.encode_blob(SAMPLE_SLOTS),
                              board=p.Board(features=MOCK_FEATURES))
        else:
            mock = MockDevice(capacity=DEFAULT_CAPACITY, fw=MOCK_FW, board=mock_board)
        return MainWindow(make_mock_connector(mock), auto_reconnect=False, mock_label="모의 장치")
    return MainWindow(HidTransport.open_first, auto_reconnect=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=APP_TITLE)
    parser.add_argument("--mock", action="store_true", help="실제 장치 대신 모의 장치 사용")
    parser.add_argument("--mock-board", metavar="KxN[xR]", type=parse_board,
                        help="모의 장치의 배치: 키 K개, 노브 N개, R행 (예: 12x2). --mock과 함께")
    args, qt_args = parser.parse_known_args(argv)
    app = QApplication([sys.argv[0], *qt_args])
    win = build_window(args.mock or args.mock_board is not None, args.mock_board)
    win.show()
    if args.mock:
        QTimer.singleShot(0, win.connect_device)
    else:
        QTimer.singleShot(0, lambda: win.connect_device(quiet=True))
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
