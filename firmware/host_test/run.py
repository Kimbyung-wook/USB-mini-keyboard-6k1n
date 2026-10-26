"""Build firmware storage/macro code with gcc and check it against the GUI encoder.

Run from the repo root:  gui\\.venv\\Scripts\\python firmware\\host_test\\run.py
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SRC = ROOT / "firmware" / "macro_keyboard" / "src"
sys.path.insert(0, str(ROOT))

from gui import protocol as p  # noqa: E402

SHIFT, CTRL, ALT, WIN = 0x02, 0x01, 0x04, 0x08


def keys(*pairs: tuple[int, int] | str) -> str:
    """Expected report string: (mods, key) pairs, or 'D50'-style delay markers."""
    out = []
    for item in pairs:
        out.append(item if isinstance(item, str) else f"{item[0]:02x}:{item[1]:02x}")
    return " ".join(out)


def build(out_dir: Path) -> Path:
    exe = out_dir / "host_test.exe"
    subprocess.run(
        ["gcc", "-std=c99", "-Wall", "-I", str(HERE / "stub"), "-I", str(SRC),
         str(HERE / "host_test.c"), str(SRC / "storage.c"), str(SRC / "macro.c"),
         str(SRC / "lock.c"),
         "-o", str(exe)],
        check=True)
    return exe


def run(exe: Path, out_dir: Path, blob: bytes, capslock: bool = False,
        extra: list[str] | None = None) -> list[str]:
    path = out_dir / "blob.bin"
    path.write_bytes(blob)
    args = [str(exe), str(path)] + (["caps"] if capslock else []) + (extra or [])
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.splitlines()


def lock_states(lines: list[str]) -> list[str]:
    """'lock locked flags 3' lines -> ['locked 3', ...]"""
    return [" ".join(line.split()[1::2]) for line in lines if line.startswith("lock ")]


def slot_lines(lines: list[str]) -> dict[int, str]:
    result = {}
    for line in lines:
        if line.startswith("slot "):
            head, _, rest = line.partition(":")
            result[int(head.split()[1])] = rest.strip()
    return result


failures = 0


def check(name: str, got: str, want: str) -> None:
    global failures
    ok = got == want
    failures += not ok
    print(f"{'PASS' if ok else 'FAIL'} {name}" + ("" if ok else f"\n   want: {want}\n   got:  {got}"))


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        exe = build(out)

        slots = [
            "Hello, World!{ENTER}",
            "{CTRL+C}{ctrl+shift+esc}{ALT+F4}{WIN+r}",
            "{{x}}",
            "a{DELAY:50}b",
            "{CTRL++}",
            "ab\ncd",
            "{UP}",
            "{DOWN}",
            "",
        ]
        lines = run(exe, out, p.encode_blob(slots))
        check("blank DataFlash reads as empty", lines[0], "blank slot0 len 0")
        check("write status", lines[1], "write status 0")
        check("commit status", lines[2], "commit status 0")
        got = slot_lines(lines)
        check("plain text + ENTER", got[0], keys(
            (SHIFT, 0x0b), (0, 0x08), (0, 0x0f), (0, 0x0f), (0, 0x12), (0, 0x36), (0, 0x2c),
            (SHIFT, 0x1a), (0, 0x12), (0, 0x15), (0, 0x0f), (0, 0x07), (SHIFT, 0x1e), (0, 0x28)))
        check("combos", got[1], keys((CTRL, 0x06), (CTRL | SHIFT, 0x29), (ALT, 0x3d), (WIN, 0x15)))
        check("brace escapes", got[2], keys((SHIFT, 0x2f), (0, 0x1b), (SHIFT, 0x30)))
        delay = got[3].split()
        check("delay waits ~50 ms", " ".join(x for x in delay if not x.startswith("D")),
              keys((0, 0x04), (0, 0x05)))
        d = [int(x[1:]) for x in delay if x.startswith("D")]
        check("delay length", str(bool(d) and 50 <= d[0] <= 53), "True")
        check("CTRL++", got[4], keys((CTRL | SHIFT, 0x2e)))
        check("newline is ENTER", got[5], keys((0, 0x04), (0, 0x05), (0, 0x28), (0, 0x06), (0, 0x07)))
        check("knob UP", got[6], keys((0, 0x52)))
        check("knob DOWN", got[7], keys((0, 0x51)))
        check("empty slot", got[8], "(empty)")
        check("press/release pairing", lines[-1], "errors 0")

        lines = run(exe, out, p.encode_blob(["aB"] + [""] * 8), capslock=True)
        check("caps lock inverts shift for letters", slot_lines(lines)[0], keys((SHIFT, 0x04), (0, 0x05)))

        # Largest blob that fits: header 8 + 9 lengths 18 + 102 chars = 128
        full = ["x" * 102] + [""] * 8
        lines = run(exe, out, p.encode_blob(full))
        check("128-byte blob commits", lines[2], "commit status 0")
        check("128-byte blob types 102 chars", str(len(slot_lines(lines)[0].split())), "102")

        lines = run(exe, out, p.encode_blob(["x" * 103] + [""] * 8))
        check("129-byte blob rejected (TOO_BIG)", lines[1], f"write status {p.Status.TOO_BIG}")

        bad = bytearray(p.encode_blob(slots))
        bad[-1] ^= 0xFF  # corrupt payload, header CRC unchanged
        lines = run(exe, out, bytes(bad))
        check("corrupt payload rejected (BAD_CRC)", lines[2], f"commit status {p.Status.BAD_CRC}")

        # Lock pattern A B C knob-CW (slot 9 of the blob)
        short = ["Hi{ENTER}", "{CTRL+C}"] + [""] * 7
        lock = [0, 1, 2, 6]
        locked_blob = p.encode_blob(short, lock)
        # H = knob held 3 s (starts a pattern entry), t = entry timeout
        lines = run(exe, out, locked_blob, extra=["lock", "0126", "H", "0126"])
        check("lock blob commits", lines[2], "commit status 0")
        check("locked ignores inputs until the knob hold, then the pattern opens",
              " | ".join(lock_states(lines)), "locked 3 | locked 3 | unlocking 3 | open 1")

        lines = run(exe, out, locked_blob, extra=["lock", "H0124", "H0126"])
        check("wrong try goes back to locked, next try opens", " | ".join(lock_states(lines)[1:]),
              "locked 3 | open 1")

        lines = run(exe, out, locked_blob, extra=["lock"] + ["H1111"] * 5 + ["H0126"])
        states = lock_states(lines)
        check("5 wrong tries block", states[5], "blocked 7")
        check("blocked ignores the hold and the right pattern", states[6], "blocked 7")

        lines = run(exe, out, locked_blob, extra=["lock"] + ["H01t"] * 6 + ["H0126"])
        states = lock_states(lines)
        check("unfinished entries time out without counting", states[6], "locked 3")
        check("...and the pattern still opens after them", states[7], "open 1")

        lines = run(exe, out, locked_blob, extra=["lock", "H0126012"])
        check("extra inputs after opening are ignored", lock_states(lines)[1], "open 1")

        lines = run(exe, out, locked_blob, extra=["lock", "H0126", "H", "0126", "H0126"])
        check("re-lock: hold + pattern locks again, then unlocks again",
              " | ".join(lock_states(lines)[1:]), "open 1 | relock 1 | locked 3 | open 1")

        lines = run(exe, out, locked_blob, extra=["lock", "H0126", "H0124", "H01t"])
        check("re-lock: wrong pattern or timeout stays open",
              " | ".join(lock_states(lines)[1:]), "open 1 | open 1 | open 1")

        lines = run(exe, out, locked_blob, extra=["lock", "H0126"] + ["H1111"] * 5 + ["H0126"])
        states = lock_states(lines)
        check("re-lock: 4 wrong tries stay open", states[5], "open 1")
        check("re-lock: 5th wrong try locks anyway", states[6], "locked 3")
        check("...and it unlocks normally afterwards", states[7], "open 1")

        lines = run(exe, out, locked_blob,
                    extra=["lock", "H0126"] + ["H1111"] * 5 + ["H1111"] * 4 + ["H0126"])
        check("auto-lock gives 5 fresh unlock tries (4 wrong, then right)",
              lock_states(lines)[-1], "open 1")

        lines = run(exe, out, locked_blob,
                    extra=["lock", "H0126"] + ["H1111"] * 4 + ["H0126", "H0126"] + ["H1111"] * 4)
        check("re-lock failures reset after a successful re-lock and unlock",
              lock_states(lines)[-1], "open 1")

        lines = run(exe, out, locked_blob, extra=["lock", "H01w26", "H01w26"])
        # Both entries wait 10 s, so the pattern still finishes after the pause
        check("6 s pause: unlock and re-lock entries (10 s) go on",
              " | ".join(lock_states(lines)[1:]), "open 1 | locked 3")

        lines = run(exe, out, p.encode_blob(short), extra=["lock", "H"])
        check("no pattern starts open and the hold does nothing",
              " | ".join(lock_states(lines)), "open 0 | open 0")

        got = slot_lines(run(exe, out, locked_blob))
        check("slots still type next to the lock slot", f"{got[0]} | {got[1]} | {got[8]}",
              keys((SHIFT, 0x0b), (0, 0x0c), (0, 0x28)) + " | " + keys((CTRL, 0x06)) + " | (empty)")

        for name, bad_lock in (("3-step lock", [0, 1, 2]), ("9-step lock", [0] * 9),
                               ("lock step 9", [0, 1, 2, 9])):
            # Built by hand: encode_blob refuses invalid patterns
            payload = bytearray()
            for s in short:
                payload += len(s).to_bytes(2, "little") + s.encode()
            payload += len(bad_lock).to_bytes(2, "little") + bytes(bad_lock)
            blob = (b"MK" + bytes([1, 10]) + len(payload).to_bytes(2, "little")
                    + p.crc16_ccitt_false(bytes(payload)).to_bytes(2, "little") + payload)
            lines = run(exe, out, blob)
            check(f"{name} rejected (BAD_ARG)", lines[2], f"commit status {p.Status.BAD_ARG}")

        # A smaller config blanks what the old one left behind
        small = out / "small.bin"
        small.write_bytes(p.encode_blob([""] * 9))
        lines = run(exe, out, p.encode_blob(full), extra=["tail", str(small)])
        check("old bytes past a new blob are blanked", lines[-1], "tail dirty 0")

    print("all passed" if failures == 0 else f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
