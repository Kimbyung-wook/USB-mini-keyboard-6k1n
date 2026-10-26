"""Wire format of the configuration protocol v2 (see docs/PROTOCOL.md).

Pure functions only: packet framing, status codes, CRC16 and the config blob.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum

VID = 0x1209
PID = 0xC55D
USAGE_PAGE = 0xFF00
USAGE = 0x01
BOOTLOADER_VID = 0x4348
BOOTLOADER_PID = 0x55E0

REPORT_SIZE = 64
MAX_CHUNK = 56            # max data bytes per READ / WRITE
PROTOCOL_VERSION = 2
# v1 (firmware 1.0) is the same without the lock: no HELLO flags, no LOCKED
SUPPORTED_PROTOCOL_VERSIONS = (1, 2)

BLOB_MAGIC = b"MK"
BLOB_VERSION = 1
BLOB_HEADER_SIZE = 8

TIMEOUT_MS = 1000
COMMIT_TIMEOUT_MS = 2000

# Lock pattern: optional extra slot after the macro slots, one byte per step
# holding the slot number of the input
LOCK_MIN_STEPS = 4
LOCK_MAX_STEPS = 8

# HELLO lock flags (protocol v2)
LOCK_FLAG_SET = 0x01
LOCK_FLAG_LOCKED = 0x02
LOCK_FLAG_BLOCKED = 0x04


# ---------------------------------------------------------------- board

BOARD_INFO_VERSION = 1      # HELLO byte 17 (docs/BOARD_INFO.md)
BOARD_FEATURE_RGB_LED = 0x01
BOARD_FEATURE_LOCK = 0x02
MAX_SLOTS = 63
BOARD_NAME_LEN = 8

# Actions of one knob, in slot order
KNOB_ACTIONS = ("CW", "CCW", "PRESS")
KNOB_ACTIONS_KO = ("시계 방향", "반시계 방향", "누르기")
KNOB_SYMBOLS = ("↻", "↺", "●")


@dataclass(frozen=True)
class Board:
    """Keys and knobs of a keyboard, as its HELLO reports them.

    Slots: keys 0..keys-1 in rows from the top left, then CW, CCW, PRESS
    for each knob; the lock pattern is stored after them (lock_slot).
    """
    keys: int = 6
    knobs: int = 1
    rows: int = 2
    name: str = "MK6K1N"
    chip_id: int = 0x52                  # as the bootloader's Detect reports it
    features: int = BOARD_FEATURE_RGB_LED | BOARD_FEATURE_LOCK
    uid: bytes = b""                     # chip unique ID, empty when unknown

    def __post_init__(self):
        if self.keys < 1 or self.knobs < 0 or self.slot_count > MAX_SLOTS:
            raise ValueError(f"지원하지 않는 배치입니다 (키 {self.keys}, 노브 {self.knobs})")
        if not 1 <= self.rows <= self.keys:
            raise ValueError(f"키 배치의 행 수가 올바르지 않습니다 ({self.rows})")

    @property
    def slot_count(self) -> int:
        return self.keys + 3 * self.knobs

    @property
    def lock_slot(self) -> int:
        return self.slot_count

    @property
    def cols(self) -> int:
        return -(-self.keys // self.rows)

    def knob_slot(self, knob: int, action: int) -> int:
        return self.keys + 3 * knob + action

    def knob_of(self, slot: int) -> tuple[int, int] | None:
        """(knob, action) of a knob slot, None for a key."""
        if slot < self.keys:
            return None
        return divmod(slot - self.keys, 3)

    def key_name(self, key: int) -> str:
        return chr(ord("A") + key) if key < 26 else f"K{key + 1}"

    def slot_name(self, slot: int) -> str:
        """Short name, also the "key" of a JSON backup: A..F, CW, CCW, PRESS, CW2, …"""
        knob = self.knob_of(slot)
        if knob is None:
            return self.key_name(slot)
        n, action = knob
        return KNOB_ACTIONS[action] + (f"{n + 1}" if n else "")

    def slot_label(self, slot: int) -> str:
        """Korean label: 키 A, 노브 시계 방향 (노브 2 시계 방향 with several knobs)."""
        knob = self.knob_of(slot)
        if knob is None:
            return f"키 {self.key_name(slot)}"
        n, action = knob
        return f"노브{f' {n + 1}' if self.knobs > 1 else ''} {KNOB_ACTIONS_KO[action]}"

    def step_name(self, slot: int) -> str:
        """Lock pattern step: the key letter, or the knob symbol."""
        knob = self.knob_of(slot)
        if knob is None:
            return self.key_name(slot)
        n, action = knob
        return (f"{n + 1}" if self.knobs > 1 else "") + KNOB_SYMBOLS[action]

    @property
    def slot_names(self) -> list[str]:
        return [self.slot_name(i) for i in range(self.slot_count)]

    @property
    def slot_labels(self) -> list[str]:
        return [self.slot_label(i) for i in range(self.slot_count)]

    @property
    def summary(self) -> str:
        knobs = f" + 노브 {self.knobs}" if self.knobs else ""
        return f"키 {self.keys}{knobs}"


# The keyboard of this project; also assumed for firmware without board info
DEFAULT_BOARD = Board()

# Slot numbers of DEFAULT_BOARD. Code that depends on the connected keyboard
# uses its Board instead.
SLOT_COUNT = DEFAULT_BOARD.slot_count
SLOT_KNOB_CW = DEFAULT_BOARD.knob_slot(0, 0)
SLOT_KNOB_CCW = DEFAULT_BOARD.knob_slot(0, 1)
SLOT_KNOB_PRESS = DEFAULT_BOARD.knob_slot(0, 2)
SLOT_LOCK = DEFAULT_BOARD.lock_slot


def lock_error(lock: list[int], board: Board = DEFAULT_BOARD) -> str | None:
    """Why a lock pattern cannot be stored, or None (an empty one means no lock)."""
    if not lock:
        return None
    if any(not 0 <= s < board.slot_count for s in lock):
        return "패턴 암호에 알 수 없는 입력이 있습니다"
    if not LOCK_MIN_STEPS <= len(lock) <= LOCK_MAX_STEPS:
        return f"패턴 암호는 {LOCK_MIN_STEPS}~{LOCK_MAX_STEPS}단계여야 합니다 (지금 {len(lock)}단계)"
    return None


def lock_text(lock: list[int], board: Board = DEFAULT_BOARD) -> str:
    return " → ".join(board.step_name(s) for s in lock)


class Cmd(IntEnum):
    HELLO = 0x01
    READ = 0x02
    WRITE = 0x03
    COMMIT = 0x04
    TEST = 0x05
    BOOT = 0x06


class Status(IntEnum):
    OK = 0
    BAD_CMD = 1
    BAD_ARG = 2
    BAD_CRC = 3
    TOO_BIG = 4
    FLASH_ERR = 5
    BUSY = 6
    LOCKED = 7


STATUS_MESSAGES_KO = {
    Status.OK: "성공",
    Status.BAD_CMD: "장치가 알 수 없는 명령입니다",
    Status.BAD_ARG: "인수 범위 오류입니다 (오프셋/길이/슬롯 번호)",
    Status.BAD_CRC: "CRC가 일치하지 않습니다 (전송 중 데이터 손상)",
    Status.TOO_BIG: "저장 용량을 초과했습니다",
    Status.FLASH_ERR: "장치의 Flash 지우기/쓰기에 실패했습니다",
    Status.BUSY: "장치가 문자열을 출력하는 중입니다. 잠시 후 다시 시도하세요",
    Status.LOCKED: "장치가 잠겨 있습니다. 키보드에서 노브를 3초 누른 뒤 패턴 암호를 입력하세요",
}


def status_message(code: int) -> str:
    try:
        return STATUS_MESSAGES_KO[Status(code)]
    except ValueError:
        return f"알 수 없는 상태 코드 ({code})"


# ---------------------------------------------------------------- CRC16

def crc16_ccitt_false(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, no xorout."""
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


