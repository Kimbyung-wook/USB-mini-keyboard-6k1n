import pytest

from gui import protocol as p
from gui.device import (
    ConfigTooBigError, DeviceClient, DeviceError, DeviceStatusError, DeviceTimeoutError,
    IncompatibleDeviceError, NotConnectedError,
)
from gui.transport import MockDevice, TransportError


def make(mock: MockDevice | None = None) -> tuple[DeviceClient, MockDevice]:
    mock = mock or MockDevice()
    client = DeviceClient(mock, sleep=lambda s: None)
    return client, mock


def cmds(mock: MockDevice, cmd: int) -> list[p.Request]:
    return [r for r in mock.requests if r.cmd == cmd]


def test_hello():
    client, _ = make(MockDevice(capacity=2048, fw=(1, 2)))
    info = client.hello()
    assert (info.protocol_version, info.fw_version, info.slot_count, info.capacity) == (2, "1.2.0", 9, 2048)


def test_blank_device_reads_as_no_config():
    client, mock = make()
    client.hello()
    cfg = client.read_config()
    assert not cfg.valid and cfg.slots == [""] * 9
    assert len(cmds(mock, p.Cmd.READ)) == 1   # only the first chunk is read


def test_full_read_edit_write_commit_cycle():
    initial = ["Hello{ENTER}", "{CTRL+C}", "", "", "", "", "{RIGHT}", "{LEFT}", "{ENTER}"]
    client, mock = make(MockDevice(storage=p.encode_blob(initial)))
    client.hello()
    cfg = client.read_config()
    assert cfg.valid and cfg.slots == initial

    edited = list(cfg.slots)
    edited[2] = "x" * 100 + "{DELAY:500}"
    edited[5] = "{CTRL+SHIFT+ESC}"
    size = client.write_config(edited)
    assert size == p.blob_size(edited)
    assert mock.commit_count == 1
    assert mock.stored_config().slots == edited

    # Seq numbers increase by one and every request got a response.
    seqs = [r.seq for r in mock.requests]
    assert seqs == [(seqs[0] + i) & 0xFF for i in range(len(seqs))]

    assert client.read_config().slots == edited


@pytest.mark.parametrize("total", [55, 56, 57, 111, 112, 113, 4096])
def test_chunking_across_56_byte_boundaries(total):
    # One slot carries the padding so the blob is exactly `total` bytes.
    filler = total - p.blob_size([""] * 9)
    slots = ["a" * filler] + [""] * 8
    assert p.blob_size(slots) == total
    client, mock = make()
    client.hello()
    client.write_config(slots)

    writes = cmds(mock, p.Cmd.WRITE)
    lengths = [r.args[2] for r in writes]
    offsets = [int.from_bytes(r.args[0:2], "little") for r in writes]
    assert all(1 <= n <= 56 for n in lengths)
    assert sum(lengths) == total
    assert offsets == list(range(0, total, 56))
    commit = cmds(mock, p.Cmd.COMMIT)[0]
    assert int.from_bytes(commit.args[0:2], "little") == total

    mock.requests.clear()
    assert client.read_config().slots == slots
    reads = cmds(mock, p.Cmd.READ)
    assert all(1 <= r.args[2] <= 56 for r in reads)
    assert sum(r.args[2] for r in reads) == max(total, 56)   # first chunk is always 56


def test_crc_failure_path_keeps_old_config():
    old = ["old"] * 9
    client, mock = make(MockDevice(storage=p.encode_blob(old)))
    client.hello()
    mock.corrupt_next_write = True
    with pytest.raises(DeviceStatusError) as ei:
        client.write_config(["new"] * 9)
    assert ei.value.status == p.Status.BAD_CRC
    assert "CRC" in str(ei.value)
    assert mock.stored_config().slots == old
    # A clean retry succeeds.
    client.write_config(["new"] * 9)
    assert mock.stored_config().slots == ["new"] * 9


def test_too_big_rejected_by_client_before_sending():
    client, mock = make(MockDevice(capacity=4096))
    client.hello()
    with pytest.raises(ConfigTooBigError) as ei:
        client.write_config(["x" * 4100] + [""] * 8)
    assert ei.value.capacity == 4096
    assert not cmds(mock, p.Cmd.WRITE)


def test_too_big_reported_by_device():
    # Device advertises 4096 but really only has 1024 bytes of storage.
    client, mock = make(MockDevice(capacity=4096, storage_capacity=1024))
    client.hello()
    with pytest.raises(DeviceStatusError) as ei:
        client.write_config(["x" * 2000] + [""] * 8)
    assert ei.value.status == p.Status.TOO_BIG
    assert "용량" in str(ei.value)
    assert mock.commit_count == 0


def test_commit_too_big_via_mock_directly():
    mock = MockDevice()
    mock.write(p.encode_request(p.Cmd.COMMIT, 1, p.commit_args(5000, 0)))
    assert p.decode_response(mock.read(10)).status == p.Status.TOO_BIG


def test_mock_rejects_out_of_order_write():
    mock = MockDevice()
    mock.write(p.encode_request(p.Cmd.WRITE, 1, p.write_args(0, b"MK")))
    mock.write(p.encode_request(p.Cmd.WRITE, 2, p.write_args(10, b"xx")))
    assert p.decode_response(mock.read(10)).status == p.Status.OK
    assert p.decode_response(mock.read(10)).status == p.Status.BAD_ARG


