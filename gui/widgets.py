"""Reusable widgets: device picture (slot selector) and the macro editor."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu,
    QPlainTextEdit, QPushButton, QSizePolicy, QTextEdit, QToolButton,
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
    """2x3 keys plus a knob with three actions; clicking selects a slot."""

    slotSelected = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFrameShape(QFrame.StyledPanel)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: list[QPushButton] = []

        keys = QGridLayout()
        keys.setSpacing(8)
        for slot in range(6):
            btn = self._make_button(slot)
            btn.setMinimumSize(96, 72)
            keys.addWidget(btn, slot // 3, slot % 3)

        knob_box = QVBoxLayout()
        knob = QLabel("노브")
        knob.setAlignment(Qt.AlignCenter)
        knob.setFixedSize(72, 72)
        knob.setStyleSheet("border: 3px solid palette(mid); border-radius: 36px; font-weight: bold;")
        knob_box.addWidget(knob, 0, Qt.AlignHCenter)
        for slot in (p.SLOT_KNOB_CW, p.SLOT_KNOB_CCW, p.SLOT_KNOB_PRESS):
            btn = self._make_button(slot)
            btn.setMinimumWidth(150)
            knob_box.addWidget(btn)
        knob_box.addStretch(1)

        row = QHBoxLayout(self)
        row.addLayout(keys, 3)
        row.addSpacing(16)
        row.addLayout(knob_box, 1)

        self.group.idClicked.connect(self.slotSelected)
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
        name = p.SLOT_NAMES[slot] if slot < 6 else {
            p.SLOT_KNOB_CW: "↻ 시계 방향",
            p.SLOT_KNOB_CCW: "↺ 반시계 방향",
            p.SLOT_KNOB_PRESS: "● 누르기",
        }[slot]
        mark = " *" if modified else ""
        preview = _preview(text) if text else "(비어 있음)"
        btn = self.buttons[slot]
        btn.setText(f"{name}{mark}\n{preview}")
        btn.setToolTip(f"{p.SLOT_LABELS_KO[slot]}{' (저장 안 됨)' if modified else ''}")
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
        self.title.setText(f"{p.SLOT_LABELS_KO[slot]} 편집")
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
