"""Reusable widgets: device picture (slot selector), macro editor, lock pattern editor."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QMenu,
    QPlainTextEdit, QPushButton, QSizePolicy, QSpinBox, QTextEdit, QToolButton,
    QVBoxLayout, QWidget,
)

from . import macro
from . import protocol as p

SYNTAX_HELP = (
    "<b>매크로 문법</b><br>"
    "일반 문자: 영문·숫자·기호(ASCII)를 그대로 입력 &nbsp;·&nbsp; 줄바꿈 = {ENTER}<br>"
    "특수 키: {ENTER} {TAB} {ESC} {BS} {DEL} {SPACE} {UP} {DOWN} {LEFT} {RIGHT} "
    "{HOME} {END} {PGUP} {PGDN} {INS} {F1}~{F12}<br>"
    "조합키: {CTRL+C} {ALT+F4} {WIN+R} {CTRL+SHIFT+ESC} (수식키 CTRL/SHIFT/ALT/WIN)<br>"
    "대기: {DELAY:100} (1~10000 ms) &nbsp;·&nbsp; 중괄호 문자: {{ → {, }} → }<br>"
    "대소문자 구분 없음. 한글 등 ASCII가 아닌 문자는 입력할 수 없습니다(US 배열 기준)."
)


def _preview(text: str, limit: int = 12) -> str:
    one_line = text.replace("\n", "⏎")
    return one_line if len(one_line) <= limit else one_line[:limit - 1] + "…"


class DeviceView(QFrame):
    """The keyboard's keys in rows plus each knob with its three actions;
    clicking selects a slot. Rebuilt by set_board for another keyboard."""

    slotSelected = Signal(int)

    def __init__(self, parent: QWidget | None = None, board: p.Board = p.DEFAULT_BOARD):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.group.idClicked.connect(self.slotSelected)
        self.buttons: list[QPushButton] = []
        self.board = board
        self._layout = QHBoxLayout(self)
        self._body: QWidget | None = None
        self.set_board(board)

    def set_board(self, board: p.Board) -> None:
        if self._body is not None and board == self.board:
            return
        self.board = board
        if self._body is not None:
            for btn in self.buttons:
                self.group.removeButton(btn)
            self._layout.removeWidget(self._body)
            self._body.setParent(None)    # gone from the screen now, not at the next event loop
            self._body.deleteLater()
        self.buttons = []
        self._body = QWidget()
        row = QHBoxLayout(self._body)
        row.setContentsMargins(0, 0, 0, 0)

        keys = QGridLayout()
        keys.setSpacing(8)
        small = board.keys > 9
        for slot in range(board.keys):
            btn = self._make_button(slot)
            btn.setMinimumSize(*((72, 56) if small else (96, 72)))
            keys.addWidget(btn, slot // board.cols, slot % board.cols)
        row.addLayout(keys, 3)

        for n in range(board.knobs):
            knob_box = QVBoxLayout()
            knob = QLabel("노브" if board.knobs == 1 else f"노브 {n + 1}")
            knob.setAlignment(Qt.AlignCenter)
            knob.setFixedSize(72, 72)
            knob.setStyleSheet("border: 3px solid palette(mid); border-radius: 36px; font-weight: bold;")
            knob_box.addWidget(knob, 0, Qt.AlignHCenter)
            for action in range(3):
                btn = self._make_button(board.knob_slot(n, action))
                btn.setMinimumWidth(150)
                knob_box.addWidget(btn)
            knob_box.addStretch(1)
            row.addSpacing(16)
            row.addLayout(knob_box, 1)

        self._layout.addWidget(self._body)
        self.buttons[0].setChecked(True)

    def _make_button(self, slot: int) -> QPushButton:
        btn = QPushButton()
        btn.setCheckable(True)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.group.addButton(btn, slot)
        self.buttons.append(btn)
        return btn

    def select(self, slot: int) -> None:
        self.buttons[slot].setChecked(True)

    def update_slot(self, slot: int, text: str, modified: bool, has_error: bool) -> None:
        knob = self.board.knob_of(slot)
        if knob is None:
            name = self.board.key_name(slot)
        else:
            name = f"{p.KNOB_SYMBOLS[knob[1]]} {p.KNOB_ACTIONS_KO[knob[1]]}"
        mark = " *" if modified else ""
        preview = _preview(text) if text else "(비어 있음)"
        length = macro.stored_length(text)  # bytes it takes in the device, macro text included
        btn = self.buttons[slot]
        btn.setText(f"{name}{mark} · {length}자\n{preview}")
        btn.setToolTip(f"{self.board.slot_label(slot)} · {length}자"
                       f"{' (저장 안 됨)' if modified else ''}")
        font = btn.font()
        font.setBold(modified)
        btn.setFont(font)
        btn.setStyleSheet("color: #c62828;" if has_error else "")


class MacroEditor(QWidget):
    """Multi-line editor with live validation, highlighting and insert helpers."""

    textEdited = Signal(str)

    INSERTS = ["{ENTER}", "{TAB}", "{ESC}", "{BS}", "{DELAY:100}", "{{", "}}"]
    COMBOS = ["{CTRL+C}", "{CTRL+V}", "{CTRL+X}", "{CTRL+Z}", "{CTRL+A}", "{CTRL+S}",
              "{CTRL+SHIFT+ESC}", "{ALT+TAB}", "{ALT+F4}", "{WIN+R}", "{WIN+D}", "{WIN+E}"]

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.title = QLabel()
        self.title.setStyleSheet("font-weight: bold; font-size: 14px;")

        self.edit = QPlainTextEdit()
        self.edit.setTabChangesFocus(True)
        mono = QFont("Consolas")
        mono.setStyleHint(QFont.Monospace)
        mono.setPointSize(11)
        self.edit.setFont(mono)
        self.edit.setPlaceholderText("예: Hello world{ENTER}  또는  {CTRL+C}")
        self.edit.textChanged.connect(self._on_changed)

        tools = QHBoxLayout()
        tools.setSpacing(4)
        for snippet in self.INSERTS:
            b = QToolButton()
            b.setText(snippet)
            b.clicked.connect(lambda _=False, s=snippet: self.insert(s))
            tools.addWidget(b)
        tools.addWidget(self._menu_button("조합키 ▾", self.COMBOS))
        tools.addWidget(self._menu_button("특수 키 ▾", [f"{{{k}}}" for k in macro.KEY_NAMES]))
        tools.addStretch(1)

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)

        help_label = QLabel(SYNTAX_HELP)
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.title)
        lay.addLayout(tools)
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.status)
        lay.addWidget(help_label)

        self.errors: list[macro.MacroError] = []
        self._loading = False
        self.board = p.DEFAULT_BOARD     # for slot labels; set by the main window

    def _menu_button(self, label: str, items: list[str]) -> QToolButton:
        b = QToolButton()
        b.setText(label)
        b.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(b)
        for item in items:
            menu.addAction(item, lambda s=item: self.insert(s))
        b.setMenu(menu)
        return b

    def set_slot(self, slot: int, text: str) -> None:
        self.title.setText(f"{self.board.slot_label(slot)} 편집")
        self._loading = True
        try:
            self.edit.setPlainText(text)
            self.edit.moveCursor(QTextCursor.End)
        finally:
            self._loading = False
        self._validate()

    def text(self) -> str:
        return self.edit.toPlainText()

    def insert(self, snippet: str) -> None:
        self.edit.insertPlainText(snippet)
        self.edit.setFocus()

    def _on_changed(self) -> None:
        self._validate()
        if not self._loading:
            self.textEdited.emit(self.text())

    def _validate(self) -> None:
        text = self.text()
        result = macro.parse(text)
        self.errors = result.errors
        selections = []
        fmt = QTextCharFormat()
        fmt.setBackground(QColor(255, 205, 210))
        fmt.setUnderlineStyle(QTextCharFormat.WaveUnderline)
        fmt.setUnderlineColor(QColor("#c62828"))
        last = max(self.edit.document().characterCount() - 1, 0)
        for err in result.errors:
            sel = QTextEdit.ExtraSelection()
            sel.format = fmt
            cur = QTextCursor(self.edit.document())
            cur.setPosition(min(err.start, last))
            cur.setPosition(min(max(err.end, err.start + 1), last), QTextCursor.KeepAnchor)
            sel.cursor = cur
            selections.append(sel)
        self.edit.setExtraSelections(selections)

        if result.ok:
            self.status.setStyleSheet("color: #2e7d32;")
            self.status.setText(f"✔ 문법 정상 · {result.byte_length}바이트")
        else:
            lines = []
            for err in result.errors[:5]:
                line = text.count("\n", 0, err.start) + 1
                col = err.start - (text.rfind("\n", 0, err.start) + 1) + 1
                lines.append(f"• {line}행 {col}열: {err.message}")
            if len(result.errors) > 5:
                lines.append(f"… 외 {len(result.errors) - 5}개 오류")
            self.status.setStyleSheet("color: #c62828;")
            self.status.setText("\n".join(lines))


# (topic, explanation) rows of the help under the pattern buttons
LOCK_HELP = (
    ("꽂으면", "잠김 (LED 꺼짐, 가끔 빨강 깜빡) · 키를 눌러도 반응 없음 · GUI 읽기·테스트 입력 안 됨"),
    ("풀기", "노브 2초 → 빨강 켜짐 → 패턴 입력 → 파랑"),
    ("다시 잠그기", "풀린 상태에서 노브 2초 → 같은 패턴 (5번 틀려도 잠김)"),
    ("자동 잠금", "풀린 뒤 정한 시간 동안 입력이 없으면 잠김 (0분 = 안 함)"),
    ("5번 틀리면", "빨강이 계속 깜빡이고 입력을 막음 → 다시 꽂기"),
    ("비워 두면", "잠금을 쓰지 않음"),
)


def help_table(rows: tuple[tuple[str, str], ...]) -> str:
    cells = "".join(f"<tr><td style='padding-right: 8px;'><b>{topic}</b></td><td>{text}</td></tr>"
                    for topic, text in rows)
    return f"<table cellspacing='0' cellpadding='1'>{cells}</table>"

AUTOLOCK_HELP = (
    "풀린 뒤 키/노브 입력과 GUI 작업(읽기·저장·테스트 입력)이 이 시간 동안 없으면 저절로 잠깁니다. "
    "0분이면 자동으로 잠그지 않습니다. 패턴 암호가 있을 때만 쓰이고, 펌웨어 1.4.0 이상이 필요합니다."
)


class LockPatternEditor(QGroupBox):
    """Builds the lock pattern from the keyboard's key/knob inputs."""

    patternChanged = Signal(list)
    autolockChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None, board: p.Board = p.DEFAULT_BOARD):
        super().__init__("패턴 암호", parent)
        self.steps: list[int] = []
        self.board = board
        self.autolock_supported = True

        self.display = QLabel()
        self.display.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.status = QLabel()

        inputs = QHBoxLayout()
        inputs.setSpacing(4)
        inputs.addWidget(QLabel("추가:"))
        self._inputs = inputs
        self.input_buttons: list[QToolButton] = []
        self._make_inputs()
        self.back_btn = QToolButton()
        self.back_btn.setText("⌫ 한 칸 지우기")
        self.back_btn.clicked.connect(self.remove_last)
        self.clear_btn = QToolButton()
        self.clear_btn.setText("모두 지우기")
        self.clear_btn.clicked.connect(lambda: self._set(self.steps[:0]))
        inputs.addSpacing(8)
        inputs.addWidget(self.back_btn)
        inputs.addWidget(self.clear_btn)
        inputs.addStretch(1)

        top = QHBoxLayout()
        top.addWidget(self.display)
        top.addStretch(1)
        top.addWidget(self.status)

        help_label = QLabel(help_table(LOCK_HELP))
        help_label.setTextFormat(Qt.RichText)
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")

        self.autolock_spin = QSpinBox()
        self.autolock_spin.setRange(0, p.AUTOLOCK_MAX_MINUTES)
        self.autolock_spin.setSuffix("분")
        self.autolock_spin.setSpecialValueText("0분 (끔)")
        self.autolock_spin.setToolTip(AUTOLOCK_HELP)
        self.autolock_spin.valueChanged.connect(self.autolockChanged.emit)
        self.autolock_note = QLabel()
        self.autolock_note.setWordWrap(True)
        self.autolock_note.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
        autolock = QHBoxLayout()
        autolock.addWidget(QLabel("자동 잠금:"))
        autolock.addWidget(self.autolock_spin)
        autolock.addWidget(self.autolock_note, 1)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addLayout(inputs)
        lay.addLayout(autolock)
        lay.addWidget(help_label)
        self._refresh()

    def _make_inputs(self) -> None:
        for slot in range(self.board.slot_count):
            b = QToolButton()
            b.setText(self.board.step_name(slot))
            b.setToolTip(self.board.slot_label(slot))
            b.setMinimumWidth(32)
            b.clicked.connect(lambda _=False, s=slot: self.add_step(s))
            self._inputs.insertWidget(1 + slot, b)    # after the "추가:" label
            self.input_buttons.append(b)

    def set_board(self, board: p.Board) -> None:
        """One input button per slot of this keyboard; the pattern is cleared."""
        if board == self.board:
            return
        self.board = board
        for b in self.input_buttons:
            self._inputs.removeWidget(b)
            b.setParent(None)
            b.deleteLater()
        self.input_buttons = []
        self._make_inputs()
        self.set_pattern([])

    def pattern(self) -> list[int]:
        return list(self.steps)

    def set_pattern(self, steps: list[int]) -> None:
        """Show a pattern without emitting patternChanged."""
        self.steps = list(steps)
        self._refresh()

    def set_modified(self, modified: bool) -> None:
        self.setTitle("패턴 암호 *" if modified else "패턴 암호")

    def autolock(self) -> int:
        return self.autolock_spin.value()

    def set_autolock(self, minutes: int) -> None:
        """Show the auto-lock minutes without emitting autolockChanged."""
        self.autolock_spin.blockSignals(True)
        self.autolock_spin.setValue(minutes)
        self.autolock_spin.blockSignals(False)
        self._refresh()

    def set_autolock_supported(self, supported: bool) -> None:
        self.autolock_supported = supported
        self._refresh()

    def add_step(self, slot: int) -> None:
        if len(self.steps) < p.LOCK_MAX_STEPS:
            self._set(self.steps + [slot])

    def remove_last(self) -> None:
        self._set(self.steps[:-1])

    def _set(self, steps: list[int]) -> None:
        self.steps = steps
        self._refresh()
        self.patternChanged.emit(self.pattern())

    def _refresh(self) -> None:
        n = len(self.steps)
        self.display.setText(p.lock_text(self.steps, self.board) if n else "(없음 · 잠금 안 씀)")
        err = p.lock_error(self.steps, self.board)
        if err:
            self.status.setStyleSheet("color: #c62828;")
            self.status.setText(f"{n}단계 · {p.LOCK_MIN_STEPS}단계 이상 필요")
        elif n:
            used = 2 + n + (3 if self.autolock() else 0)
            self.status.setStyleSheet("color: #2e7d32;")
            self.status.setText(f"✔ {n}단계 · {used}바이트 사용")
        else:
            self.status.setStyleSheet("")
            self.status.setText(f"{p.LOCK_MIN_STEPS}~{p.LOCK_MAX_STEPS}단계")
        full = n >= p.LOCK_MAX_STEPS
        for b in self.input_buttons:
            b.setEnabled(not full)
        self.back_btn.setEnabled(n > 0)
        self.clear_btn.setEnabled(n > 0)
        # Without a pattern there is nothing to lock
        self.autolock_spin.setEnabled(self.autolock_supported and n > 0)
        if not self.autolock_supported:
            self.autolock_note.setText("이 펌웨어는 자동 잠금을 지원하지 않습니다 (펌웨어 1.4.0 이상 필요)")
        elif not n:
            self.autolock_note.setText("패턴 암호를 정하면 쓸 수 있습니다")
        elif self.autolock():
            self.autolock_note.setText(f"입력이 {self.autolock()}분 동안 없으면 잠급니다 (3바이트 사용)")
        else:
            self.autolock_note.setText("자동으로 잠그지 않습니다")
