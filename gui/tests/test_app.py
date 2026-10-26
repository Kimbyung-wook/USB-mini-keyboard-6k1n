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


def test_version_shown(win):
    from gui.version import VERSION, version_text
    assert f"v{VERSION}" in win.windowTitle()
    assert win.version_label.text() == version_text()


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


# ---------------------------------------------------------------- lock pattern

LOCK = [0, 1, 2, p.SLOT_KNOB_CW]


def locked_window(qapp, slots=None, lock=LOCK):
    mock = MockDevice(capacity=128, storage=p.encode_blob(slots or SAMPLE_SLOTS[:2] + [""] * 7, lock))
    w = MainWindow(make_mock_connector(mock), auto_reconnect=False)
    w.mock = mock
    w.dialogs = []
    w.ask = lambda t, m: (w.dialogs.append(("ask", t, m)), True)[1]
    w.inform = lambda t, m: w.dialogs.append(("inform", t, m))
    w.error = lambda t, m: w.dialogs.append(("error", t, m))
    return w


def test_lock_editor_builds_pattern(win):
    win.connect_device()
    ed = win.lock_editor
    assert "없음" in ed.display.text()
    for slot in (0, 3):
        ed.input_buttons[slot].click()
    assert win.lock == [0, 3] and win.has_unsaved()
    assert "4단계 이상" in ed.status.text()
    assert not win.save_btn.isEnabled()
    ed.input_buttons[p.SLOT_KNOB_CW].click()
    ed.input_buttons[p.SLOT_KNOB_PRESS].click()
    assert ed.display.text() == "A → D → ↻ → ●"
    assert win.save_btn.isEnabled() and "패턴 암호 *" == ed.title()
    for _ in range(10):
        ed.input_buttons[1].click()
    assert len(win.lock) == p.LOCK_MAX_STEPS
    ed.back_btn.click()
    assert len(win.lock) == p.LOCK_MAX_STEPS - 1
    ed.clear_btn.click()
    assert win.lock == [] and not win.has_unsaved()


def test_lock_costs_capacity(win):
    win.connect_device()
    before = win.blob_size()
    win.set_lock(LOCK)
    assert win.blob_size() == before + 2 + len(LOCK)
    chars = sum(len(s) for s in SAMPLE_SLOTS)
    assert f"{chars}자 입력" in win.capacity_bar.format()   # the lock is not counted as text


def test_save_lock_then_replug_locks(win):
    win.connect_device()
    win.set_lock(LOCK)
    assert win.save_to_device()
    assert win.mock.stored_config().lock == LOCK
    assert "다시 꽂을 때부터" in win.dialogs[-1][2]
    assert not win.device_locked and not win.has_unsaved()

    win.mock.power_cycle()
    win.disconnect_device()
    win.connect_device()
    assert win.device_locked
    assert "잠김" in win.conn_label.text()
    assert not win.read_btn.isEnabled() and not win.test_btn.isEnabled()


def test_connect_locked_does_not_read_then_unlock_reads(qapp):
    w = locked_window(qapp)
    assert w.connect_device()
    assert w.device_locked and w.slots == [""] * 9
    assert not any(r.cmd == p.Cmd.READ for r in w.mock.requests)
    assert "패턴 암호를 입력" in w.conn_label.text()

    w.mock.enter_pattern([5, 5, 5, 5])          # wrong
    w._poll_device()
    assert w.device_locked
    w.mock.enter_pattern(LOCK)
    w._poll_device()
    assert not w.device_locked and "연결됨" in w.conn_label.text()
    assert w.slots[:2] == SAMPLE_SLOTS[:2] and w.lock == LOCK
    assert not w.has_unsaved()
    w.close()


def test_blocked_shown(qapp):
    w = locked_window(qapp)
    for _ in range(5):
        w.mock.enter_pattern([5, 5, 5, 5])
    w.connect_device()
    assert "다시 꽂으세요" in w.conn_label.text()
    w.close()


