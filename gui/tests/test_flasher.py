"""Firmware upload helpers (gui/flasher.py) and the update dialog."""
import sys
import textwrap
from pathlib import Path

import pytest

from gui import flasher

ERASE = "\x1b[2K"


def make_hex(path: Path, size: int, start: int = 0) -> Path:
    """Intel HEX with `size` bytes of 0x00 from `start`, 16 bytes per record."""
    lines = []
    addr = start
    while addr < start + size:
        n = min(16, start + size - addr)
        rec = bytes([n, addr >> 8 & 0xFF, addr & 0xFF, 0]) + bytes(n)
        lines.append(":" + (rec + bytes([-sum(rec) & 0xFF])).hex().upper())
        addr += n
    lines.append(":00000001FF")
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path


# ---------------------------------------------------------------- hex file

def test_hex_size_is_highest_address(tmp_path):
    assert flasher.check_hex(make_hex(tmp_path / "a.hex", 11587)) == 11587
    assert flasher.hex_size(make_hex(tmp_path / "b.hex", 10, start=0x100)) == 0x10A


def test_too_big_hex_rejected(tmp_path):
    path = make_hex(tmp_path / "big.hex", flasher.FLASH_SIZE + 1)
    with pytest.raises(flasher.FlashError) as e:
        flasher.check_hex(path)
    assert "너무 큽니다" in str(e.value)
    assert flasher.check_hex(make_hex(tmp_path / "max.hex", flasher.FLASH_SIZE)) == flasher.FLASH_SIZE


@pytest.mark.parametrize("text, msg", [
    ("hello\n", "Intel HEX"),
    (":10000000000000000000000000000000000000FF\n:00000001FF\n", "체크섬"),
    (":0100000000FF\n", "EOF"),
    (":00000001FF\n", "데이터가 없습니다"),
])
def test_bad_hex_rejected(tmp_path, text, msg):
    path = tmp_path / "bad.hex"
    path.write_text(text, encoding="ascii")
    with pytest.raises(flasher.FlashError) as e:
        flasher.check_hex(path)
    assert msg in str(e.value)


def test_missing_file(tmp_path):
    with pytest.raises(flasher.FlashError):
        flasher.check_hex(tmp_path / "none.hex")


def test_command_matches_flash_ps1(tmp_path):
    cmd = flasher.build_command(Path("up.exe"), tmp_path / "fw.hex", 30)
    assert cmd == ["up.exe", "-r", "30", "-t", "CH552", "-c", "1", str(tmp_path / "fw.hex")]


def test_uploader_from_env(tmp_path, monkeypatch):
    exe = tmp_path / flasher.UPLOADER_NAME
    exe.write_bytes(b"")
    monkeypatch.setenv("MACROKB_UPLOADER", str(exe))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "nothing"))
    assert flasher.find_uploader() == exe
    monkeypatch.setenv("MACROKB_UPLOADER", str(tmp_path / "missing.exe"))
    with pytest.raises(flasher.FlashError):
        flasher.find_uploader()


# ---------------------------------------------------------------- uploader output

# What vnproch55x printed in a real upload (dots redrawn after an erase code)
REAL_LOG = (
    "usbRertySeconds 60\ntarget: CH552\nconfig bytes: 1\n"
    + "No CH55x USB Found, retry...\n" * 3
    + "CH375 open OK\nMCU ID: 52 11\nFound Device CH552\nBootloader: 2.5.0\n"
    "ID: 7D E2 0F BD\nWrite 11587 bytes from bin file.\n"
    + "".join(f"{ERASE}{'.' * n}" for n in range(1, 51)) + "\nWrite complete!!!\nVerify chip\n"
    + "".join(f"{ERASE}{'.' * n}" for n in range(1, 51)) + "\nVerify complete!!!\n"
    "------------------------------------------------------------------\nReset OK\n"
)


def test_progress_parses_real_log_in_pieces():
    p = flasher.FlashProgress()
    seen = []
    for i in range(0, len(REAL_LOG), 7):     # arrives in arbitrary chunks
        p.feed(REAL_LOG[i:i + 7])
        seen.append((p.stage, p.percent))
    p.finish()
    assert (p.chip, p.bootloader, p.written) == ("CH552", "2.5.0", 11587)
    assert p.succeeded and p.reset and p.stage == flasher.STAGE_DONE and p.percent == 100
    assert p.lines.count("No CH55x USB Found, retry...") == 1
    percents = [pc for _, pc in seen]
    assert percents == sorted(percents)                    # never goes backwards
    assert any(st == flasher.STAGE_WRITING and 0 < pc < 50 for st, pc in seen)
    assert any(st == flasher.STAGE_VERIFYING and 50 < pc < 100 for st, pc in seen)


def test_progress_without_device_fails():
    p = flasher.FlashProgress()
    p.feed("No CH55x USB Found, retry...\n" * 5 + "Can not find CH55x\n")
    p.finish()
    assert p.stage == flasher.STAGE_WAITING and not p.succeeded


# ---------------------------------------------------------------- dialog

pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def fake_uploader(tmp_path: Path, log: str, code: int) -> list[str]:
    script = tmp_path / "fake_uploader.py"
    script.write_text(textwrap.dedent(f"""
        import sys
        sys.stdout.write({log!r})
        sys.stdout.flush()
        sys.exit({code})
    """), encoding="utf-8")
    return [sys.executable, str(script)]


def chip(index=0, chip_id=0x52, uid=bytes.fromhex("7DE20FBD")):
    from gui.bootloader import ChipInfo
    return ChipInfo(index, chip_id, 0x11, "2.5.0", uid)