def test_mock_read_bounds():
    mock = MockDevice(capacity=100)
    for seq, (off, n) in enumerate([(90, 11), (0, 0), (0, 57)]):
        mock.write(p.encode_request(p.Cmd.READ, seq, p.read_args(off, n)))
        assert p.decode_response(mock.read(10)).status == p.Status.BAD_ARG


def test_flash_error():
    client, mock = make()
    client.hello()
    mock.flash_error = True
    with pytest.raises(DeviceStatusError) as ei:
        client.write_config([""] * 9)
    assert ei.value.status == p.Status.FLASH_ERR


def test_test_command_records_slot():
    client, mock = make()
    client.hello()
    client.test(4)
    client.test(8)
    assert mock.typed == [4, 8]
    with pytest.raises(ValueError):
        client.test(9)


def test_busy_after_test_is_retried():
    client, mock = make()
    client.hello()
    mock.busy_after_test = 3
    client.test(0)
    cfg = client.read_config()       # first 3 READs answered BUSY, then retried
    assert not cfg.valid
    assert sum(1 for r in mock.requests if r.cmd == p.Cmd.READ) == 4


def test_test_while_busy_raises():
    client, mock = make()
    client.hello()
    mock.busy_after_test = 1
    client.test(0)
    with pytest.raises(DeviceStatusError) as ei:
        client.test(1)
    assert ei.value.status == p.Status.BUSY


def test_timeout():
    client, mock = make()
    mock.drop_responses = 1
    with pytest.raises(DeviceTimeoutError):
        client.hello()


def test_stale_response_is_skipped():
    client, mock = make()
    mock.drop_responses = 0
    # Queue an unrelated stale reply before the real one.
    mock._out.append(p.encode_response(p.Cmd.HELLO, 200, 0))
    assert client.hello().slot_count == 9


def test_incompatible_protocol_version():
    class OldDevice(MockDevice):
        def _handle(self, req):
            if req.cmd == p.Cmd.HELLO:
                return p.encode_response(1, req.seq, 0, p.encode_hello_result(p.HelloInfo(3, 0, 1, 9, 4096)))
            return super()._handle(req)

    client, _ = make(OldDevice())
    with pytest.raises(IncompatibleDeviceError):
        client.hello()


def test_boot_disconnects():
    client, mock = make()
    client.hello()
    client.reboot_to_bootloader()
    assert mock.in_bootloader and not mock.connected
    assert not client.connected
    with pytest.raises(TransportError):
        mock.write(p.encode_request(p.Cmd.HELLO, 1))


def test_disconnected_transport_raises_not_connected():
    client, mock = make()
    client.hello()
    mock.connected = False
    with pytest.raises(NotConnectedError):
        client.read_config()


# ---------------------------------------------------------------- lock pattern

LOCK = [0, 1, 2, p.SLOT_KNOB_CW]


def test_locked_device_refuses_read_test_boot():
    client, mock = make(MockDevice(storage=p.encode_blob(["secret"] + [""] * 8, LOCK)))
    info = client.hello()
    assert info.locked and not info.blocked and info.lock_flags & p.LOCK_FLAG_SET
    for call in (client.read_config, lambda: client.test(0)):
        with pytest.raises(DeviceStatusError) as e:
            call()
        assert e.value.status == p.Status.LOCKED
    assert mock.typed == []

    mock.enter_pattern(LOCK)
    assert not client.hello().locked
    cfg = client.read_config()
    assert cfg.slots[0] == "secret" and cfg.lock == LOCK


def test_wrong_patterns_block_until_power_cycle():
    _, mock = make(MockDevice(storage=p.encode_blob([""] * 9, LOCK)))
    for _ in range(5):
        mock.enter_pattern([5, 5, 5, 5])
    mock.enter_pattern(LOCK)
    client, _ = make(mock)
    assert client.hello().blocked
    mock.power_cycle()
    mock.enter_pattern(LOCK)
    assert not client.hello().locked


def test_write_while_locked_replaces_config():
    client, mock = make(MockDevice(storage=p.encode_blob(["secret"] + [""] * 8, LOCK)))
    client.hello()
    client.write_config(["new"] + [""] * 8)          # no lock in the new config
    assert not client.hello().locked
    assert client.read_config().slots[0] == "new"


def test_save_lock_keeps_open_device_open_until_replug():
    client, mock = make()
    client.hello()
    client.write_config([""] * 9, lock=LOCK)
    assert client.hello().lock_flags == p.LOCK_FLAG_SET
    mock.power_cycle()
    assert client.hello().locked


def test_lock_needs_protocol_2():
    client, mock = make(MockDevice(protocol=1, fw=(1, 0)))
    info = client.hello()
    assert not info.supports_lock and not info.locked
    with pytest.raises(DeviceError) as e:
        client.write_config([""] * 9, lock=LOCK)
    assert "패턴 암호" in str(e.value)
    assert mock.commit_count == 0


def test_mock_relock_rules():
    _, mock = make(MockDevice(storage=p.encode_blob([""] * 9, LOCK)))
    mock.enter_pattern(LOCK)
    for _ in range(4):
        mock.relock([5, 5, 5, 5])
    assert not mock.locked
    mock.relock([5, 5, 5, 5])                 # fifth wrong re-lock: locks anyway
    assert mock.locked and mock.lock_fails == 0
    mock.enter_pattern(LOCK)
    assert not mock.locked
