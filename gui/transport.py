"""Transports: a real hidapi transport and an in-process firmware simulator."""
from __future__ import annotations

import struct
from abc import ABC, abstractmethod
from collections import deque

from . import protocol as p

# Mock lock states (firmware lock.h)
LOCK_OPEN, LOCK_LOCKED, LOCK_BLOCKED = 0, 1, 2
LOCK_MAX_FAILS = 5


class TransportError(Exception):
    """The link to the device is gone or could not be opened."""


class Transport(ABC):
    @abstractmethod
    def write(self, report: bytes) -> None:
        """Send one 64-byte OUT report (without any report-ID prefix)."""

    @abstractmethod
    def read(self, timeout_ms: int) -> bytes | None:
        """Return one 64-byte IN report, or None on timeout."""

    @abstractmethod
    def close(self) -> None: ...

    @property
    @abstractmethod
    def description(self) -> str: ...


# ------------------------------------------------------------------ hidapi

def _hid():
    try:
        import hid  # provided by the "hidapi" pip package
    except ImportError as e:
        raise TransportError("hidapi 모듈을 불러올 수 없습니다 (pip install hidapi)") from e
    return hid


class HidTransport(Transport):
    def __init__(self, path: bytes):
        hid = _hid()
        self._path = path
        self._dev = hid.device()
        try:
            self._dev.open_path(path)
        except (OSError, IOError) as e:
            raise TransportError(f"장치를 열 수 없습니다: {e}") from e

    @staticmethod
    def find_paths() -> list[bytes]:
        """Paths of the vendor (0xFF00) interface of every matching keyboard."""
        hid = _hid()
        return [d["path"] for d in hid.enumerate(p.VID, p.PID)
                if d.get("usage_page") == p.USAGE_PAGE]

    @classmethod
    def open_first(cls) -> "HidTransport":
        paths = cls.find_paths()
        if not paths:
            raise TransportError("키보드를 찾을 수 없습니다. USB 연결을 확인하세요")
        return cls(paths[0])

    def write(self, report: bytes) -> None:
        # hidapi expects the report ID first; 0x00 because the device uses none.
        try:
            n = self._dev.write(b"\x00" + bytes(report))
        except (OSError, IOError, ValueError) as e:
            raise TransportError(f"장치에 쓰기 실패: {e}") from e
        if n < 0:
            raise TransportError("장치에 쓰기 실패 (연결이 끊겼을 수 있습니다)")

    def read(self, timeout_ms: int) -> bytes | None:
        try:
            data = self._dev.read(p.REPORT_SIZE, timeout_ms)
        except (OSError, IOError, ValueError) as e:
            raise TransportError(f"장치에서 읽기 실패: {e}") from e
        return bytes(data) if data else None

    def close(self) -> None:
        try:
            self._dev.close()
        except Exception:
            pass

    @property
    def description(self) -> str:
        return "USB"


# ------------------------------------------------------------------ mock

