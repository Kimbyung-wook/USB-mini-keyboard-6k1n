"""Boards the GUI knows (docs/BOARD_INFO.md 5-1).

One entry per keyboard product (PCB), named like the firmware's board file
(firmware/macro_keyboard/src/boards/<name>.h). HELLO's board info is what the
keyboard really is; this list is for when no firmware of ours answers, such as
in the bootloader: which uploader settings to use and how to get there.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import chips
from .protocol import Board

# vnproch55x -c: the bootloader entry pin written with the firmware
BOOT_P15 = 1        # P1.5 pull-down: hold the key on P1.5 while plugging in
BOOT_P36 = 3        # P3.6 (USB D+) pull-up, CH55xDuino's default


@dataclass(frozen=True)
class BoardSpec:
    name: str              # HELLO bytes 24-31, also in the firmware ID
    description: str
    layout: Board          # keys, knobs, rows and chip as HELLO reports them
    boot_config: int       # BOOT_P15 or BOOT_P36
    boot_key: str = ""     # the key on the entry pin, e.g. "D" (BOOT_P15)

    @property
    def chip(self) -> chips.Chip | None:
        return chips.find(self.layout.chip_id)

    @property
    def chip_name(self) -> str:
        return chips.name_of(self.layout.chip_id)

    @property
    def firmware_file(self) -> str:
        """What tools/build_fw.ps1 writes for this board."""
        return f"macro_keyboard-{self.name}.hex"

    @property
    def boot_hint(self) -> str:
        """How to plug it in to reach the bootloader, e.g. "키 D를 누른 채"."""
        if not self.boot_key:
            return "업데이트 모드 단추를 누른 채"
        # L, M, N, R end in a consonant when read aloud (엘, 엠, 엔, 알)
        return f"키 {self.boot_key}{'을' if self.boot_key[-1] in 'LMNR' else '를'} 누른 채"


BOARDS = (
    BoardSpec("MK6K1N", "6키 + 노브 1개 (CH552G)",
              Board(keys=6, knobs=1, rows=2, name="MK6K1N", chip_id=0x52),
              boot_config=BOOT_P15, boot_key="D"),
)


def find(name: str) -> BoardSpec | None:
    for spec in BOARDS:
        if spec.name == name:
            return spec
    return None
