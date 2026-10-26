from gui import bootloader as b

DETECT_REPLY = bytes([0xA1, 0x00, 0x02, 0x00, 0x52, 0x11])
# fields 0x18, bootloader 00 02 05 00, UID 7D E2 0F BD (as vnproch55x prints it)
CONFIG_REPLY = bytes([0xA7, 0x00, 0x0E, 0x00, 0x18, 0x00, 0x00, 0x02, 0x05, 0x00,
                      0x7D, 0xE2, 0x0F, 0xBD, 0x00, 0x00, 0x00, 0x00])


class FakeDriver:
    def __init__(self, devices):
        self.devices = devices          # index -> (usb id, {cmd: reply})
        self.sent = []
        self.opened = set()

    def open(self, index):
        if index in self.devices:
            self.opened.add(index)
            return True
        return False

    def close(self, index):
        self.opened.discard(index)

    def usb_id(self, index):
        return self.devices[index][0]

    def transfer(self, index, data):
        self.sent.append((index, data))
        return self.devices[index][1].get(data[0], b"")


def test_packets_match_ch55xtool():
    assert b.packet(b.CMD_DETECT, b.DETECT_PAYLOAD) == bytes([0xA1, 0x12, 0x00, 0x42, 0x10]) + b"MCU ISP & WCH.CN"
    assert b.packet(b.CMD_READ_CONFIG, b"\x18\x00") == bytes([0xA7, 0x02, 0x00, 0x18, 0x00])


def test_parse_replies():
    assert b.parse_detect(DETECT_REPLY) == (0x52, 0x11)
    assert b.parse_detect(b"\xA7\x00\x02\x00\x52\x11") is None
    assert b.parse_config(CONFIG_REPLY, 0x52, 0x11) == ("2.5.0", bytes([0x7D, 0xE2, 0x0F, 0xBD]))
    assert b.parse_config(b"", 0x52, 0x11) == ("", b"")


def test_scan_lists_only_bootloaders():
    replies = {b.CMD_DETECT: DETECT_REPLY, b.CMD_READ_CONFIG: CONFIG_REPLY}
    drv = FakeDriver({0: ((0x4348, 0x55E0), replies),
                      2: ((0x1A86, 0x7523), replies),        # some other WCH device
                      3: ((0x4348, 0x55E0), {})})            # does not answer
    chips = b.scan(drv)
    assert len(chips) == 1
    c = chips[0]
    assert (c.index, c.part, c.serial, c.bootloader) == (0, "CH552", "7D-E2-0F-BD", "2.5.0")
    assert not drv.opened                                    # every device closed again
    assert all(data[0] in (b.CMD_DETECT, b.CMD_READ_CONFIG) for _, data in drv.sent)   # read-only


def test_scan_without_devices():
    assert b.scan(FakeDriver({})) == []