class MockDevice(Transport):
    """Simulates the firmware side of PROTOCOL.md in-process.

    Knobs for tests: ``capacity`` (reported in HELLO), ``storage_capacity``
    (what COMMIT/WRITE really accept, defaults to capacity), ``busy_count``
    (answer the next N commands after a TEST with BUSY), ``corrupt_next_write``
    (flip a byte of the next WRITE to provoke BAD_CRC), ``flash_error``,
    ``drop_responses`` (swallow the next N responses to provoke timeouts),
    ``protocol`` (1 = firmware 1.0 without the lock), ``fw`` (major, minor[, patch])
    and ``build`` (year, month, day, hour, minute; zeros = no build date).

    Like the firmware it starts locked when the stored config has a lock
    pattern; ``enter_pattern`` plays the keyboard inputs and ``power_cycle``
    re-plugs it.
    """

    def __init__(self, capacity: int = 4096, fw: tuple[int, ...] = (0, 1),
                 storage: bytes | None = None, storage_capacity: int | None = None,
                 protocol: int = p.PROTOCOL_VERSION,
                 build: tuple[int, int, int, int, int] = (0, 0, 0, 0, 0)):
        self.capacity = capacity
        self.protocol = protocol
        self.storage_capacity = capacity if storage_capacity is None else storage_capacity
        self.fw = fw
        self.build = build
        # Flash content: blank flash reads as 0xFF.
        self.storage = bytearray(b"\xFF" * self.storage_capacity)
        if storage:
            self.storage[:len(storage)] = storage
        self.staging = bytearray(self.storage_capacity)
        self.next_write_offset = 0
        self.typed: list[int] = []          # slots requested via TEST
        self.busy_count = 0
        self.busy_after_test = 0
        self.corrupt_next_write = False
        self.flash_error = False
        self.drop_responses = 0
        self.connected = True
        self.in_bootloader = False
        self.commit_count = 0
        self.requests: list[p.Request] = []
        self._out: deque[bytes] = deque()
        self.lock_state = LOCK_OPEN
        self.lock_fails = 0
        self._init_lock()

    # Transport API -----------------------------------------------------
    def write(self, report: bytes) -> None:
        if not self.connected:
            raise TransportError("장치 연결이 끊겼습니다")
        req = p.decode_request(bytes(report))
        self.requests.append(req)
        resp = self._handle(req)
        if self.drop_responses > 0:
            self.drop_responses -= 1
            return
        self._out.append(resp)

    def read(self, timeout_ms: int) -> bytes | None:
        if self._out:
            return self._out.popleft()
        if not self.connected:
            raise TransportError("장치 연결이 끊겼습니다")
        return None  # behaves like a timeout, without actually waiting

    def close(self) -> None:
        self._out.clear()

    @property
    def description(self) -> str:
        return "모의 장치"

    def reconnect(self) -> None:
        """Simulate re-plugging the keyboard (e.g. after BOOT)."""
        self.connected = True
        self.in_bootloader = False
        self._out.clear()

    # Helpers for tests ---------------------------------------------------
    def stored_config(self) -> p.Config:
        return p.decode_blob(bytes(self.storage))

    def power_cycle(self) -> None:
        """Unplug and plug in again: locks again when a pattern is stored."""
        self.reconnect()
        self._init_lock()

    def enter_pattern(self, steps: list[int]) -> None:
        """One full try on the keyboard (key/knob inputs as slot numbers)."""
        if self.lock_state != LOCK_LOCKED:
            return
        if list(steps) == self.stored_config().lock:
            self.lock_state = LOCK_OPEN
            self.lock_fails = 0
            self.relock_fails = 0
            return
        self.lock_fails += 1
        if self.lock_fails >= LOCK_MAX_FAILS:
            self.lock_state = LOCK_BLOCKED

    def relock(self, steps: list[int]) -> None:
        """Knob hold plus a pattern on an open keyboard: the right one locks,
        and so does the fifth wrong one in a row."""
        lock = self.stored_config().lock
        if self.lock_state != LOCK_OPEN or not lock:
            return
        if list(steps) != lock:
            self.relock_fails += 1
            if self.relock_fails < LOCK_MAX_FAILS:
                return
        self.lock_state = LOCK_LOCKED
        self.lock_fails = 0
        self.relock_fails = 0

    @property
    def locked(self) -> bool:
        return self.lock_state != LOCK_OPEN

    def _init_lock(self) -> None:
        has_lock = self.protocol >= 2 and bool(self.stored_config().lock)
        self.lock_state = LOCK_LOCKED if has_lock else LOCK_OPEN
        self.lock_fails = 0
        self.relock_fails = 0

    def _lock_flags(self) -> int:
        flags = p.LOCK_FLAG_SET if self.stored_config().lock else 0
        if self.lock_state != LOCK_OPEN:
            flags |= p.LOCK_FLAG_LOCKED
        if self.lock_state == LOCK_BLOCKED:
            flags |= p.LOCK_FLAG_BLOCKED
        return flags

    # Firmware logic --------------------------------------------------------
    def _handle(self, req: p.Request) -> bytes:
        cmd, seq, a = req.cmd, req.seq, req.args

        def reply(status: int, result: bytes = b"") -> bytes:
            return p.encode_response(cmd, seq, status, result)

        if self.busy_count > 0 and cmd != p.Cmd.HELLO:
            self.busy_count -= 1
            return reply(p.Status.BUSY)

        if cmd == p.Cmd.HELLO:
            info = p.HelloInfo(self.protocol, self.fw[0], self.fw[1],
                               p.SLOT_COUNT, self.capacity)
            if self.protocol >= 2:
                info.lock_flags = self._lock_flags()
                info.fw_patch = self.fw[2] if len(self.fw) > 2 else 0
                info.build = self.build
            return reply(p.Status.OK, p.encode_hello_result(info))

        if self.locked and cmd in (p.Cmd.READ, p.Cmd.TEST, p.Cmd.BOOT):
            return reply(p.Status.LOCKED)

        if cmd == p.Cmd.READ:
            offset, length = struct.unpack_from("<HB", a)
            if not 1 <= length <= p.MAX_CHUNK or offset + length > self.capacity:
                return reply(p.Status.BAD_ARG)
            data = bytes(self.storage[offset:offset + length])
            data += b"\xFF" * (length - len(data))
            return reply(p.Status.OK, p.encode_read_result(offset, data))

        if cmd == p.Cmd.WRITE:
            offset, length = struct.unpack_from("<HB", a)
            if not 1 <= length <= p.MAX_CHUNK:
                return reply(p.Status.BAD_ARG)
            if offset == 0:
                self.next_write_offset = 0       # a new transfer starts
            if offset != self.next_write_offset:
                return reply(p.Status.BAD_ARG)   # must be sequential, no gaps
            if offset + length > self.storage_capacity:
                return reply(p.Status.TOO_BIG)
            data = bytearray(a[3:3 + length])
            if self.corrupt_next_write:
                data[-1] ^= 0xFF
                self.corrupt_next_write = False
            self.staging[offset:offset + length] = data
            self.next_write_offset = offset + length
            return reply(p.Status.OK)

        if cmd == p.Cmd.COMMIT:
            total_len, crc = struct.unpack_from("<HH", a)
            if total_len > self.storage_capacity:
                return reply(p.Status.TOO_BIG)
            if total_len < p.BLOB_HEADER_SIZE or self.next_write_offset < total_len:
                return reply(p.Status.BAD_ARG)
            blob = bytes(self.staging[:total_len])
            try:
                header = p.parse_blob_header(blob)
            except p.BlobError:
                return reply(p.Status.BAD_ARG)
            if header.total_len != total_len:
                return reply(p.Status.BAD_ARG)
            if header.crc != crc or p.crc16_ccitt_false(blob[p.BLOB_HEADER_SIZE:]) != crc:
                return reply(p.Status.BAD_CRC)
            if not p.decode_blob(blob).valid:
                return reply(p.Status.BAD_ARG)   # e.g. a bad lock pattern
            if self.flash_error:
                return reply(p.Status.FLASH_ERR)
            self.storage[:] = b"\xFF" * self.storage_capacity
            self.storage[:total_len] = blob
            self.next_write_offset = 0
            self.commit_count += 1
            if self.locked:
                self._init_lock()   # the new config's own pattern decides
            return reply(p.Status.OK)

        if cmd == p.Cmd.TEST:
            slot = a[0]
            if slot >= p.SLOT_COUNT:
                return reply(p.Status.BAD_ARG)
            self.typed.append(slot)
            self.busy_count = self.busy_after_test
            return reply(p.Status.OK)

        if cmd == p.Cmd.BOOT:
            # Reply first, then "drop off the bus".
            self.connected = False
            self.in_bootloader = True
            return reply(p.Status.OK)

        return reply(p.Status.BAD_CMD)
