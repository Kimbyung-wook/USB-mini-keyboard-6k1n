"""JSON backup of the nine slot strings (format documented in gui/README.md)."""
from __future__ import annotations

import json
from pathlib import Path

from . import protocol as p
from .macro import normalize_newlines

FORMAT_NAME = "usb-mini-keyboard-6k1n"
FORMAT_VERSION = 1


class BackupError(ValueError):
    pass


def to_json(slots: list[str]) -> str:
    doc = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "slots": [
            {"slot": i, "key": p.SLOT_NAMES[i], "label": p.SLOT_LABELS_KO[i], "macro": text}
            for i, text in enumerate(slots)
        ],
    }
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


def from_json(text: str) -> list[str]:
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
    slots = [""] * p.SLOT_COUNT
    for pos, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("macro"), str):
            raise BackupError(f"slots[{pos}] 항목에 macro 문자열이 없습니다")
        idx = entry.get("slot", pos)
        if not isinstance(idx, int) or not 0 <= idx < p.SLOT_COUNT:
            raise BackupError(f"slots[{pos}]의 slot 번호가 올바르지 않습니다 ({idx})")
        slots[idx] = normalize_newlines(entry["macro"])
    return slots


def save(path: str | Path, slots: list[str]) -> None:
    Path(path).write_text(to_json(slots), encoding="utf-8")


def load(path: str | Path) -> list[str]:
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError as e:
        raise BackupError(f"파일을 읽을 수 없습니다: {e}") from e
    return from_json(text)
