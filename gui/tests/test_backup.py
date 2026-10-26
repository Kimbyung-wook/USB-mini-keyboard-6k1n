import json

import pytest

from gui import backup
from gui import protocol as p


def test_round_trip(tmp_path):
    slots = [f"slot{i}{{ENTER}}" for i in range(9)]
    slots[3] = "multi\nline"
    path = tmp_path / "b.json"
    backup.save(path, slots)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["format"] == backup.FORMAT_NAME and len(doc["slots"]) == 9
    assert doc["slots"][6]["label"] == "노브 시계 방향"
    assert doc["board"] == {"name": "MK6K1N", "keys": 6, "knobs": 1}
    assert backup.load(path) == (slots, [])


def test_partial_and_crlf():
    text = json.dumps({"format": backup.FORMAT_NAME, "version": 1,
                       "slots": [{"slot": 8, "macro": "a\r\nb"}]})
    assert backup.from_json(text) == [""] * 8 + ["a\nb"]


@pytest.mark.parametrize("text", [
    "not json",
    "{}",
    json.dumps({"format": backup.FORMAT_NAME, "version": 2, "slots": []}),
    json.dumps({"format": backup.FORMAT_NAME, "version": 1, "slots": [{"slot": -1, "macro": ""}]}),
    json.dumps({"format": backup.FORMAT_NAME, "version": 1, "slots": [{"slot": 0}]}),
])
def test_invalid(text):
    with pytest.raises(backup.BackupError):
        backup.from_json(text)


def test_slot_beyond_board_is_skipped():
    text = json.dumps({"format": backup.FORMAT_NAME, "version": 1, "slots": [{"slot": 9, "macro": "x"}]})
    assert backup.read_json(text) == ([""] * 9, ["#9"])


def test_other_board_matches_by_key_name():
    big = p.Board(keys=12, knobs=2, rows=3)
    slots = [f"s{i}" for i in range(big.slot_count)]
    text = backup.to_json(slots, big)
    got, skipped = backup.read_json(text)           # into the 6-key board
    assert got == ["s0", "s1", "s2", "s3", "s4", "s5", "s12", "s13", "s14"]
    assert skipped == ["G", "H", "I", "J", "K", "L", "CW2", "CCW2", "PRESS2"]
    back, skipped = backup.read_json(backup.to_json(got), big)
    assert back[:6] == got[:6] and back[12:15] == got[6:] and skipped == []
