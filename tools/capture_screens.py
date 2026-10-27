"""Capture the GUI screens used in the docs (docs/images/*.png).

Runs the real windows off screen against the mock keyboard (no keyboard or
display needed), with the sample config, a lock pattern and auto-lock.

Run from the repo root:  gui\\.venv\\Scripts\\python tools\\capture_screens.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "images"
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gui import protocol as p  # noqa: E402
from gui.app import MOCK_FEATURES, SAMPLE_SLOTS, MainWindow, make_mock_connector  # noqa: E402
from gui.bootloader import ChipInfo  # noqa: E402
from gui.flash_dialog import FirmwareDialog  # noqa: E402
from gui.transport import MockDevice  # noqa: E402

WIDTH = 720
# Fits 128 bytes together with the lock pattern and auto-lock (SAMPLE_SLOTS does not)
SLOTS = list(SAMPLE_SLOTS)
SLOTS[3] = "{WIN+R}{DELAY:300}calc{ENTER}"
SLOTS[5] = "{CTRL+Z}"
LOCK = [0, 1, 2, 6]                      # A → B → C → ↻
UID = bytes.fromhex("7DE20FBD")
BOARD = p.Board(features=MOCK_FEATURES, uid=UID)


def keyboard(locked: bool) -> MockDevice:
    mock = MockDevice(capacity=128, fw=(1, 4, 0), build=(2026, 10, 27, 10, 8), board=BOARD,
                      storage=p.encode_blob(SLOTS, LOCK, autolock=10))
    mock.power_cycle()                   # starts locked, like a fresh plug-in
    if not locked:
        mock.enter_pattern(LOCK)
    return mock


def window(mock: MockDevice) -> MainWindow:
    w = MainWindow(make_mock_connector(mock), auto_reconnect=False)
    w.show()
    w.connect_device(quiet=True)
    w.resize(WIDTH, w.minimumSizeHint().height())
    return w


def connection_bar(w: MainWindow) -> QRect:
    """The top of the window, down to the key/knob picture."""
    return QRect(0, 0, w.width(), w.device_view.parentWidget().geometry().top())


def save(widget, name: str, rect: QRect | None = None) -> None:
    QApplication.processEvents()
    image = widget.grab(rect) if rect else widget.grab()
    image.save(str(OUT / name))
    print(f"{name}: {image.width()}x{image.height()}")


def main() -> None:
    app = QApplication.instance() or QApplication([])
    app.setFont(QFont("Malgun Gothic", 9))
    OUT.mkdir(parents=True, exist_ok=True)

    w = window(keyboard(locked=False))
    w.select_slot(3)                     # key D: a longer macro in the editor
    save(w, "gui_main.png")
    save(w.lock_editor, "gui_lock.png")
    save(w.centralWidget(), "gui_connected.png", connection_bar(w))
    w.close()

    w = window(keyboard(locked=True))
    save(w.centralWidget(), "gui_locked.png", connection_bar(w))
    w.close()

    os.chdir(ROOT)                       # show the hex path relative to the repo
    hex_path = Path("firmware/macro_keyboard/build") / "macro_keyboard-MK6K1N.hex"
    dlg = FirmwareDialog(lambda: "", scan_fn=lambda: [ChipInfo(0, 0x52, 0x11, "2.5.0", UID)],
                         auto_scan=False, keyboard=BOARD,
                         hex_path=hex_path if hex_path.is_file() else None)
    dlg.show()
    dlg.resize(800, 520)
    save(dlg, "gui_firmware.png")
    dlg.close()


if __name__ == "__main__":
    main()
