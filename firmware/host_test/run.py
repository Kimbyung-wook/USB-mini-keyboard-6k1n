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
         "-o", str(exe)],
        check=True)
    return exe


def run(exe: Path, out_dir: Path, blob: bytes, capslock: bool = False) -> list[str]:
    path = out_dir / "blob.bin"
    path.write_bytes(blob)
    args = [str(exe), str(path)] + (["caps"] if capslock else [])
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.splitlines()


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

    print("all passed" if failures == 0 else f"{failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
