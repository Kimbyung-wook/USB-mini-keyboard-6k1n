"""Script entry point: python gui/main.py [--mock]"""
import sys
from pathlib import Path

# Make the repository root importable so the "gui" package resolves.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gui.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
