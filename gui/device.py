"""High-level client for the keyboard's configuration protocol."""
from __future__ import annotations

import time
from typing import Callable

from . import protocol as p
from .transport import Transport, TransportError

Progress = Callable[[int, int], None]   # (bytes done, bytes total)


class DeviceError(Exception):
    """Base class; str(e) is a user-facing Korean message."""


class NotConnectedError(DeviceError):
    def __init__(self, msg: str = "장치가 연결되어 있지 않습니다"):
        super().__init__(msg)


class DeviceTimeoutError(DeviceError):
    pass


class DeviceStatusError(DeviceError):
    def __init__(self, cmd: int, status: int):
        self.cmd = cmd
        self.status = status
        name = p.Cmd(cmd).name if cmd in p.Cmd._value2member_map_ else f"0x{cmd:02X}"
        super().__init__(f"{name} 실패: {p.status_message(status)}")


class IncompatibleDeviceError(DeviceError):
    pass


class ConfigTooBigError(DeviceError):
    def __init__(self, size: int, capacity: int):
        self.size = size
        self.capacity = capacity
        super().__init__(f"설정 크기({size}바이트)가 장치 용량({capacity}바이트)을 넘습니다")


class DeviceClient:
    def __init__(self, transport: Transport, *, timeout_ms: int = p.TIMEOUT_MS,
                 commit_timeout_ms: int = p.COMMIT_TIMEOUT_MS,
                 busy_retries: int = 20, busy_delay_s: float = 0.1,
                 sleep: Callable[[float], None] = time.sleep):
        self.transport: Transport | None = transport
        self.timeout_ms = timeout_ms
        self.commit_timeout_ms = commit_timeout_ms
        self.busy_retries = busy_retries
        self.busy_delay_s = busy_delay_s
        self._sleep = sleep
        self._seq = 0
        self.info: p.HelloInfo | None = None

    # ---------------------------------------------------------- low level
    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFF
        return self._seq

    def _transact(self, cmd: int, args: bytes, timeout_ms: int) -> p.Response:
        if self.transport is None:
            raise NotConnectedError()
        seq = self._next_seq()
        try:
            self.transport.write(p.encode_request(cmd, seq, args))
            deadline = time.monotonic() + timeout_ms / 1000
            while True:
                remaining = int((deadline - time.monotonic()) * 1000)
                report = self.transport.read(max(remaining, 1))
                if report is None:
                    break
                try:
                    resp = p.decode_response(report)
                except p.PacketError:
                    continue
                if resp.cmd == cmd and resp.seq == seq:
                    return resp
                # Stale reply to an earlier (timed-out) request: skip it.
                if time.monotonic() >= deadline:
                    break
        except TransportError as e:
            raise NotConnectedError(f"장치와의 연결이 끊겼습니다 ({e})") from e
        raise DeviceTimeoutError(f"장치가 응답하지 않습니다 ({p.Cmd(cmd).name}, {timeout_ms}ms 초과)")

    def _request(self, cmd: int, args: bytes = b"", timeout_ms: int | None = None,
                 retry_busy: bool = True) -> p.Response:
        timeout = self.timeout_ms if timeout_ms is None else timeout_ms
        attempts = self.busy_retries if retry_busy else 0
        while True:
            resp = self._transact(cmd, args, timeout)
            if resp.status == p.Status.BUSY and attempts > 0:
                attempts -= 1
                self._sleep(self.busy_delay_s)
                continue
            if resp.status != p.Status.OK:
                raise DeviceStatusError(cmd, resp.status)
            return resp

    def _require_info(self) -> p.HelloInfo:
        if self.info is None:
            self.hello()
        assert self.info is not None
        return self.info

    # ---------------------------------------------------------- commands
    def hello(self) -> p.HelloInfo:
        resp = self._request(p.Cmd.HELLO)
        try:
            info = p.parse_hello_result(resp.result)
        except p.BoardInfoError as e:
            raise IncompatibleDeviceError(f"장치의 보드 정보가 올바르지 않습니다: {e}") from e
        if info.protocol_version not in p.SUPPORTED_PROTOCOL_VERSIONS:
            raise IncompatibleDeviceError(
                f"지원하지 않는 프로토콜 버전입니다 (장치 v{info.protocol_version}, "
                f"프로그램 v{p.PROTOCOL_VERSION}). 펌웨어 또는 프로그램을 업데이트하세요")
        board = info.board
        if info.slot_count != board.slot_count:
            raise IncompatibleDeviceError(
                f"슬롯 수가 맞지 않습니다 (장치 {info.slot_count}개, "
                f"{board.summary} 배치라면 {board.slot_count}개)")
        self.info = info
        return info

    def read_range(self, offset: int, length: int) -> bytes:
        out = bytearray()
        while len(out) < length:
            n = min(p.MAX_CHUNK, length - len(out))
            pos = offset + len(out)
            resp = self._request(p.Cmd.READ, p.read_args(pos, n))
            got_off, data = p.parse_read_result(resp.result)
            if got_off != pos or not data:
                raise DeviceError(f"READ 응답이 올바르지 않습니다 (오프셋 {got_off}, 길이 {len(data)})")
            out += data
        return bytes(out[:length])

    def read_blob(self, progress: Progress | None = None) -> bytes:
        """Read the stored blob; for an invalid header only the first chunk."""
        cap = self._require_info().capacity
        first = self.read_range(0, min(p.MAX_CHUNK, cap))
        try:
            total = p.parse_blob_header(first).total_len
        except p.BlobError:
            return first
        if total > cap:
            return first      # header claims more than fits: treat as corrupt
        blob = bytearray(first)
        while len(blob) < total:
            if progress:
                progress(len(blob), total)
            blob += self.read_range(len(blob), min(p.MAX_CHUNK, total - len(blob)))
        if progress:
            progress(total, total)
        return bytes(blob[:total])

    def read_config(self, progress: Progress | None = None) -> p.Config:
        board = self._require_info().board
        return p.decode_blob(self.read_blob(progress), board)

    def write_config(self, slots: list[str], progress: Progress | None = None,
                     check_capacity: bool = True, lock: list[int] | tuple[int, ...] = ()) -> int:
        """WRITE the encoded blob in chunks, then COMMIT. Returns blob size."""
        info = self._require_info()
        try:
            blob = p.encode_blob(slots, lock, info.board)
        except p.BlobError as e:
            raise DeviceError(f"설정을 만들 수 없습니다: {e}") from e
        if lock and not info.supports_lock:
            raise DeviceError(f"펌웨어 v{info.fw_version}은 패턴 암호를 지원하지 않습니다. "
                              "펌웨어를 업데이트하거나 패턴 암호를 지우세요")
        cap = info.capacity
        if check_capacity and len(blob) > cap:
            raise ConfigTooBigError(len(blob), cap)
        for offset in range(0, len(blob), p.MAX_CHUNK):
            if progress:
                progress(offset, len(blob))
            self._request(p.Cmd.WRITE, p.write_args(offset, blob[offset:offset + p.MAX_CHUNK]))
        crc = p.crc16_ccitt_false(blob[p.BLOB_HEADER_SIZE:])
        self._request(p.Cmd.COMMIT, p.commit_args(len(blob), crc),
                      timeout_ms=self.commit_timeout_ms)
        if progress:
            progress(len(blob), len(blob))
        return len(blob)

    def test(self, slot: int) -> None:
        if not 0 <= slot < self._require_info().board.slot_count:
            raise ValueError(f"slot out of range: {slot}")
        self._request(p.Cmd.TEST, p.test_args(slot), retry_busy=False)

    def reboot_to_bootloader(self) -> None:
        """Send BOOT. The device disconnects afterwards; the client is closed."""
        try:
            self._request(p.Cmd.BOOT, retry_busy=False)
        except (DeviceTimeoutError, NotConnectedError):
            pass  # it may drop off the bus before the reply gets through
        self.close()

    def close(self) -> None:
        if self.transport is not None:
            self.transport.close()
        self.transport = None
        self.info = None

    @property
    def connected(self) -> bool:
        return self.transport is not None