# ---------------------------------------------------------------- packets

class PacketError(ValueError):
    pass


def _pad(data: bytes) -> bytes:
    if len(data) > REPORT_SIZE:
        raise PacketError(f"packet too long: {len(data)} bytes")
    return data + bytes(REPORT_SIZE - len(data))


def encode_request(cmd: int, seq: int, args: bytes = b"") -> bytes:
    """Build a 64-byte OUT report: cmd, seq, args, zero padding."""
    return _pad(bytes([cmd & 0xFF, seq & 0xFF]) + args)


@dataclass
class Request:
    cmd: int
    seq: int
    args: bytes  # bytes 2..63


def decode_request(report: bytes) -> Request:
    if len(report) != REPORT_SIZE:
        raise PacketError(f"request must be {REPORT_SIZE} bytes, got {len(report)}")
    return Request(report[0], report[1], bytes(report[2:]))


def encode_response(cmd: int, seq: int, status: int, result: bytes = b"") -> bytes:
    return _pad(bytes([(cmd | 0x80) & 0xFF, seq & 0xFF, status & 0xFF]) + result)


@dataclass
class Response:
    cmd: int      # original command (0x80 bit stripped)
    seq: int
    status: int
    result: bytes  # bytes 3..63


def decode_response(report: bytes) -> Response:
    if len(report) < 3:
        raise PacketError(f"response too short: {len(report)} bytes")
    if not report[0] & 0x80:
        raise PacketError(f"not a response packet (byte0=0x{report[0]:02X})")
    return Response(report[0] & 0x7F, report[1], report[2], bytes(report[3:]))


