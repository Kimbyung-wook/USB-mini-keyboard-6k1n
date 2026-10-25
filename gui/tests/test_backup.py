import json

import pytest

from gui import backup


def test_round_trip(tmp_path):
    slots = [f"slot{i}{{ENTER}}" for i in range(9)]
    slots[3] = "multi\nline"
    path = tmp_path / "b.json"
    backup.save(path, slots)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["format"] == backup.FORMAT_NAME and len(doc["slots"]) == 9
    assert doc["slots"][6]["label"] == "노브 시계 방향"
    assert backup.load(path) == slots


def test_partial_and_crlf():
    text = json.dumps({"format": backup.FORMAT_NAME, "version": 1,
                       "slots": [{"slot": 8, "macro": "a\r\nb"}]})
    assert backup.from_json(text) == [""] * 8 + ["a\nb"]


@pytest.mark.parametrize("text", [
    "not json",
    "{}",
    json.dumps({"format": backup.FORMAT_NAME, "version": 2, "slots": []}),
    json.dumps({"format": backup.FORMAT_NAME, "version": 1, "slots": [{"slot": 9, "macro": ""}]}),
    json.dumps({"format": backup.FORMAT_NAME, "version": 1, "slots": [{"slot": 0}]}),
])
def test_invalid(text):
    with pytest.raises(backup.BackupError):
        backup.from_json(text)
