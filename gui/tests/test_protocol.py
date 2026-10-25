import struct

import pytest

from gui import protocol as p


def test_crc16_check_value():
    assert p.crc16_ccitt_false(b"123456789") == 0x29B1


def test_crc16_empty_is_init():
    assert p.crc16_ccitt_false(b"") == 0xFFFF


def test_blob_round_trip():
    slots = ["Hello{ENTER}", "", "{CTRL+C}", "a\nb", "{{x}}", "", "{RIGHT}", "{LEFT}", "x" * 300]
    blob = p.encode_blob(slots)
    assert blob[:2] == b"MK" and blob[2] == 1 and blob[3] == 9
    (length,) = struct.unpack_from("<H", blob, 4)
    assert len(blob) == 8 + length == p.blob_size(slots)
    (crc,) = struct.unpack_from("<H", blob, 6)
    assert crc == p.crc16_ccitt_false(blob[8:])
    cfg = p.decode_blob(blob)
    assert cfg.valid and cfg.slots == slots


def test_empty_blob_layout():
    blob = p.encode_blob([""] * 9)
    assert len(blob) == 8 + 9 * 2
    assert blob[8:] == bytes(18)


def test_blob_decode_ignores_trailing_flash_bytes():
    blob = p.encode_blob(["a"] * 9)
    assert p.decode_blob(blob + b"\xFF" * 100).slots == ["a"] * 9


@pytest.mark.parametrize("data", [
    b"",
    b"\xFF" * 64,                     # blank flash
    bytes(64),                         # zeroed
    b"MK\x02\x09" + bytes(60),         # unknown version
])
def test_invalid_blob_gives_empty_config(data):
    cfg = p.decode_blob(data)
    assert not cfg.valid
    assert cfg.slots == [""] * 9
    assert cfg.reason


def test_bad_crc_blob_is_invalid():
    blob = bytearray(p.encode_blob(["abc"] * 9))
    blob[10] ^= 0x01
    cfg = p.decode_blob(bytes(blob))
    assert not cfg.valid and "CRC" in cfg.reason


def test_truncated_blob_is_invalid():
    blob = p.encode_blob(["abc"] * 9)
    assert not p.decode_blob(blob[:-1]).valid


def test_inconsistent_slot_lengths_invalid():
    # Payload whose slot length runs past the end, with a matching CRC.
    payload = struct.pack("<H", 50) + b"abc"
    header = b"MK" + struct.pack("<BBHH", 1, 9, len(payload), p.crc16_ccitt_false(payload))
    assert not p.decode_blob(header + payload).valid


def test_encode_rejects_non_ascii_and_wrong_count():
    with pytest.raises(p.BlobError):
        p.encode_blob(["한글"] + [""] * 8)
    with pytest.raises(p.BlobError):
        p.encode_blob([""] * 8)


def test_request_framing():
    pkt = p.encode_request(p.Cmd.READ, 0x2A, p.read_args(0x1234, 56))
    assert len(pkt) == 64
    assert pkt[:5] == bytes([0x02, 0x2A, 0x34, 0x12, 56])
    assert pkt[5:] == bytes(59)
    req = p.decode_request(pkt)
    assert (req.cmd, req.seq) == (0x02, 0x2A)


def test_seq_wraps_to_byte():
    assert p.encode_request(1, 256)[1] == 0


def test_write_args_layout():
    pkt = p.encode_request(p.Cmd.WRITE, 1, p.write_args(56, b"\xAA" * 56))
    assert len(pkt) == 64
    assert pkt[2:5] == bytes([56, 0, 56])
    assert pkt[5:61] == b"\xAA" * 56


def test_commit_args_layout():
    assert p.commit_args(0x0102, 0xBEEF) == bytes([0x02, 0x01, 0xEF, 0xBE])


def test_response_framing_and_hello():
    info = p.HelloInfo(1, 0, 3, 9, 4096)
    pkt = p.encode_response(p.Cmd.HELLO, 7, p.Status.OK, p.encode_hello_result(info))
    assert len(pkt) == 64
    assert pkt[:9] == bytes([0x81, 7, 0, 1, 0, 3, 9, 0x00, 0x10])
    resp = p.decode_response(pkt)
    assert (resp.cmd, resp.seq, resp.status) == (1, 7, 0)
    assert p.parse_hello_result(resp.result) == info
    assert info.fw_version == "0.3"


def test_read_result_parse():
    pkt = p.encode_response(p.Cmd.READ, 3, 0, p.encode_read_result(112, b"xyz"))
    assert pkt[3:9] == bytes([112, 0, 3]) + b"xyz"
    assert p.parse_read_result(p.decode_response(pkt).result) == (112, b"xyz")


def test_decode_response_rejects_request():
    with pytest.raises(p.PacketError):
        p.decode_response(p.encode_request(1, 1))


def test_oversized_packet_rejected():
    with pytest.raises(p.PacketError):
        p.encode_request(3, 1, bytes(63))


def test_status_messages_are_korean():
    assert "용량" in p.status_message(p.Status.TOO_BIG)
    assert "알 수 없는" in p.status_message(99)
