"""JSON backup of the slot strings (format documented in gui/README.md)."""
from __future__ import annotations

import json
from pathlib import Path

from . import protocol as p
from .macro import normalize_newlines

FORMAT_NAME = "usb-mini-keyboard-6k1n"
FORMAT_VERSION = 1


class BackupError(ValueError):
    pass


def to_json(slots: list[str], board: p.Board = p.DEFAULT_BOARD) -> str:
    doc = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "board": {"name": board.name, "keys": board.keys, "knobs": board.knobs},
        "slots": [
            {"slot": i, "key": board.slot_name(i), "label": board.slot_label(i), "macro": text}
            for i, text in enumerate(slots)
        ],
    }
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def from_json(text: str, board: p.Board = p.DEFAULT_BOARD) -> list[str]:
    return read_json(text, board)[0]


def read_json(text: str, board: p.Board = p.DEFAULT_BOARD) -> tuple[list[str], list[str]]:
    """Slots for this board, and the keys of entries it has no slot for.

    Entries are matched by their "key" name (A, B, …, CW, CCW, PRESS), so a
    backup of another keyboard keeps whatever slots both have. Files without
    names fall back to the slot number.
    """
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        raise BackupError(f"JSON 형식이 올바르지 않습니다: {e}") from e
    if not isinstance(doc, dict) or doc.get("format") != FORMAT_NAME:
        raise BackupError("이 프로그램의 백업 파일이 아닙니다 (format 값 불일치)")
    if doc.get("version") != FORMAT_VERSION:
        raise BackupError(f"지원하지 않는 백업 버전입니다 ({doc.get('version')})")
    entries = doc.get("slots")
    if not isinstance(entries, list):
        raise BackupError("slots 목록이 없습니다")
    names = board.slot_names
    slots = [""] * board.slot_count
    skipped: list[str] = []
    for pos, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("macro"), str):
            raise BackupError(f"slots[{pos}] 항목에 macro 문자열이 없습니다")
        key = entry.get("key")
        if isinstance(key, str):
            if key not in names:
                skipped.append(key)
                continue
            idx = names.index(key)
        else:
            idx = entry.get("slot", pos)
            if not isinstance(idx, int) or idx < 0:
                raise BackupError(f"slots[{pos}]의 slot 번호가 올바르지 않습니다 ({idx})")
            if idx >= board.slot_count:
                skipped.append(f"#{idx}")
                continue
        slots[idx] = normalize_newlines(entry["macro"])
    return slots, skipped


def save(path: str | Path, slots: list[str], board: p.Board = p.DEFAULT_BOARD) -> None:
    Path(path).write_text(to_json(slots, board), encoding="utf-8")


def load(path: str | Path, board: p.Board = p.DEFAULT_BOARD) -> tuple[list[str], list[str]]:
    """Slots and skipped keys, as read_json."""
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as e:
        raise BackupError(f"파일을 읽을 수 없습니다: {e}") from e
    return read_json(text, board)
