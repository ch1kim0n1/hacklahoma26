import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYLINK_DIR = ROOT / "pylink"
sys.path.insert(0, str(PYLINK_DIR))

from core.nlu.parser import parse_intent
from core.runtime.orchestrator import PixelLinkRuntime
from desktop_bridge import (
    _accessibility_state,
    _announcement_payload,
    _blind_mode_guidance,
    _normalize_narration_level,
)


def test_blind_mode_intents_parse():
    assert parse_intent("enable blind mode").name == "set_blind_mode"
    assert parse_intent("turn off blind mode").entities.get("enabled") is False
    assert parse_intent("I am blind and need help").entities.get("enabled") is True
    assert parse_intent("I'm blind and need help").name == "set_blind_mode"
    assert parse_intent("read status").name == "read_status"
    assert parse_intent("repeat last response").name == "repeat_last_response"
    assert parse_intent("blind help").name == "blind_help"


def test_bridge_accessibility_helpers():
    assert _normalize_narration_level("verbose") == "verbose"
    assert _normalize_narration_level("anything") == "concise"

    acc = _accessibility_state(
        blind_mode_enabled=True,
        narration_level="verbose",
        screen_reader_hints_enabled=False,
        last_announcement="hello",
    )
    assert acc["blind_mode_enabled"] is True
    assert acc["narration_level"] == "verbose"
    assert acc["screen_reader_hints_enabled"] is False
    assert acc["last_announcement"] == "hello"

    announce = _announcement_payload("Blind mode enabled", "assertive")
    assert announce["status"] == "announcement"
    assert announce["priority"] == "assertive"
    assert announce["message"] == "Blind mode enabled"


def test_blind_mode_guidance_for_missing_voice_paths():
    msg = _blind_mode_guidance(voice_output_enabled=False, voice_input_enabled=False)
    assert "text-to-speech is unavailable" in msg
    assert "speech-to-text is unavailable" in msg
    assert _blind_mode_guidance(True, True) == ""


def test_runtime_local_blind_mode_commands():
    runtime = PixelLinkRuntime(
        dry_run=True,
        enable_kill_switch=False,
        verbose=False,
        mcp_tools={},
    )
    runtime._use_conversational_mode = False
    try:
        enabled = runtime.handle_input("enable blind mode")
        assert enabled["status"] == "completed"
        assert runtime.blind_mode_enabled is True

        status = runtime.handle_input("read status")
        assert status["status"] == "completed"
        assert "Status:" in status["message"]

        repeated = runtime.handle_input("repeat last response")
        assert repeated["status"] == "completed"
        assert repeated["message"]

        help_result = runtime.handle_input("blind help")
        assert help_result["status"] == "completed"
        assert "read status" in help_result["message"].lower()
    finally:
        runtime.close()


def test_sensitive_confirmation_still_requires_confirm_cancel():
    runtime = PixelLinkRuntime(
        dry_run=True,
        enable_kill_switch=False,
        verbose=False,
        mcp_tools={},
    )
    runtime._use_conversational_mode = False
    runtime.set_preferences(blind_mode_enabled=True)
    try:
        pending = runtime.handle_input("reply email saying hello")
        assert pending["status"] == "awaiting_confirmation"
        assert "confirm" in pending["message"].lower()
        assert "cancel" in pending["message"].lower()

        completed = runtime.handle_input("confirm")
        assert completed["status"] == "completed"
    finally:
        runtime.close()