def test_save_while_locked_warns_and_overwrites(qapp):
    w = locked_window(qapp)
    w.connect_device()
    w.set_slot_text(0, "fresh")
    assert w.save_to_device()
    assert "모두 지우고" in [d for d in w.dialogs if d[0] == "ask"][-1][2]
    assert w.mock.stored_config().slots[0] == "fresh"
    assert not w.device_locked            # the new config has no pattern
    w.close()


def test_old_firmware_cannot_save_lock(qapp):
    mock = MockDevice(capacity=128, fw=(1, 0), protocol=1)
    w = MainWindow(make_mock_connector(mock), auto_reconnect=False)
    w.dialogs = []
    w.ask = lambda t, m: True
    w.inform = w.error = lambda t, m: w.dialogs.append((t, m))
    w.connect_device()
    assert not w.lock_editor.isEnabled()
    w.set_lock(LOCK)
    assert not w.save_to_device(confirm=False)
    assert "지원하지 않습니다" in w.dialogs[-1][1]
    assert mock.commit_count == 0
    w.baseline, w.lock_baseline = list(w.slots), list(w.lock)
    w.close()


def test_firmware_version_and_build_date_shown(qapp):
    mock = MockDevice(capacity=128, fw=(1, 1, 0), build=(2026, 10, 26, 11, 40))
    w = MainWindow(make_mock_connector(mock), auto_reconnect=False)
    w.connect_device()
    assert "펌웨어 v1.1.0 (빌드 2026-10-26 11:40)" in w.conn_label.text()
    w.close()


def test_poll_notices_relock_and_unlock(qapp):
    w = locked_window(qapp)
    w.mock.enter_pattern(LOCK)
    w.connect_device()
    assert not w.device_locked and w.read_btn.isEnabled()
    w.mock.relock(LOCK)                      # knob hold + pattern on the keyboard
    w._poll_device()
    assert w.device_locked and not w.read_btn.isEnabled()
    assert "노브를 3초" in w.conn_label.text()
    w.mock.enter_pattern(LOCK)
    w._poll_device()
    assert not w.device_locked
    w.close()


# ---------------------------------------------------------------- nothing shown without a keyboard

def test_startup_shows_nothing_and_cannot_edit(qapp):
    w = MainWindow(make_mock_connector(MockDevice()), auto_reconnect=False)
    assert w.slots == [""] * 9 and w.lock == []
    for widget in (w.device_view, w.editor, w.lock_editor, w.export_btn, w.import_btn):
        assert not widget.isEnabled()
    w.dialogs = []
    w.error = lambda t, m: w.dialogs.append((t, m))
    assert not w.import_json("unused.json") and not w.export_json("unused.json")
    w.close()


def test_disconnect_clears_slots_and_lock(win):
    win.connect_device()
    win.set_lock(LOCK)
    assert win.save_to_device(confirm=False)
    win.set_slot_text(0, "unsaved edit")
    win.disconnect_device()
    assert win.slots == [""] * 9 and win.lock == [] and not win.has_unsaved()
    assert "없음" in win.lock_editor.display.text()
    assert win.editor.text() == ""
    assert not win.windowTitle().startswith("*")
    assert win.connect_device()                 # read back from the device
    assert win.slots == SAMPLE_SLOTS and win.lock == LOCK


def test_relock_clears_screen(qapp):
    w = locked_window(qapp)
    w.mock.enter_pattern(LOCK)
    w.connect_device()
    assert w.slots[0] == SAMPLE_SLOTS[0] and w.lock == LOCK
    w.mock.relock(LOCK)
    w._poll_device()
    assert w.device_locked and w.slots == [""] * 9 and w.lock == []
    w.close()


def test_unplug_clears_screen(win):
    win.connect_device()
    win.mock.connected = False
    win.read_from_device(confirm=False)         # fails: the keyboard is gone
    assert not win.connected and win.slots == [""] * 9
