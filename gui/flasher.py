"""Firmware upload through the CH55x ROM bootloader (same as tools/flash.ps1).

Runs CH55xDuino's vnproch55x uploader and turns its console output into
progress steps for the GUI. Pure Python; the GUI runs the command with QProcess.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import chips

UPLOADER_NAME = "vnproch55x.exe"
WAIT_SECONDS = 60           # how long the uploader waits for the bootloader
MAX_IMAGE = 1 << 20         # larger addresses are not a CH55x firmware


class FlashError(Exception):
    """User-facing Korean message."""


# ---------------------------------------------------------------- uploader

def find_uploader() -> Path:
    """Bundled uploader (exe build), MACROKB_UPLOADER, or CH55xDuino's newest one."""
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(getattr(sys, "_MEIPASS", "")) / "uploader" / UPLOADER_NAME)
    env = os.environ.get("MACROKB_UPLOADER")
    if env:
        candidates.append(Path(env))
    tools = Path(os.environ.get("LOCALAPPDATA", "")) / "Arduino15/packages/CH55xDuino/tools/MCS51Tools"
    if tools.is_dir():
        for version in sorted((d for d in tools.iterdir() if d.is_dir()), reverse=True):
            candidates.append(version / "win" / UPLOADER_NAME)
    for path in candidates:
        if path.is_file():
            return path
    raise FlashError("업로드 프로그램(vnproch55x.exe)을 찾을 수 없습니다. "
                     "Arduino IDE에 CH55xDuino를 설치하거나, 업로더가 포함된 exe를 사용하세요")


def build_command(uploader: Path, hex_path: Path, chip: str, boot_config: int,
                  wait_seconds: int = WAIT_SECONDS) -> list[str]:
    """chip: -t value ("CH552"). boot_config: -c, the bootloader entry pin
    written with the firmware (boards.BOOT_P15 / BOOT_P36). A wrong one makes
    the bootloader unreachable the usual way (docs/TROUBLESHOOTING.md 2-3), so
    it comes from the board list, never from the user."""
    return [str(uploader), "-r", str(wait_seconds), "-t", chip, "-c", str(boot_config), str(hex_path)]


# ---------------------------------------------------------------- hex file

FIRMWARE_ID_PREFIX = b"MKFW1:"


@dataclass(frozen=True)
class FirmwareId:
    """"MKFW1:<board>:<chip>:<version>" that our firmware carries (1.3.0 and later)."""
    board: str
    chip: str
    version: str


@dataclass(frozen=True)
class HexInfo:
    size: int
    firmware_id: FirmwareId | None     # None: older or someone else's firmware


def read_hex(path: str | Path) -> bytes:
    """Code flash image of an Intel HEX file, from address 0 to the highest
    address written (gaps read as 0xFF, like erased flash)."""
    try:
        lines = Path(path).read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        raise FlashError(f"펌웨어 파일을 읽을 수 없습니다: {e}") from e
    base = 0
    records: list[tuple[int, bytes]] = []
    seen_eof = False
    for n, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            raise FlashError(f"Intel HEX 파일이 아닙니다 ({n}번째 줄)")
        try:
            raw = bytes.fromhex(line[1:])
        except ValueError as e:
            raise FlashError(f"HEX 파일이 손상되었습니다 ({n}번째 줄)") from e
        if len(raw) < 5 or len(raw) != raw[0] + 5 or sum(raw) & 0xFF:
            raise FlashError(f"HEX 파일이 손상되었습니다 ({n}번째 줄, 체크섬)")
        count, addr, rtype = raw[0], (raw[1] << 8) | raw[2], raw[3]
        if rtype == 0x00:
            records.append((base + addr, raw[4:4 + count]))
        elif rtype == 0x01:
            seen_eof = True
            break
        elif rtype == 0x02:
            base = ((raw[4] << 8) | raw[5]) << 4
        elif rtype == 0x04:
            base = ((raw[4] << 8) | raw[5]) << 16
    if not seen_eof:
        raise FlashError("HEX 파일이 끝까지 있지 않습니다 (EOF 레코드 없음)")
    end = max((addr + len(data) for addr, data in records), default=0)
    if end == 0:
        raise FlashError("HEX 파일에 데이터가 없습니다")
    if end > MAX_IMAGE:
        raise FlashError(f"CH55x 펌웨어가 아닙니다 (주소 0x{end:X}까지 씀)")
    image = bytearray(b"\xff" * end)
    for addr, data in records:
        image[addr:addr + len(data)] = data
    return bytes(image)