# Request argument builders ------------------------------------------------

def read_args(offset: int, length: int) -> bytes:
    return struct.pack("<HB", offset, length)


def write_args(offset: int, data: bytes) -> bytes:
    return struct.pack("<HB", offset, len(data)) + data


def commit_args(total_len: int, crc: int) -> bytes:
    return struct.pack("<HH", total_len, crc)


def test_args(slot: int) -> bytes:
    return bytes([slot])


# Response result parsers --------------------------------------------------

@dataclass
class HelloInfo:
    protocol_version: int
    fw_major: int
    fw_minor: int
    slot_count: int
    capacity: int
    lock_flags: int = 0      # LOCK_FLAG_* (protocol v2)
    fw_patch: int = 0        # protocol v2
    build: tuple[int, int, int, int, int] = (0, 0, 0, 0, 0)  # year, month, day, hour, minute; 0 = unknown
    board_info: Board | None = None   # HELLO bytes 17-35; None = firmware without board info

    @property
    def board(self) -> Board:
        return self.board_info or DEFAULT_BOARD

    @property
    def fw_version(self) -> str:
        if self.supports_lock:   # v2 also reports the patch number
            return f"{self.fw_major}.{self.fw_minor}.{self.fw_patch}"
        return f"{self.fw_major}.{self.fw_minor}"

    @property
    def build_date(self) -> str | None:
        """'2026-10-26 11:40', or None when the firmware was built without a date."""
        year, month, day, hour, minute = self.build
        if not year:
            return None
        return f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"

    @property
    def fw_text(self) -> str:
        """Version and build date for display."""
        if not self.supports_lock:
            return f"펌웨어 v{self.fw_version}"
        date = self.build_date
        return f"펌웨어 v{self.fw_version} (빌드 {date})" if date else f"펌웨어 v{self.fw_version} (빌드 날짜 없음)"

    @property
    def supports_lock(self) -> bool:
        return self.protocol_version >= 2

    @property
    def locked(self) -> bool:
        return bool(self.lock_flags & LOCK_FLAG_LOCKED)

    @property
    def blocked(self) -> bool:
        return bool(self.lock_flags & LOCK_FLAG_BLOCKED)


# Board info inside the HELLO result (bytes 3..63): packet byte 17 = result[14]
BOARD_INFO_OFFSET = 14
BOARD_INFO_FORMAT = f"<BBBBBBB{BOARD_NAME_LEN}s4s"


def encode_hello_result(info: HelloInfo) -> bytes:
    out = struct.pack("<BBBBHBBHBBBB", info.protocol_version, info.fw_major,
                      info.fw_minor, info.slot_count, info.capacity, info.lock_flags,
                      info.fw_patch, *info.build)
    b = info.board_info
    if b is not None:
        out += struct.pack(BOARD_INFO_FORMAT, BOARD_INFO_VERSION, b.chip_id, b.keys, b.knobs,
                           b.rows, b.features, 0, b.name.encode("ascii")[:BOARD_NAME_LEN],
                           b.uid[:4].ljust(4, bytes(1)))
    return out


class BoardInfoError(ValueError):
    pass


def parse_board_info(result: bytes) -> Board | None:
    """Board from HELLO bytes 17-35, None when the firmware sends none (byte 17 = 0)."""
    if len(result) < BOARD_INFO_OFFSET + struct.calcsize(BOARD_INFO_FORMAT):
        return None
    version, chip, keys, knobs, rows, features, _, name, uid = struct.unpack_from(
        BOARD_INFO_FORMAT, result, BOARD_INFO_OFFSET)
    if version == 0:
        return None
    try:
        return Board(keys=keys, knobs=knobs, rows=rows, chip_id=chip, features=features,
                     name=name.rstrip(bytes(1)).decode("ascii", errors="replace"),
                     uid=b"" if uid == bytes(4) else uid)
    except ValueError as e:
        raise BoardInfoError(str(e)) from e


def parse_hello_result(result: bytes) -> HelloInfo:
    info = HelloInfo(*struct.unpack_from("<BBBBH", result))
    if info.supports_lock and len(result) >= 14:
        info.lock_flags, info.fw_patch, *build = struct.unpack_from("<BBHBBBB", result, 6)
        info.build = tuple(build)
        info.board_info = parse_board_info(result)
    return info


def encode_read_result(offset: int, data: bytes) -> bytes:
    return struct.pack("<HB", offset, len(data)) + data


def parse_read_result(result: bytes) -> tuple[int, bytes]:
    offset, length = struct.unpack_from("<HB", result)
    if length > MAX_CHUNK:
        raise PacketError(f"READ response length {length} > {MAX_CHUNK}")
    return offset, bytes(result[3:3 + length])


