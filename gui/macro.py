"""Macro syntax parser / validator (see "매크로 문법" in docs/PROTOCOL.md).

The device stores the raw macro text and interprets it when typing, so the GUI
only needs to validate it and report errors with character positions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

DELAY_MIN = 1
DELAY_MAX = 10000

MODIFIERS = ("CTRL", "SHIFT", "ALT", "WIN")
KEY_NAMES = (
    "ENTER", "TAB", "ESC", "BS", "DEL", "SPACE",
    "UP", "DOWN", "LEFT", "RIGHT", "HOME", "END", "PGUP", "PGDN", "INS",
    *(f"F{i}" for i in range(1, 13)),
)


@dataclass(frozen=True)
class MacroError:
    start: int     # index of first offending character
    end: int       # index one past the last offending character
    message: str


@dataclass(frozen=True)
class Token:
    kind: str      # "char" | "key" | "delay" | "combo"
    value: str     # char itself, key name, delay ms as text, or "CTRL+SHIFT+ESC"
    start: int
    end: int


@dataclass
class ParseResult:
    tokens: list[Token] = field(default_factory=list)
    errors: list[MacroError] = field(default_factory=list)
    byte_length: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors


def stored_length(text: str) -> int:
    """Number of bytes the text occupies in the blob (ASCII, one byte per char)."""
    return len(text.encode("ascii", errors="replace"))


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _is_printable(ch: str) -> bool:
    return 0x20 <= ord(ch) <= 0x7E


def _parse_braced(content: str, start: int, end: int) -> Token | MacroError:
    """Interpret the text between '{' and '}' (start/end cover the braces)."""
    def err(msg: str) -> MacroError:
        return MacroError(start, end, msg)

    for i, ch in enumerate(content):
        if not _is_printable(ch):
            pos = start + 1 + i
            return MacroError(pos, pos + 1, f"중괄호 안에 허용되지 않는 문자 '{ch}'가 있습니다")
    if not content:
        return err("빈 중괄호 {}는 쓸 수 없습니다. 문자 {를 입력하려면 {{ 를 쓰세요")

    upper = content.upper()
    if upper.startswith("DELAY"):
        if not upper.startswith("DELAY:"):
            return err("DELAY는 {DELAY:밀리초} 형식으로 씁니다 (예: {DELAY:100})")
        num = content[6:]
        if not num.isdigit():
            return err(f"DELAY 값 '{num}'이(가) 숫자가 아닙니다")
        ms = int(num)
        if not DELAY_MIN <= ms <= DELAY_MAX:
            return err(f"DELAY 값은 {DELAY_MIN}~{DELAY_MAX} 사이여야 합니다 (현재 {ms})")
        return Token("delay", str(ms), start, end)

    if "+" in content and content != "+":
        # "{CTRL++}" means CTRL + the '+' character.
        if content.endswith("++"):
            mods, key = content[:-2].split("+"), "+"
        else:
            *mods, key = content.split("+")
        for m in mods:
            if not m:
                return err("수식키 이름이 비어 있습니다 (예: {CTRL+C})")
            if m.upper() not in MODIFIERS:
                return err(f"알 수 없는 수식키 '{m}' (사용 가능: {', '.join(MODIFIERS)})")
        if not key:
            return err("조합키 뒤에 누를 키가 없습니다 (예: {CTRL+C})")
        if key.upper() in MODIFIERS:
            return err(f"'{key}'는 수식키입니다. 마지막에는 일반 키를 써야 합니다 (예: {{CTRL+SHIFT+ESC}})")
        if len(key) != 1 and key.upper() not in KEY_NAMES:
            return err(f"알 수 없는 키 이름 '{key}'")
        if len(key) == 1:
            key_text = key.upper() if key.isalpha() else key
        else:
            key_text = key.upper()
        return Token("combo", "+".join([m.upper() for m in mods] + [key_text]), start, end)

    if upper in KEY_NAMES:
        return Token("key", upper, start, end)
    if upper in MODIFIERS:
        return err(f"수식키 '{content}'만 단독으로 쓸 수 없습니다 (예: {{{upper}+C}})")
    return err(f"알 수 없는 키 이름 '{content}'")


def parse(text: str) -> ParseResult:
    result = ParseResult(byte_length=stored_length(text))
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "{":
            if i + 1 < n and text[i + 1] == "{":
                result.tokens.append(Token("char", "{", i, i + 2))
                i += 2
                continue
            # Find the closing brace; a newline or another '{' means it's unclosed.
            j = i + 1
            while j < n and text[j] not in "{}\n":
                j += 1
            if j >= n or text[j] != "}":
                result.errors.append(MacroError(i, j, "닫히지 않은 중괄호 { 입니다. 문자 {를 입력하려면 {{ 를 쓰세요"))
                i = j
                continue
            item = _parse_braced(text[i + 1:j], i, j + 1)
            (result.errors if isinstance(item, MacroError) else result.tokens).append(item)
            i = j + 1
        elif ch == "}":
            if i + 1 < n and text[i + 1] == "}":
                result.tokens.append(Token("char", "}", i, i + 2))
                i += 2
            else:
                result.errors.append(MacroError(i, i + 1, "짝이 없는 } 입니다. 문자 }를 입력하려면 }} 를 쓰세요"))
                i += 1
        elif ch == "\n":
            result.tokens.append(Token("key", "ENTER", i, i + 1))
            i += 1
        elif _is_printable(ch):
            result.tokens.append(Token("char", ch, i, i + 1))
            i += 1
        else:
            # Group a run of disallowed characters (e.g. a Korean word) into one error.
            j = i
            while j < n and text[j] != "\n" and not _is_printable(text[j]):
                j += 1
            bad = text[i:j]
            if all(ord(c) < 0x80 for c in bad):
                msg = "제어 문자는 쓸 수 없습니다"
            else:
                msg = f"ASCII가 아닌 문자 '{bad}'는 쓸 수 없습니다 (한글 등 미지원, 영문 배열 기준)"
            result.errors.append(MacroError(i, j, msg))
            i = j
    return result


def validate(text: str) -> list[MacroError]:
    return parse(text).errors
