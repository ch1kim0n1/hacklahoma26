from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_renderer_has_blind_mode_controls_and_live_regions():
    html = _read(ROOT / "electron" / "renderer" / "index.html")
    assert 'id="blindModeToggle"' in html
    assert 'id="livePolite"' in html
    assert 'id="liveAssertive"' in html
    assert 'aria-live="polite"' in html
    assert 'aria-live="assertive"' in html
    assert 'id="commandInput"' in html and 'aria-label="Command input"' in html


def test_renderer_js_has_shortcuts_and_conflict_guard():
    app_js = _read(ROOT / "electron" / "renderer" / "app.js")
    assert "repeat last response" in app_js
    assert "read status" in app_js
    assert "if (key === \"v\")" in app_js
    assert "if (key === \"r\")" in app_js
    assert "if (key === \"s\")" in app_js
    assert "state.preferences.blindModeEnabled && state.preferences.visualOnly" in app_js
    assert "elements.visualOnlyToggle.disabled = Boolean(state.preferences.blindModeEnabled)" in app_js
    assert "onAnnouncement" in app_js


def test_main_process_accepts_accessibility_preferences():
    main_js = _read(ROOT / "electron" / "main.js")
    assert "blind_mode_enabled: payload?.blindModeEnabled" in main_js
    assert "narration_level: payload?.narrationLevel" in main_js
    assert "screen_reader_hints_enabled: payload?.screenReaderHintsEnabled" in main_js
    assert "runtime:announcement" in main_js
