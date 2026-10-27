"""GUI version and build information.

VERSION is edited by hand for each release. The build date is not stored in the
source: tools/build_gui.ps1 writes gui/_build_info.py with the actual build time
just before running PyInstaller and deletes it afterwards, so only a built exe
carries a date.
"""
from __future__ import annotations

VERSION = "1.4.0"


def build_date() -> str | None:
    """Build time of this exe ("YYYY-MM-DD HH:MM"), or None when run from source."""
    try:
        from ._build_info import BUILD_DATE
    except ImportError:
        return None
    return BUILD_DATE


def version_text() -> str:
    date = build_date()
    return f"GUI v{VERSION} · 빌드 {date}" if date else f"GUI v{VERSION} · 개발 실행 (빌드 전)"
