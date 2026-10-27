"""Board info (docs/BOARD_INFO.md): slot names, HELLO bytes 17-35, and a GUI
built for keyboards other than the 6-key one."""
import pytest

from gui import protocol as p
from gui.device import DeviceClient, IncompatibleDeviceError
from gui.transport import MockDevice

BIG = p.Board(keys=12, knobs=2, rows=3, name="MK12K2N", uid=bytes.fromhex("7DE20FBD"))
NO_KNOB = p.Board(keys=3, knobs=0, rows=1, name="MK3K")


def test_default_board_keeps_todays_slots():
    b = p.DEFAULT_BOARD
    assert (b.slot_count, b.lock_slot, b.cols) == (9, 9, 3)
    assert b.slot_names == ["A", "B", "C", "D", "E", "F", "CW", "CCW", "PRESS"]
    assert b.slot_labels[6:] == ["노브 시계 방향", "노브 반시계 방향", "노브 누르기"]
    assert (p.SLOT_COUNT, p.SLOT_KNOB_CW, p.SLOT_KNOB_PRESS, p.SLOT_LOCK) == (9, 6, 8, 9)
    assert p.lock_text([0, 3, 6, 7, 8]) == "A → D → ↻ → ↺ → ●"


def test_board_with_two_knobs():
    assert (BIG.slot_count, BIG.cols) == (18, 4)
    assert BIG.knob_slot(1, 0) == 15 and BIG.knob_of(17) == (1, 2) and BIG.knob_of(11) is None
    assert BIG.slot_names[12:] == ["CW", "CCW", "PRESS", "CW2", "CCW2", "PRESS2"]
    assert BIG.slot_label(15) == "노브 2 시계 방향"
    assert p.lock_text([11, 12, 17], BIG) == "L → 1↻ → 2●"
    assert BIG.summary == "키 12 + 노브 2" and NO_KNOB.summary == "키 3"


@pytest.mark.parametrize("kw", [dict(keys=0), dict(keys=4, rows=5), dict(keys=40, knobs=8)])
def test_bad_board_rejected(kw):
    with pytest.raises(ValueError):
        p.Board(**kw)


def test_hello_board_info_round_trip():
    info = p.HelloInfo(2, 1, 3, BIG.slot_count, 512, fw_patch=0, board_info=BIG)
    result = p.encode_hello_result(info)
    assert result[14] == p.BOARD_INFO_VERSION          # packet byte 17
    got = p.parse_hello_result(result)
    assert got.board == BIG and got.board.uid == BIG.uid


def test_hello_without_board_info_is_default_board():
    info = p.parse_hello_result(p.encode_hello_result(p.HelloInfo(2, 1, 2, 9, 128)) + bytes(30))
    assert info.board_info is None and info.board == p.DEFAULT_BOARD


def test_blob_uses_board_slots_and_lock_slot():
    slots = [f"m{i}" for i in range(BIG.slot_count)]
    lock = [0, 11, 12, 17]
    cfg = p.decode_blob(p.encode_blob(slots, lock, BIG), BIG)
    assert cfg.valid and cfg.slots == slots and cfg.lock == lock
    assert p.lock_error([18, 0, 1, 2], BIG)              # past the last slot
    with pytest.raises(p.BlobError):
        p.encode_blob(slots[:9], board=BIG)


def client_for(board: p.Board, **kw) -> tuple[DeviceClient, MockDevice]:
    mock = MockDevice(board=board, **kw)
    return DeviceClient(mock, sleep=lambda s: None), mock


def test_device_round_trip_on_other_board():
    client, mock = client_for(BIG)
    assert client.hello().board == BIG
    slots = [""] * BIG.slot_count
    slots[17] = "{ENTER}"
    client.write_config(slots, lock=[0, 1, 2, 17])
    cfg = client.read_config()
    assert cfg.slots == slots and cfg.lock == [0, 1, 2, 17]
    client.test(17)
    assert mock.typed == [17]
    with pytest.raises(ValueError):
        client.test(18)


def test_slot_count_must_match_board_info():
    mock = MockDevice(board=BIG)
    mock.board = p.DEFAULT_BOARD      # HELLO says 9 slots, board info says 18
    with pytest.raises(IncompatibleDeviceError, match="슬롯 수"):
        DeviceClient(mock, sleep=lambda s: None).hello()


# ---------------------------------------------------------------- GUI

pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def window(mock):
    from gui.app import MainWindow, make_mock_connector
    w = MainWindow(make_mock_connector(mock), auto_reconnect=False)
    w.dialogs = []
    w.ask = lambda t, m: (w.dialogs.append(("ask", t, m)), True)[1]
    w.inform = lambda t, m: w.dialogs.append(("inform", t, m))
    w.error = lambda t, m: w.dialogs.append(("error", t, m))
    return w


@pytest.mark.parametrize("board", [BIG, NO_KNOB])
def test_window_builds_the_connected_board(qapp, board):
    w = window(MockDevice(capacity=512, board=board))
    assert len(w.device_view.buttons) == 9              # default board before connecting
    assert w.connect_device()
    assert len(w.device_view.buttons) == board.slot_count
    assert len(w.lock_editor.input_buttons) == board.slot_count
    assert len(w.slots) == board.slot_count
    assert f"{board.name} ({board.summary})" in w.conn_label.text()
    last = board.slot_count - 1
    w.device_view.buttons[last].click()
    assert w.current == last and board.slot_label(last) in w.editor.title.text()
    w.close()


def test_window_saves_on_other_board(qapp):
    mock = MockDevice(capacity=512, board=BIG)
    w = window(mock)
    w.connect_device()
    w.select_slot(16)
    w.editor.edit.setPlainText("{CTRL+C}")
    w.lock_editor.input_buttons[0].click()
    for slot in (5, 12, 17):
        w.lock_editor.input_buttons[slot].click()
    assert w.lock == [0, 5, 12, 17]
    assert w.save_to_device(confirm=False)
    cfg = mock.stored_config()
    assert cfg.slots[16] == "{CTRL+C}" and cfg.lock == [0, 5, 12, 17]
    w.close()


def test_window_switching_keyboards_asks_about_unsaved_edits(qapp):
    from gui.app import MainWindow
    small = MockDevice(capacity=128)
    big = MockDevice(capacity=512, board=BIG)
    current = [small]

    def connect():
        current[0].reconnect()
        return current[0]
    w = MainWindow(connect, auto_reconnect=False)
    asked = []
    w.ask = lambda t, m: (asked.append(t), False)[1]
    w.error = w.inform = lambda t, m: None
    w.connect_device()
    w.set_slot_text(0, "unsaved")
    w.disconnect_device()                 # screen is cleared on disconnect
    w.set_slot_text(0, "typed while away")
    current[0] = big
    assert not w.connect_device()          # answered "no": stays as it was
    assert asked == ["다른 키보드"] and w.slots[0] == "typed while away"
    assert len(w.device_view.buttons) == 9
    w.baseline = list(w.slots)
    w.close()


def test_connection_bar_has_three_lines(qapp):
    w = window(MockDevice(capacity=512, board=BIG, fw=(1, 4)))
    w.connect_device()
    state, board, fw = w.conn_label.text().split("<br>")
    assert "연결됨 - 잠금 안 씀" in state
    assert board == f"{BIG.name} ({BIG.summary}) / 용량 512바이트"
    assert fw.startswith("펌웨어 v1.4")
    w.close()
