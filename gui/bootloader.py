"""Find CH55x chips waiting in the ROM bootloader and read their part number and ID.

Talks to the bootloader through WCH's driver DLL (CH375DLL64.dll, installed
with the driver flash.ps1 / the uploader need anyway). Only the read-only
Detect (0xA1) and ReadConfig (0xA7) commands are sent, as ch55xtool and
vnproch55x do before they write anything, so scanning never changes the chip.
"""
from __future__ import annotations

import ctypes
import struct
import sys
from dataclasses import dataclass

from .flasher import FlashError

DLL_NAME = "CH375DLL64.dll" if struct.calcsize("P") == 8 else "CH375DLL.dll"
MAX_DEVICES = 8              # WCH driver indexes to try (it supports 16)
TIMEOUT_MS = 300
BOOT_IDS = {(0x4348, 0x55E0), (0x1A86, 0x55E0)}

CMD_DETECT = 0xA1
CMD_READ_CONFIG = 0xA7
DETECT_PAYLOAD = b"\x42\x10" + b"MCU ISP & WCH.CN"
FIELD_BOOTVER = 0x08
FIELD_UID = 0x10


@dataclass(frozen=True)
class ChipInfo:
    index: int           # WCH driver device index
    chip_id: int         # 0x52 for CH552
    sub_id: int          # 0x11 for the CH55x family
    bootloader: str      # "2.5.0"
    uid: bytes           # chip unique ID (4 bytes on CH551/552/554)

    @property
    def part(self) -> str:
        return f"CH5{self.chip_id & 0x7F:02X}" if self.chip_id else "알 수 없음"

    @property
    def serial(self) -> str:
        return "-".join(f"{b:02X}" for b in self.uid) if self.uid else "-"


def packet(cmd: int, payload: bytes) -> bytes:
    return bytes([cmd]) + len(payload).to_bytes(2, "little") + payload


def reply_payload(cmd: int, reply: bytes) -> bytes | None:
    """Payload of a bootloader reply (cmd, status, len16, payload), None if not ours."""
    if len(reply) < 4 or reply[0] != cmd:
        return None
    n = int.from_bytes(reply[2:4], "little")
    return reply[4:4 + n] if len(reply) >= 4 + n else None


def parse_detect(reply: bytes) -> tuple[int, int] | None:
    pl = reply_payload(CMD_DETECT, reply)
    if pl is None or len(pl) != 2:
        return None
    return pl[0], pl[1]


def parse_config(reply: bytes, chip_id: int, sub_id: int) -> tuple[str, bytes]:
    """(bootloader version, UID) from a ReadConfig reply for BOOTVER|UID."""
    pl = reply_payload(CMD_READ_CONFIG, reply)
    if pl is None or len(pl) < 2 + 4 + 4:
        return "", b""
    ver = pl[2:6]
    uid_len = 4 if sub_id == 0x11 and chip_id not in (0x55, 0x56, 0x57) else 8
    uid = bytes(pl[6:6 + uid_len])
    return f"{ver[1]}.{ver[2]}.{ver[3]}", uid


class WchDriver:
    """Thin ctypes wrapper over the WCH CH375 driver DLL."""

    def __init__(self):
        if sys.platform != "win32":
            raise FlashError("칩 검색은 Windows에서만 지원합니다")
        try:
            dll = ctypes.WinDLL(DLL_NAME)
        except OSError as e:
            raise FlashError(f"WCH 드라이버({DLL_NAME})가 없습니다. "
                             "업데이트 모드용 드라이버를 설치하세요 (docs/TROUBLESHOOTING.md)") from e
        dll.CH375OpenDevice.restype = ctypes.c_void_p
        dll.CH375OpenDevice.argtypes = [ctypes.c_ulong]
        dll.CH375CloseDevice.argtypes = [ctypes.c_ulong]
        dll.CH375GetUsbID.restype = ctypes.c_ulong
        dll.CH375GetUsbID.argtypes = [ctypes.c_ulong]
        dll.CH375SetTimeout.argtypes = [ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
        for name in ("CH375WriteData", "CH375ReadData"):
            fn = getattr(dll, name)
            fn.restype = ctypes.c_int
            fn.argtypes = [ctypes.c_ulong, ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        self.dll = dll

    def open(self, index: int) -> bool:
        handle = self.dll.CH375OpenDevice(index)
        if handle is None or handle == ctypes.c_void_p(-1).value:
            return False
        self.dll.CH375SetTimeout(index, TIMEOUT_MS, TIMEOUT_MS)
        return True

    def close(self, index: int) -> None:
        self.dll.CH375CloseDevice(index)

    def usb_id(self, index: int) -> tuple[int, int]:
        v = self.dll.CH375GetUsbID(index)
        return v & 0xFFFF, v >> 16

    def transfer(self, index: int, data: bytes) -> bytes:
        n = ctypes.c_ulong(len(data))
        buf = ctypes.create_string_buffer(data, len(data))
        if not self.dll.CH375WriteData(index, buf, ctypes.byref(n)):
            return b""
        out = ctypes.create_string_buffer(64)
        n = ctypes.c_ulong(64)
        if not self.dll.CH375ReadData(index, out, ctypes.byref(n)):
            return b""
        return out.raw[:n.value]


def scan(driver=None) -> list[ChipInfo]:
    """Every chip in the bootloader right now (empty list when none)."""
    driver = driver or WchDriver()
    chips: list[ChipInfo] = []
    for index in range(MAX_DEVICES):
        if not driver.open(index):
            continue
        try:
            if driver.usb_id(index) not in BOOT_IDS:
                continue
            ids = parse_detect(driver.transfer(index, packet(CMD_DETECT, DETECT_PAYLOAD)))
            if ids is None:
                continue
            chip_id, sub_id = ids
            fields = (FIELD_BOOTVER | FIELD_UID).to_bytes(2, "little")
            ver, uid = parse_config(driver.transfer(index, packet(CMD_READ_CONFIG, fields)),
                                    chip_id, sub_id)
            chips.append(ChipInfo(index, chip_id, sub_id, ver, uid))
        finally:
            driver.close(index)
    return chips