# ---------------------------------------------------------------- blob

@dataclass
class Config:
    """Macro strings, the lock pattern and whether the blob was valid."""
    slots: list[str] = field(default_factory=lambda: [""] * SLOT_COUNT)
    valid: bool = True       # False -> "설정 없음" (blank or corrupt blob)
    reason: str = ""         # why the blob was rejected, for display
    lock: list[int] = field(default_factory=list)   # empty = no lock

    @classmethod
    def empty(cls, reason: str = "", board: Board = DEFAULT_BOARD) -> "Config":
        return cls([""] * board.slot_count, valid=False, reason=reason)


class BlobError(ValueError):
    pass


def encode_blob(slots: list[str], lock: list[int] | tuple[int, ...] = (),
                board: Board = DEFAULT_BOARD) -> bytes:
    """Encode slot strings into a v1 blob. Strings must be ASCII.

    A lock pattern is stored as one more slot (lock_slot); without one the
    blob has exactly the board's slots, as firmware 1.0 expects.
    """
    if len(slots) != board.slot_count:
        raise BlobError(f"need {board.slot_count} slots, got {len(slots)}")
    lock = list(lock)
    err = lock_error(lock, board)
    if err:
        raise BlobError(err)
    raws = []
    for i, text in enumerate(slots):
        try:
            raws.append(text.encode("ascii"))
        except UnicodeEncodeError as e:
            raise BlobError(f"slot {i} contains non-ASCII text") from e
    if lock:
        raws.append(bytes(lock))
    payload = bytearray()
    for i, raw in enumerate(raws):
        if len(raw) > 0xFFFF:
            raise BlobError(f"slot {i} too long")
        payload += struct.pack("<H", len(raw)) + raw
    if len(payload) > 0xFFFF:
        raise BlobError("payload too long")
    header = BLOB_MAGIC + struct.pack("<BBHH", BLOB_VERSION, len(raws),
                                      len(payload), crc16_ccitt_false(bytes(payload)))
    return header + bytes(payload)


def blob_size(slots: list[str], lock: list[int] | tuple[int, ...] = ()) -> int:
    """Total blob length (header + payload) for the given slot texts and lock."""
    size = BLOB_HEADER_SIZE + sum(2 + len(s.encode("ascii", errors="replace")) for s in slots)
    return size + (2 + len(lock) if lock else 0)


@dataclass
class BlobHeader:
    version: int
    slot_count: int
    payload_len: int
    crc: int

    @property
    def total_len(self) -> int:
        return BLOB_HEADER_SIZE + self.payload_len


def parse_blob_header(data: bytes) -> BlobHeader:
    if len(data) < BLOB_HEADER_SIZE:
        raise BlobError("헤더가 너무 짧습니다")
    if data[0:2] != BLOB_MAGIC:
        raise BlobError("매직 값(MK)이 없습니다")
    version, count, length, crc = struct.unpack_from("<BBHH", data, 2)
    if version != BLOB_VERSION:
        raise BlobError(f"지원하지 않는 블롭 버전입니다 ({version})")
    return BlobHeader(version, count, length, crc)


def decode_blob(data: bytes, board: Board = DEFAULT_BOARD) -> Config:
    """Decode a blob. Any problem yields empty slots with valid=False."""
    try:
        header = parse_blob_header(data)
        payload = data[BLOB_HEADER_SIZE:header.total_len]
        if len(payload) != header.payload_len:
            raise BlobError("블롭 길이가 헤더와 맞지 않습니다")
        if crc16_ccitt_false(payload) != header.crc:
            raise BlobError("CRC가 일치하지 않습니다")
        raws: list[bytes] = []
        pos = 0
        for _ in range(header.slot_count):
            if pos + 2 > len(payload):
                raise BlobError("슬롯 데이터가 잘렸습니다")
            (n,) = struct.unpack_from("<H", payload, pos)
            pos += 2
            if pos + n > len(payload):
                raise BlobError("슬롯 데이터가 잘렸습니다")
            raws.append(bytes(payload[pos:pos + n]))
            pos += n
        if pos != len(payload):
            raise BlobError("페이로드 끝에 남는 데이터가 있습니다")
        lock = list(raws[board.lock_slot]) if len(raws) > board.lock_slot else []
        if lock_error(lock, board):
            raise BlobError(lock_error(lock, board))
    except (BlobError, struct.error) as e:
        return Config.empty(str(e), board)
    # latin-1 never fails; non-ASCII bytes are caught by the validator.
    # Tolerate a different slot count: keep the board's slots, pad with empty.
    n = board.slot_count
    slots = [r.decode("latin-1") for r in raws[:n]]
    slots += [""] * (n - len(slots))
    return Config(slots, valid=True, lock=lock)
