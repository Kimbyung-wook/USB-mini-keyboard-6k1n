"""Firmware update dialog: pick a .hex, find the chip in the bootloader, then flash.

What to flash with comes from the board list (gui/boards.py): the keyboard
that was connected last (its HELLO board, or the default one) picks the chip,
the uploader options and how to reach the bootloader.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import QProcess, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import boards, bootloader, chips, flasher
from . import protocol as p

# Repo build output (tools/build_fw.ps1): the board's own file first, then
# the plain sketch output
BUILD_DIR = Path(__file__).resolve().parents[1] / "firmware/macro_keyboard/build"
DEFAULT_HEX = BUILD_DIR / "macro_keyboard.ino.hex"

Prepare = Callable[[], str]               # puts the keyboard in the bootloader; returns a hint
CommandFn = Callable[[Path], list[str]]   # hex path -> uploader command line
ScanFn = Callable[[], list[bootloader.ChipInfo]]

SCAN_INTERVAL_MS = 1000

RED, GREEN, GREY, ORANGE = "#c62828", "#2e7d32", "#757575", "#e65100"


def default_hex(spec: boards.BoardSpec | None) -> Path | None:
    for path in ([BUILD_DIR / spec.firmware_file] if spec else []) + [DEFAULT_HEX]:
        if path.is_file():
            return path
    return None


class FirmwareDialog(QDialog):
    def __init__(self, prepare: Prepare, command_fn: CommandFn | None = None,
                 parent: QWidget | None = None, hex_path: str | Path | None = None,
                 scan_fn: ScanFn | None = None, auto_scan: bool = True,
                 keyboard: p.Board = p.DEFAULT_BOARD):
        super().__init__(parent)
        self.setWindowTitle("펌웨어 업데이트")
        self.resize(640, 560)
        self._prepare = prepare
        self._command_fn = command_fn or self._default_command
        self._scan_fn = scan_fn or bootloader.scan
        self.progress = flasher.FlashProgress()
        self.process: QProcess | None = None
        self.succeeded = False
        self.hex: flasher.HexInfo | None = None
        self.chips: list[bootloader.ChipInfo] = []
        self.scan_error = ""
        # The keyboard being updated: HELLO's board, its entry in the board list
        self.keyboard = keyboard
        self.spec = boards.find(keyboard.name)
        self.chip = chips.find(keyboard.chip_id)
        self.boot_hint = self.spec.boot_hint if self.spec else "업데이트 모드 진입 방법대로"

        self.board_label = QLabel(self._board_text())
        self.board_label.setWordWrap(True)

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("펌웨어 파일(.hex)을 고르세요")
        self.browse_btn = QPushButton("파일 선택…")
        self.browse_btn.clicked.connect(self.browse)
        row = QHBoxLayout()
        row.addWidget(self.path_edit, 1)
        row.addWidget(self.browse_btn)

        self.size_label = QLabel()
        self.size_label.setWordWrap(True)

        chips_title = QLabel("인식된 칩 (업데이트 모드)")
        chips_title.setStyleSheet("font-weight: bold;")
        self.chip_table = QTableWidget(0, 4)
        self.chip_table.setHorizontalHeaderLabels(["번호", "파트 번호", "시리얼 번호 (칩 ID)", "부트로더"])
        self.chip_table.verticalHeader().setVisible(False)
        self.chip_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.chip_table.setSelectionMode(QAbstractItemView.NoSelection)
        header = self.chip_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)   # serial + "(방금 연결된 키보드)"
        self.chip_table.setMaximumHeight(130)
        self.chip_status = QLabel()
        self.chip_status.setWordWrap(True)
        self.boot_btn = QPushButton("업데이트 모드로 전환")
        self.boot_btn.setToolTip("연결되어 잠금이 풀린 키보드를 업데이트 모드로 바꿉니다")
        self.boot_btn.clicked.connect(self.enter_bootloader)
        self.scan_btn = QPushButton("다시 검색")
        self.scan_btn.clicked.connect(self.scan)
        chip_buttons = QHBoxLayout()
        chip_buttons.addWidget(self.chip_status, 1)
        chip_buttons.addWidget(self.boot_btn)
        chip_buttons.addWidget(self.scan_btn)

        self.hint = QLabel(
            "키보드가 연결되어 있고 잠금이 풀려 있으면 [업데이트 모드로 전환]을 누르세요. "
            f"잠겨 있거나 연결되어 있지 않으면 키보드를 뽑았다가 <b>{self.boot_hint}</b> 다시 꽂으세요. "
            "칩이 목록에 나타나면 [장입]을 누릅니다. 키별 문자열과 패턴 암호는 그대로 남습니다.")
        self.hint.setWordWrap(True)

        self.stage_label = QLabel("대기")
        self.stage_label.setStyleSheet("font-weight: bold;")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)

        self.start_btn = QPushButton("장입")
        self.start_btn.clicked.connect(self.start)
        self.close_btn = QPushButton("닫기")
        self.close_btn.clicked.connect(self.cancel_or_close)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.start_btn)
        buttons.addWidget(self.close_btn)

        lay = QVBoxLayout(self)
        lay.addWidget(self.board_label)
        lay.addLayout(row)
        lay.addWidget(self.size_label)
        lay.addWidget(chips_title)
        lay.addWidget(self.chip_table)
        lay.addLayout(chip_buttons)
        lay.addWidget(self.hint)
        lay.addWidget(self.stage_label)
        lay.addWidget(self.bar)
        lay.addWidget(self.log, 1)
        lay.addLayout(buttons)

        # The list follows plugging and unplugging without pressing anything
        self.scan_timer = QTimer(self)
        self.scan_timer.setInterval(SCAN_INTERVAL_MS)
        self.scan_timer.timeout.connect(self.scan)

        start = hex_path or default_hex(self.spec)
        if start:
            self.set_hex(start)
        self.scan()
        if auto_scan:
            self.scan_timer.start()

    @property
    def hex_size(self) -> int:
        return self.hex.size if self.hex else 0

    def _board_text(self) -> str:
        k = self.keyboard
        chip = chips.name_of(k.chip_id)
        if self.spec is None:
            return f"키보드: {k.name} ({chip}, {k.summary}) · 보드 목록에 없는 키보드"
        return f"키보드: {k.name} · {self.spec.description} · 업데이트 모드: {self.boot_hint} 꽂기"

    # ------------------------------------------------------------ dialogs (overridable in tests)
    def choose_hex_path(self) -> str:
        start = self.path_edit.text() or str(BUILD_DIR if BUILD_DIR.is_dir() else "")
        path, _ = QFileDialog.getOpenFileName(self, "펌웨어 파일 선택", start, "Intel HEX (*.hex)")
        return path

    def confirm(self, title: str, text: str) -> bool:
        return QMessageBox.question(self, title, text) == QMessageBox.Yes

    # ------------------------------------------------------------ file
    def browse(self) -> None:
        path = self.choose_hex_path()
        if path:
            self.set_hex(path)

    def set_hex(self, path: str | Path) -> bool:
        """Check the file only; flashing waits for [장입]."""
        self.path_edit.setText(str(path))
        self.hex = None
        try:
            if self.chip is None:
                raise flasher.FlashError(f"이 키보드의 칩({chips.name_of(self.keyboard.chip_id)})을 모릅니다")
            info = flasher.check_hex(path, self.chip)
            fid = info.firmware_id
            if fid and fid.chip != self.chip.name:
                raise flasher.FlashError(
                    f"{fid.chip}용 펌웨어입니다 ({fid.board} v{fid.version}). 이 키보드는 {self.chip.name}입니다")
        except flasher.FlashError as e:

            self.size_label.setText(f"✖ {e}")
            self.size_label.setStyleSheet(f"color: {RED};")
            self._refresh()
            return False
        self.hex = info
        pct = info.size * 100 // self.chip.flash_size
        text = f"{info.size} / {self.chip.flash_size}바이트 ({pct}%)"
        warning = self.hex_warning
        if fid:
            text += f" · {fid.board}용 ({fid.chip}) v{fid.version}"
        if warning:
            self.size_label.setText(f"⚠ {text} · {warning}")
            self.size_label.setStyleSheet(f"color: {ORANGE};")
        else:
            self.size_label.setText(f"✔ {text}")
            self.size_label.setStyleSheet(f"color: {GREEN};")
        self._refresh()
        return True

    @property
    def hex_warning(self) -> str:
        """Why the file may not be right for this keyboard ("" when it is)."""
        if self.hex is None:
            return ""
        fid = self.hex.firmware_id
        if fid is None:
            return "식별 정보가 없는 펌웨어 (1.2.x 이하이거나 다른 펌웨어)"
        if fid.board != self.keyboard.name:
            return f"다른 키보드({fid.board})용 펌웨어"
        return ""

    # ------------------------------------------------------------ chips
    def enter_bootloader(self) -> None:
        self._append(self._prepare())
        self.scan()

    def scan(self) -> None:
        if self.running:
            return              # the uploader owns the device now
        try:
            chips_now = self._scan_fn()
            self.scan_error = ""
        except flasher.FlashError as e:
            chips_now = []
            if str(e) != self.scan_error:
                self._append(f"✖ {e}")
            self.scan_error = str(e)
        if chips_now != self.chips or self.chip_table.rowCount() != len(chips_now):
            self.chips = chips_now
            self._show_chips()
        self._refresh()

    def is_this_keyboard(self, chip: bootloader.ChipInfo) -> bool:
        """The chip's unique ID is the one the connected keyboard reported."""
        return bool(self.keyboard.uid) and chip.uid == self.keyboard.uid

    def _show_chips(self) -> None:
        self.chip_table.setRowCount(len(self.chips))
        for row, chip in enumerate(self.chips):
            serial = chip.serial + (" (방금 연결된 키보드)" if self.is_this_keyboard(chip) else "")
            cells = [str(row + 1), chip.part, serial, chip.bootloader or "-"]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                self.chip_table.setItem(row, col, item)
        for chip in self.chips:
            self._append(f"칩 인식: {chip.part} · ID {chip.serial} · 부트로더 {chip.bootloader or '?'}")

    @property
    def target(self) -> bootloader.ChipInfo | None:
        """The one chip [장입] will write, or None when that is not clear."""
        if self._chip_problem() is None:
            return self.chips[0]
        return None

    def _chip_problem(self) -> str | None:
        """Why [장입] cannot write the detected chip, None when it can."""
        if self.scan_error:
            return self.scan_error
        if not self.chips:
            return "업데이트 모드인 칩이 없습니다"
        if len(self.chips) > 1:
            return f"칩이 {len(self.chips)}개 연결되어 있습니다. 장입할 키보드 하나만 남기세요"
        if self.spec is None:
            return (f"보드 목록에 없는 키보드({self.keyboard.name})라서 "
                    "업데이트 모드 진입 설정을 알 수 없습니다. 장입할 수 없습니다")
        found = self.chips[0]
        if self.chip is None or found.chip_id != self.chip.chip_id:
            return f"{found.part}는 이 키보드({self.keyboard.name}, {self.spec.chip_name})의 칩이 아닙니다"
        if not self.chip.supported:
            return f"{self.chip.name}: {self.chip.note}"
        return None

    def _chip_message(self) -> tuple[str, str]:
        problem = self._chip_problem()
        if problem is not None:
            return problem, GREY if not self.chips and not self.scan_error else RED
        if self.is_this_keyboard(self.chips[0]):
            return "장입할 준비가 되었습니다 (방금 연결되어 있던 키보드)", GREEN
        return "장입할 준비가 되었습니다", GREEN

    # ------------------------------------------------------------ state
    @property
    def running(self) -> bool:
        return self.process is not None and self.process.state() != QProcess.NotRunning

    def _refresh(self) -> None:
        text, color = self._chip_message()
        self.chip_status.setText(text)
        self.chip_status.setStyleSheet(f"color: {color};")
        busy = self.running
        self.start_btn.setEnabled(self.hex_size > 0 and self.target is not None and not busy)
        self.browse_btn.setEnabled(not busy)
        self.boot_btn.setEnabled(not busy)
        self.scan_btn.setEnabled(not busy)
        self.close_btn.setText("취소" if busy else "닫기")

    # ------------------------------------------------------------ upload
    def _default_command(self, hex_path: Path) -> list[str]:
        return flasher.build_command(flasher.find_uploader(), hex_path,
                                     self.chip.name, self.spec.boot_config)

    def start(self) -> bool:
        if self.hex_size == 0 or self.target is None or self.running:
            return False
        warning = self.hex_warning
        if warning and not self.confirm(
                "펌웨어 확인",
                f"{warning}입니다.\n이 키보드({self.keyboard.name})에 맞지 않으면 키가 동작하지 않을 수 있습니다.\n"
                f"그래도 장입할까요? (실패해도 {self.boot_hint} 꽂으면 다시 장입할 수 있습니다)"):
            return False
        try:
            command = self._command_fn(Path(self.path_edit.text()))
        except flasher.FlashError as e:
            self._append(f"✖ {e}")
            self.stage_label.setText("업로드 프로그램을 찾을 수 없습니다")
            return False
        chip = self.target
        self.scan_timer.stop()
        self.progress = flasher.FlashProgress()
        self.succeeded = False
        self.bar.setValue(0)
        self.stage_label.setStyleSheet("font-weight: bold;")
        self._append(f"장입 시작: {chip.part} · ID {chip.serial} ← {Path(self.path_edit.text()).name}")
        self.stage_label.setText(flasher.STAGE_TEXT_KO[flasher.STAGE_WAITING])

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_output)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_error)
        self.process.start(command[0], command[1:])
        self._refresh()
        return True

    def _append(self, line: str) -> None:
        self.log.appendPlainText(line)

    def _on_output(self) -> None:
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        before = len(self.progress.lines)
        self.progress.feed(data)
        for line in self.progress.lines[before:]:
            self._append(line)
        self._show_progress()

    def _show_progress(self) -> None:
        prog = self.progress
        text = flasher.STAGE_TEXT_KO[prog.stage]
        if prog.chip:
            text += f" · {prog.chip}"
        if prog.bootloader:
            text += f" (부트로더 {prog.bootloader})"
        self.stage_label.setText(text)
        self.bar.setValue(prog.percent)

    def _on_finished(self, code: int, _status=None) -> None:
        self.progress.finish()
        self._show_progress()
        self.succeeded = code == 0 and self.progress.succeeded
        if self.succeeded:
            self.stage_label.setText(f"✔ 장입 완료 ({self.progress.written}바이트). 키보드가 새 펌웨어로 다시 시작합니다")
            self.stage_label.setStyleSheet(f"font-weight: bold; color: {GREEN};")
        else:
            if self.progress.stage == flasher.STAGE_WAITING:
                reason = (f"{flasher.WAIT_SECONDS}초 안에 칩을 찾지 못했습니다. "
                          f"{self.boot_hint} 다시 꽂고, 칩이 목록에 나타나면 [장입]을 다시 누르세요")
            else:
                reason = (f"장입이 끝나지 않았습니다. 키보드를 뽑았다가 {self.boot_hint} 꽂고 다시 시도하세요 "
                          "(업데이트 모드는 그대로 들어갈 수 있습니다)")
            self.stage_label.setText(f"✖ 실패 (종료 코드 {code}). {reason}")
            self.stage_label.setStyleSheet(f"font-weight: bold; color: {RED};")
        self.scan()
        self.scan_timer.start()
        self._refresh()

    def _on_error(self, error) -> None:
        if error == QProcess.FailedToStart:
            self.stage_label.setText("✖ 업로드 프로그램을 실행할 수 없습니다")
            self.stage_label.setStyleSheet(f"font-weight: bold; color: {RED};")
            self.scan_timer.start()
            self._refresh()

    # ------------------------------------------------------------ closing
    def cancel_or_close(self) -> None:
        if self.running:
            self.process.kill()
            self.process.waitForFinished(2000)
            self._append("사용자가 취소했습니다")
            return
        self.scan_timer.stop()
        self.accept() if self.succeeded else self.reject()

    def closeEvent(self, event) -> None:
        if self.running:
            event.ignore()        # use [취소] so the uploader is stopped first
            return
        self.scan_timer.stop()
        super().closeEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape and self.running:
            return
        super().keyPressEvent(event)
