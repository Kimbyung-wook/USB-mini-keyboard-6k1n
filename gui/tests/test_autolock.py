"""Auto-lock minutes: the settings slot after the lock slot (firmware 1.4.0)."""
import pytest

from gui import protocol as p
from gui.device import DeviceClient, DeviceError
from gui.transport import MockDevice

SLOTS = ["a", "b"] + [""] * 7
LOCK = [0, 1, 2, 6]
NEW_FW = p.Board(features=p.BOARD_FEATURE_RGB_LED | p.BOARD_FEATURE_LOCK | p.BOARD_FEATURE_AUTO_LOCK)


def test_blob_round_trip():
    blob = p.encode_blob(SLOTS, LOCK, autolock=15)
    assert blob[3] == 11 and len(blob) == p.blob_size(SLOTS, LOCK, 15)   # 9 slots + lock + settings
    cfg = p.decode_blob(blob)
    assert cfg.valid and cfg.lock == LOCK and cfg.autolock == 15 and cfg.slots == SLOTS


def test_no_settings_slot_without_pattern_or_minutes():
    assert p.encode_blob(SLOTS, LOCK, autolock=0) == p.encode_blob(SLOTS, LOCK)
    assert p.encode_blob(SLOTS, autolock=5) == p.encode_blob(SLOTS)   # nothing to lock
    assert p.blob_size(SLOTS, autolock=5) == p.blob_size(SLOTS)
    assert p.decode_blob(p.encode_blob(SLOTS, LOCK)).autolock == 0


def test_minutes_range():
    assert p.autolock_error(255) is None and p.autolock_error(256)
    with pytest.raises(p.BlobError):
        p.encode_blob(SLOTS, LOCK, autolock=300)


def test_feature_bit_from_hello():
    old = p.parse_hello_result(p.encode_hello_result(p.HelloInfo(2, 1, 3, 9, 128, board_info=p.DEFAULT_BOARD)))
    new = p.parse_hello_result(p.encode_hello_result(p.HelloInfo(2, 1, 4, 9, 128, board_info=NEW_FW)))
    assert not old.supports_autolock and new.supports_autolock
    assert new.board == p.DEFAULT_BOARD          # features are not part of the layout


def test_device_refuses_autolock_on_old_firmware():
    client = DeviceClient(MockDevice(capacity=128), sleep=lambda s: None)
    client.hello()
    with pytest.raises(DeviceError, match="자동 잠금"):
        client.write_config(SLOTS, lock=LOCK, autolock=5)
    mock = MockDevice(capacity=128, board=NEW_FW)
    client = DeviceClient(mock, sleep=lambda s: None)
    client.hello()
    client.write_config(SLOTS, lock=LOCK, autolock=5)
    assert mock.stored_config().autolock == 5


# ---------------------------------------------------------------- GUI

pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def window(mock):
    from gui.app import MainWindow, make_mock_connector
    w = MainWindow(make_mock_connector(mock), auto_reconnect=False)
    w.ask = lambda t, m: True
    w.inform = w.error = lambda t, m: None
    return w


def test_window_edits_and_saves_autolock(qapp):
    mock = MockDevice(capacity=128, board=NEW_FW, storage=p.encode_blob(SLOTS, LOCK, autolock=3))
    mock.power_cycle()
    mock.enter_pattern(LOCK)
    w = window(mock)
    assert w.connect_device()
    spin = w.lock_editor.autolock_spin
    assert w.autolock == 3 and spin.value() == 3 and spin.isEnabled()
    spin.setValue(10)
    assert w.autolock == 10 and w.has_unsaved()
    assert w.save_to_device(confirm=False)
    assert mock.stored_config().autolock == 10 and not w.has_unsaved()
    w.lock_editor.clear_btn.click()                       # no pattern: nothing to lock
    assert w.autolock == 0 and not spin.isEnabled()
    w.baseline = list(w.slots)
    w.lock_baseline, w.autolock_baseline = list(w.lock), w.autolock
    w.close()


def test_window_disables_autolock_on_old_firmware(qapp):
    w = window(MockDevice(capacity=128, storage=p.encode_blob(SLOTS)))
    assert w.connect_device()
    w.set_lock(LOCK)
    assert not w.lock_editor.autolock_spin.isEnabled()
    assert "1.4.0" in w.lock_editor.autolock_note.text()
    w.lock_baseline = list(w.lock)
    w.close()
