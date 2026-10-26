"""Version / build-date text (gui/version.py)."""
import sys
import types

from gui import version


def test_source_run_has_no_build_date(monkeypatch):
    monkeypatch.setitem(sys.modules, "gui._build_info", None)  # import fails
    assert version.build_date() is None
    assert version.version_text() == f"GUI v{version.VERSION} · 개발 실행 (빌드 전)"


def test_built_exe_shows_build_date(monkeypatch):
    info = types.ModuleType("gui._build_info")
    info.BUILD_DATE = "2026-10-26 01:23"
    monkeypatch.setitem(sys.modules, "gui._build_info", info)
    assert version.build_date() == "2026-10-26 01:23"
    assert version.version_text() == f"GUI v{version.VERSION} · 빌드 2026-10-26 01:23"