def make_dialog(tmp_path, chips, cmd=("unused",), prepare=lambda: "", hex_size=11587):
    from gui.flash_dialog import FirmwareDialog
    return FirmwareDialog(prepare, lambda hex_path: list(cmd),
                          hex_path=make_hex(tmp_path / "fw.hex", hex_size),
                          scan_fn=lambda: list(chips), auto_scan=False)


def run_dialog(qapp, tmp_path, log, code, hex_size=11587):
    cmd = fake_uploader(tmp_path, log, code)
    dlg = make_dialog(tmp_path, [chip()], cmd, hex_size=hex_size)
    assert dlg.process is None                             # choosing the file does not flash
    assert dlg.start_btn.isEnabled()
    assert dlg.start()
    assert dlg.process.waitForFinished(10000)
    qapp.processEvents()
    return dlg


def test_dialog_upload_success(qapp, tmp_path):
    dlg = run_dialog(qapp, tmp_path, REAL_LOG, 0)
    assert dlg.succeeded and dlg.bar.value() == 100
    assert "장입 완료" in dlg.stage_label.text()
    assert "Found Device CH552" in dlg.log.toPlainText()
    assert dlg.close_btn.text() == "닫기"


def test_dialog_upload_timeout(qapp, tmp_path):
    dlg = run_dialog(qapp, tmp_path, "No CH55x USB Found, retry...\n" * 3, 1)
    assert not dlg.succeeded
    assert "찾지 못했습니다" in dlg.stage_label.text()
    assert dlg.start_btn.isEnabled()                       # can try again


def test_dialog_refuses_oversized_hex(qapp, tmp_path):
    dlg = make_dialog(tmp_path, [chip()], hex_size=flasher.FLASH_SIZE + 16)
    assert not dlg.start_btn.isEnabled() and not dlg.start()
    assert "너무 큽니다" in dlg.size_label.text()


def test_dialog_lists_chips_and_waits_for_one(qapp, tmp_path):
    chips = []
    dlg = make_dialog(tmp_path, chips)
    assert dlg.chip_table.rowCount() == 0
    assert not dlg.start_btn.isEnabled() and not dlg.start()   # no chip yet
    assert "칩이 없습니다" in dlg.chip_status.text()

    chips.append(chip())
    dlg.scan()
    row = [dlg.chip_table.item(0, c).text() for c in range(4)]
    assert row == ["1", "CH552", "7D-E2-0F-BD", "2.5.0"]
    assert dlg.start_btn.isEnabled() and dlg.process is None
    assert "ID 7D-E2-0F-BD" in dlg.log.toPlainText()

    chips.append(chip(1, uid=bytes.fromhex("01020304")))
    dlg.scan()
    assert dlg.chip_table.rowCount() == 2
    assert dlg.chip_table.item(1, 2).text() == "01-02-03-04"
    assert not dlg.start_btn.isEnabled()                       # which one is unclear
    assert "2개" in dlg.chip_status.text()


def test_dialog_refuses_other_chip(qapp, tmp_path):
    dlg = make_dialog(tmp_path, [chip(chip_id=0x54)])
    assert dlg.chip_table.item(0, 1).text() == "CH554"
    assert not dlg.start_btn.isEnabled()
    assert "CH554" in dlg.chip_status.text()


def test_dialog_boot_button_runs_prepare(qapp, tmp_path):
    calls = []
    dlg = make_dialog(tmp_path, [], prepare=lambda: calls.append(1) or "업데이트 모드로 바꿨습니다")
    dlg.boot_btn.click()
    assert calls == [1] and "업데이트 모드로 바꿨습니다" in dlg.log.toPlainText()
    assert dlg.process is None                                 # still waits for [장입]


def test_dialog_scan_error_shown_once(qapp, tmp_path):
    from gui.flash_dialog import FirmwareDialog

    def broken():
        raise flasher.FlashError("WCH 드라이버가 없습니다")
    dlg = FirmwareDialog(lambda: "", lambda p: ["unused"], scan_fn=broken, auto_scan=False,
                         hex_path=make_hex(tmp_path / "fw.hex", 100))
    dlg.scan()
    assert dlg.log.toPlainText().count("WCH 드라이버가 없습니다") == 1
    assert "WCH 드라이버" in dlg.chip_status.text() and not dlg.start_btn.isEnabled()


def test_main_window_boots_open_device_before_upload(qapp, tmp_path):
    from gui import protocol as p
    from gui.app import MainWindow, make_mock_connector
    from gui.transport import MockDevice
    mock = MockDevice(capacity=128, storage=p.encode_blob(["secret"] + [""] * 8))
    w = MainWindow(make_mock_connector(mock), auto_reconnect=False)
    w.connect_device()
    hint = w.prepare_bootloader()
    assert mock.in_bootloader and not w.connected
    assert "업데이트 모드로 바꿨습니다" in hint
    assert w.slots == [""] * 9                             # nothing left on screen
    w.close()


def test_main_window_locked_device_needs_key_d(qapp, tmp_path):
    from gui import protocol as p
    from gui.app import MainWindow, make_mock_connector
    from gui.transport import MockDevice
    mock = MockDevice(capacity=128, storage=p.encode_blob([""] * 9, [0, 1, 2, 3]))
    w = MainWindow(make_mock_connector(mock), auto_reconnect=False)
    w.connect_device()
    hint = w.prepare_bootloader()
    assert not mock.in_bootloader                          # BOOT is refused while locked
    assert "키 D" in hint and "잠겨" in hint
    w.close()
