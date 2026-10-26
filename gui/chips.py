"""Chips the firmware update knows (docs/BOARD_INFO.md 4).

Looked up by the chip ID the bootloader's Detect reports (also HELLO byte 18).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chip:
    chip_id: int
    name: str            # e.g. "CH552", also vnproch55x's -t value
    flash_size: int      # code flash usable by firmware (bootloader above)
    supported: bool      # this firmware is built and tested for it
    note: str = ""       # why it is not supported


CHIPS = {c.chip_id: c for c in (
    Chip(0x51, "CH551", 10240, False, "펌웨어 미지원 (USB 버퍼를 줄여야 함)"),
    Chip(0x52, "CH552", 14336, True),
    Chip(0x54, "CH554", 14336, False, "확인하지 않은 칩"),
)}


def find(chip_id: int) -> Chip | None:
    return CHIPS.get(chip_id)


def name_of(chip_id: int) -> str:
    chip = find(chip_id)
    return chip.name if chip else f"CH5{chip_id & 0x7F:02X}" if chip_id else "알 수 없음"
