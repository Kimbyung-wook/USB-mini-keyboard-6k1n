"""Headless smoke test of the main window against the mock device."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from gui import protocol as p  # noqa: E402
from gui.app import MainWindow, SAMPLE_SLOTS, make_mock_connector  # noqa: E402
from gui.transport import MockDevice  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(qapp):
    mock = MockDevice(storage=p.encode_blob(SAMPLE_SLOTS))
    w = MainWindow(make_mock_connector(mock), auto_reconnect=False)
    w.mock = mock
    w.dialogs = []
    w.answer = True
    w.ask = lambda t, m: (w.dialogs.append(("ask", t, m)), w.answer)[1]
    w.inform = lambda t, m: w.dialogs.append(("inform", t, m))
    w.error = lambda t, m: w.dialogs.append(("error", t, m))
    w.show()
    yield w
    w.baseline = list(w.slots)  # avoid the unsaved-changes prompt
    w.close()


def test_connect_reads_device(win):
    assert win.connect_device()
    assert win.connected and win.slots == SAMPLE_SLOTS
    assert "연결됨" in win.conn_label.text() and "4096" in win.conn_label.text()
    assert not win.has_unsaved()


def test_select_edit_save_readback(win):
    win.connect_device()
    win.device_view.buttons[4].click()          # key E
    assert win.current == 4
    assert win.editor.text() == SAMPLE_SLOTS[4]

    win.editor.edit.setPlainText("typed{TAB}text\nnext")
    assert win.slots[4] == "typed{TAB}text\nnext"
    assert win.is_modified(4) and "*" in win.device_view.buttons[4].text()
    assert win.windowTitle().startswith("*")

    win.select_slot(p.SLOT_KNOB_PRESS)
    win.editor.insert("{CTRL+SHIFT+ESC}")
    assert win.slots[8].endswith("{CTRL+SHIFT+ESC}")

    assert win.save_to_device()
    assert not win.has_unsaved()
    assert win.mock.stored_config().slots == win.slots

    # Change locally, read back over it (confirm prompt answered yes).
    win.set_slot_text(0, "scratch")
    assert win.read_from_device()
    assert any(d[0] == "ask" for d in win.dialogs)
    assert win.slots[4] == "typed{TAB}text\nnext"
    assert win.slots[0] == SAMPLE_SLOTS[0]


def test_invalid_slot_blocks_save(win):
    win.connect_device()
    win.select_slot(2)
    win.editor.edit.setPlainText("안녕 {FOO}")
    assert len(win.editor.errors) == 2
    assert "행" in win.editor.status.text()
    commits = win.mock.commit_count
    assert not win.save_to_device()
    assert win.mock.commit_count == commits
    assert win.dialogs[-1][0] == "error"


def test_slot_buttons_show_length(win):
    win.connect_device()
    assert f"· {len(SAMPLE_SLOTS[0])}자" in win.device_view.buttons[0].text()
    win.set_slot_text(1, "x" * 20)
    assert "· 20자" in win.device_view.buttons[1].text()
    win.set_slot_text(2, "")
    assert "· 0자" in win.device_view.buttons[2].text()


def test_capacity_shows_characters_left(qapp):
    # Same capacity as firmware v1.0 (128-byte DataFlash)
    mock = MockDevice(capacity=128, storage=p.encode_blob(SAMPLE_SLOTS))
    w = MainWindow(make_mock_connector(mock), auto_reconnect=False)
    w.connect_device()
    chars = sum(len(s) for s in SAMPLE_SLOTS)
    assert f"{chars}자 입력" in w.capacity_bar.format()
    assert f"{128 - p.blob_size(SAMPLE_SLOTS)}자 더 입력 가능" in w.capacity_bar.format()
    w.set_slot_text(0, w.slots[0] + "x" * 10)  # 125 + 10 = 135 bytes
    assert "7자 초과" in w.capacity_bar.format()
    assert not w.save_btn.isEnabled()
    w.baseline = list(w.slots)
    w.close()


def test_capacity_over_blocks_save(win):
    win.connect_device()
    win.set_slot_text(0, "x" * 5000)
    assert not win.save_btn.isEnabled()
    assert "초과" in win.capacity_bar.format()
    assert not win.save_to_device(confirm=False)


def test_test_input_countdown(win):
    win.connect_device()
    win.select_slot(1)
    assert win.start_test()
    assert "3초" in win.test_btn.text()
    for _ in range(3):
        win._test_tick()
    assert win.mock.typed == [1]
    assert win.test_btn.isEnabled()


def test_json_export_import(win, tmp_path):
    win.connect_device()
    path = tmp_path / "backup.json"
    assert win.export_json(str(path))
    win.set_slot_text(3, "changed")
    assert win.import_json(str(path))
    assert win.slots == SAMPLE_SLOTS


def test_close_with_unsaved_asks(win):
    win.connect_device()
    win.set_slot_text(0, "unsaved")
    win.answer = False
    win.close()
    assert win.isVisible()
    win.answer = True


def test_disconnected_device_handled(win):
    win.connect_device()
    win.mock.connected = False
    assert not win.read_from_device(confirm=False)
    assert not win.connected
    assert "연결 안 됨" in win.conn_label.text()