def firmware_id(image: bytes) -> FirmwareId | None:
    start = image.find(FIRMWARE_ID_PREFIX)
    if start < 0:
        return None
    end = image.find(b"\0", start)
    text = image[start + len(FIRMWARE_ID_PREFIX):end if end >= 0 else None]
    parts = text.decode("ascii", errors="replace").split(":")
    if len(parts) != 3 or not all(parts):
        return None
    return FirmwareId(*parts)


def check_hex(path: str | Path, chip: chips.Chip) -> HexInfo:
    """Read the file and check that it fits the chip's flash."""
    image = read_hex(path)
    if len(image) > chip.flash_size:
        raise FlashError(f"펌웨어가 너무 큽니다 ({len(image)}바이트, {chip.name} 최대 {chip.flash_size}바이트)")
    return HexInfo(len(image), firmware_id(image))


def hex_size(path: str | Path) -> int:
    """Bytes of code flash an Intel HEX file uses (highest address + 1)."""
    return len(read_hex(path))


# ---------------------------------------------------------------- output

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

STAGE_WAITING = "waiting"
STAGE_FOUND = "found"
STAGE_WRITING = "writing"
STAGE_VERIFYING = "verifying"
STAGE_DONE = "done"

STAGE_TEXT_KO = {
    STAGE_WAITING: "업데이트 모드(부트로더)를 기다리는 중",
    STAGE_FOUND: "키보드를 찾았습니다",
    STAGE_WRITING: "펌웨어 쓰는 중",
    STAGE_VERIFYING: "검증 중",
    STAGE_DONE: "완료",
}

PROGRESS_DOTS = 50          # the uploader draws up to 50 dots per pass


@dataclass
class FlashProgress:
    """State parsed from the uploader's console output so far."""
    stage: str = STAGE_WAITING
    percent: int = 0            # 0-100 over writing + verifying
    chip: str = ""              # e.g. "CH552"
    bootloader: str = ""        # e.g. "2.5.0"
    written: int = 0            # bytes the uploader reports writing
    verified: bool = False
    reset: bool = False
    lines: list[str] = field(default_factory=list)   # readable log
    _raw: str = ""     # an escape code cut in half by the pipe waits here
    _buf: str = ""     # current line; "\r" marks a redraw (erase code)

    def feed(self, text: str) -> None:
        raw = self._raw + text
        cut = raw.rfind("\x1b")
        if cut != -1 and not ANSI.match(raw, cut):
            raw, self._raw = raw[:cut], raw[cut:]
        else:
            self._raw = ""
        # The progress dots are redrawn after an erase-line code each time
        self._buf += ANSI.sub("\r", raw)
        *done, self._buf = self._buf.split("\n")
        for line in done:
            self._line(line)
        self._dots(self._buf.split("\r")[-1])

    def finish(self) -> None:
        if self._buf:
            self._line(self._buf)
            self._buf = ""

    @property
    def succeeded(self) -> bool:
        return self.verified

    def _dots(self, text: str) -> None:
        dots = text.count(".")
        if self.stage in (STAGE_WRITING, STAGE_VERIFYING) and dots and not text.strip(". "):
            part = min(dots, PROGRESS_DOTS) * 50 // PROGRESS_DOTS
            self.percent = max(self.percent, part + (50 if self.stage == STAGE_VERIFYING else 0))

    def _line(self, line: str) -> None:
        stripped = line.split("\r")[-1].strip() if line.strip("\r. ") == "" else line.replace("\r", "").strip()
        if not stripped:
            return
        if not stripped.strip("."):
            self._dots(stripped)
            return
        if stripped.startswith("No CH55x USB Found"):
            # Repeats every 0.1 s while waiting: log it once
            if self.lines and self.lines[-1].startswith("No CH55x USB Found"):
                return
        self.lines.append(stripped)
        m = re.match(r"Found Device (\S+)", stripped)
        if m:
            self.chip = m.group(1)
            self.stage = STAGE_FOUND
        m = re.match(r"Bootloader:\s*(\S+)", stripped)
        if m:
            self.bootloader = m.group(1)
        m = re.match(r"Write (\d+) bytes", stripped)
        if m:
            self.written = int(m.group(1))
            self.stage = STAGE_WRITING
        if stripped.startswith("Write complete"):
            self.percent = max(self.percent, 50)
        if stripped.startswith("Verify chip"):
            self.stage = STAGE_VERIFYING
        if stripped.startswith("Verify complete"):
            self.verified = True
            self.percent = 100
        if stripped.startswith("Reset OK"):
            self.reset = True
            self.stage = STAGE_DONE
