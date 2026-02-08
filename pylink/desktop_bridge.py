from __future__ import annotations

import json
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load environment variables from .env file next to this script
# (needed because Electron sets CWD to repo root, not pylink/)
_PYLINK_DIR = Path(__file__).resolve().parent
load_dotenv(_PYLINK_DIR / ".env")
load_dotenv()  # Also check CWD / parent dirs as fallback

from core.runtime.orchestrator import DEFAULT_PERMISSION_PROFILE, MaesRuntime

# Add parent directory to path to import bridge
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge import load_plugins


_WRITE_LOCK = threading.Lock()

# Strict pipeline state machine: idle -> listen -> processing -> action -> output -> idle
# During action and output states, no new input is accepted (no interruptions)
_PIPELINE_LOCK = threading.Lock()
_pipeline_state = "idle"  # "idle", "listen", "processing", "action", "output"


def _get_pipeline_state() -> str:
    with _PIPELINE_LOCK:
        return _pipeline_state


def _set_pipeline_state(new_state: str) -> None:
    global _pipeline_state
    with _PIPELINE_LOCK:
        _pipeline_state = new_state
    _write_json({"status": "pipeline_state", "state": new_state})


def _is_input_blocked() -> bool:
    """Check if input is blocked (during action or output phases)."""
    state = _get_pipeline_state()
    return state in ("action", "output")


def _read_json_line() -> dict[str, Any] | None:
    line = sys.stdin.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return {}
    payload = json.loads(line)
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object")
    return payload


def _write_json(payload: dict[str, Any]) -> None:
    with _WRITE_LOCK:
        sys.stdout.write(json.dumps(payload, default=str) + "\n")
        sys.stdout.flush()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _runtime_state(runtime: MaesRuntime) -> dict[str, Any]:
    return {
        "pending_confirmation": bool(runtime.session.pending_steps),
        "pending_clarification": bool(runtime.session.pending_clarification),
        "clarification_prompt": (runtime.session.pending_clarification or {}).get("prompt", ""),
        "last_app": runtime.session.last_app,
        "history_count": len(runtime.session.history),
        "last_response_message": runtime.session.last_response_message,
        "last_status_message": runtime.session.last_status_message,
    }


def _normalize_narration_level(value: Any) -> str:
    return "verbose" if str(value or "").lower() == "verbose" else "concise"


def _accessibility_state(
    *,
    blind_mode_enabled: bool,
    narration_level: str,
    screen_reader_hints_enabled: bool,
    last_announcement: str,
) -> dict[str, Any]:
    return {
        "blind_mode_enabled": bool(blind_mode_enabled),
        "narration_level": _normalize_narration_level(narration_level),
        "screen_reader_hints_enabled": bool(screen_reader_hints_enabled),
        "last_announcement": last_announcement or "",
    }


def _announcement_payload(message: str, priority: str = "polite") -> dict[str, Any]:
    return {
        "status": "announcement",
        "priority": "assertive" if str(priority).lower() == "assertive" else "polite",
        "message": message,
    }


def _blind_mode_guidance(voice_output_enabled: bool, voice_input_enabled: bool) -> str:
    issues: list[str] = []
    if not voice_output_enabled:
        issues.append("text-to-speech is unavailable")
    if not voice_input_enabled:
        issues.append("speech-to-text is unavailable")
    if not issues:
        return ""
    return (
        "Blind mode is enabled, but "
        + " and ".join(issues)
        + ". Check your API keys, microphone permission, and voice dependencies."
    )


def _build_error(
    *,
    message: str,
    code: str,
    request_id: str | None = None,
    error: Exception | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "error",
        "message": message,
        "error": {
            "code": code,
            "type": type(error).__name__ if error else None,
            "details": str(error) if error else None,
        },
    }
    if request_id is not None:
        payload["request_id"] = request_id
    if extra:
        payload.update(extra)
    return payload


def _voice_error_guidance(code: str, details: str = "") -> tuple[str, list[str]]:
    detail = details.lower()
    if code == "VOICE_INPUT_UNAVAILABLE":
        return (
            "Voice input is currently unavailable.",
            [
                "Enable voice input in settings, then try again.",
                "If microphone permission changed recently, restart Maes.",
            ],
        )
    if code == "VOICE_INPUT_EMPTY":
        return (
            "No speech was detected.",
            [
                "Speak after pressing the Voice button.",
                "Move closer to the microphone or reduce background noise.",
            ],
        )
    if "permission" in detail or "not permitted" in detail or "not authorized" in detail:
        return (
            "Microphone permission is blocked.",
            [
                "Allow microphone access for Terminal/Electron in system privacy settings.",
                "Restart Maes after granting permission.",
            ],
        )
    if "pyaudio" in detail or "portaudio" in detail:
        return (
            "Microphone audio backend is unavailable.",
            [
                "Install or repair PyAudio/PortAudio dependencies.",
                "Restart Maes after installation.",
            ],
        )
    if "network" in detail or "connection" in detail:
        return (
            "Voice model download failed due to a network issue.",
            [
                "Check your internet connection and try again.",
                "Keep Maes open until model preparation completes.",
            ],
        )
    if "whisper" in detail or "model" in detail:
        return (
            "Speech model initialization failed.",
            [
                "Retry in a moment; first-run model setup can take time.",
                "If this persists, clear the Whisper cache and restart.",
            ],
        )
    if code == "VOICE_INPUT_FAILED":
        return (
            "Voice input failed before transcription completed.",
            [
                "Try again and speak clearly after the listening indicator appears.",
                "Check microphone device and permissions.",
            ],
        )
    return (
        "Voice command failed.",
        [
            "Try again in a quieter environment.",
            "If the issue continues, restart Maes.",
        ],
    )


def _build_voice_error(
    *,
    code: str,
    details: str = "",
    message: str | None = None,
    request_id: str | None = None,
    error: Exception | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    user_message, hints = _voice_error_guidance(code, details or (str(error) if error else ""))
    payload_extra = {
        "user_message": user_message,
        "hints": hints,
    }
    if extra:
        payload_extra.update(extra)
    payload = _build_error(
        message=message or user_message,
        code=code,
        request_id=request_id,
        error=error,
        extra=payload_extra,
    )
    if not isinstance(payload.get("error"), dict):
        payload["error"] = {
            "code": code,
            "type": type(error).__name__ if error else None,
            "details": details or (str(error) if error else None),
        }
    if details:
        payload["error"]["details"] = details
    payload["error"]["user_message"] = user_message
    payload["error"]["hints"] = hints
    return payload


def main() -> int:
    dry_run = _as_bool(os.getenv("MAES_DRY_RUN"), default=False)
    speed = float(os.getenv("MAES_SPEED", "1.0"))
    enable_kill_switch = _as_bool(os.getenv("MAES_ENABLE_KILL_SWITCH"), default=False)
    requested_voice_output = _as_bool(os.getenv("MAES_VOICE_OUTPUT"), default=True)
    requested_voice_input = _as_bool(os.getenv("MAES_VOICE_INPUT"), default=True)
    blind_mode_enabled = _as_bool(os.getenv("MAES_BLIND_MODE"), default=False)
    narration_level = _normalize_narration_level(os.getenv("MAES_NARRATION_LEVEL", "concise"))
    screen_reader_hints_enabled = _as_bool(os.getenv("MAES_SCREEN_READER_HINTS"), default=True)
    last_announcement = ""

    calendar_credentials = os.getenv("MAES_CALENDAR_CREDENTIALS_PATH")
    calendar_token = os.getenv("MAES_CALENDAR_TOKEN_PATH")
    gmail_credentials = os.getenv("MAES_GMAIL_CREDENTIALS_PATH")
    gmail_token = os.getenv("MAES_GMAIL_TOKEN_PATH")

    # Load MCP plugins
    user_config: dict[str, dict[str, Any]] = {
        "reminders-mcp": {},
        "notes-mcp": {},
        "calendar-mcp": {
            **({"credentials_path": calendar_credentials} if calendar_credentials else {}),
            **({"token_path": calendar_token} if calendar_token else {}),
        },
        "gmail-mcp": {
            **({"credentials_path": gmail_credentials} if gmail_credentials else {}),
            **({"token_path": gmail_token} if gmail_token else {}),
        },
    }
    try:
        mcp_tools = load_plugins(ROOT / "plugins", user_config)
        tool_map = {tool["name"]: tool["fn"] for tool in mcp_tools}
    except Exception as e:
        _write_json({"status": "warning", "message": f"Could not load MCP plugins: {e}"})
        tool_map = {}

    runtime = MaesRuntime(
        dry_run=dry_run,
        speed=speed,
        permission_profile=DEFAULT_PERMISSION_PROFILE,
        enable_kill_switch=enable_kill_switch,
        verbose=False,
        mcp_tools=tool_map,
    )
    runtime.set_preferences(
        blind_mode_enabled=blind_mode_enabled,
        narration_level=narration_level,
        screen_reader_hints_enabled=screen_reader_hints_enabled,
    )

    voice_controller = None
    voice_errors: dict[str, str] = {}

    try:
        from core.voice import VoiceController

        if requested_voice_input or requested_voice_output:
            voice_controller = VoiceController(
                enable_tts=requested_voice_output,
                enable_stt=requested_voice_input,
            )
            voice_errors = voice_controller.init_errors
    except Exception as exc:
        voice_errors["voice"] = str(exc)
        voice_controller = None

    voice_input_enabled = bool(voice_controller and voice_controller.stt_available)
    voice_output_enabled = bool(voice_controller and voice_controller.tts_available)
    voice_model_lock = threading.Lock()
    voice_model_state: dict[str, Any] = (
        voice_controller.stt_model_status if voice_controller and voice_input_enabled else {
            "model": "",
            "state": "unavailable",
            "stage": "unavailable",
            "message": "Voice input is unavailable.",
            "progress": 0,
            "cached": None,
            "error": "",
        }
    )

    def _get_voice_model_state() -> dict[str, Any]:
        with voice_model_lock:
            return dict(voice_model_state)

    def _update_voice_model_state(update: dict[str, Any]) -> dict[str, Any]:
        with voice_model_lock:
            voice_model_state.update(update)
            return dict(voice_model_state)

    def _emit_voice_model_status(update: dict[str, Any]) -> None:
        _update_voice_model_state(update)
        _write_json(
            {
                "status": "voice_model_status",
                "voice_model": _get_voice_model_state(),
            }
        )

    def _voice_state() -> dict[str, Any]:
        return {
            "requested_input": requested_voice_input,
            "requested_output": requested_voice_output,
            "input_enabled": voice_input_enabled,
            "output_enabled": voice_output_enabled,
            "errors": voice_errors,
            "model": _get_voice_model_state(),
        }

    def _current_accessibility_state() -> dict[str, Any]:
        return _accessibility_state(
            blind_mode_enabled=blind_mode_enabled,
            narration_level=narration_level,
            screen_reader_hints_enabled=screen_reader_hints_enabled,
            last_announcement=last_announcement,
        )

    def _emit_announcement(message: str, priority: str = "polite") -> None:
        nonlocal last_announcement
        clean_message = str(message or "").strip()
        if not clean_message:
            return
        last_announcement = clean_message
        payload = _announcement_payload(clean_message, priority)
        payload["accessibility"] = _current_accessibility_state()
        _write_json(payload)

    def _apply_blind_mode_voice_requirements() -> None:
        nonlocal requested_voice_output, requested_voice_input, voice_output_enabled, voice_input_enabled
        requested_voice_output = True
        requested_voice_input = True
        voice_output_enabled = bool(voice_controller and voice_controller.tts_available)
        voice_input_enabled = bool(voice_controller and voice_controller.stt_available)
        if voice_controller and voice_input_enabled:
            voice_controller.warm_stt_async(status_callback=_emit_voice_model_status)

    def _blind_mode_availability_guidance() -> str:
        return _blind_mode_guidance(voice_output_enabled, voice_input_enabled)

    # Register pre-task announcement callback so voice speaks BEFORE execution
    def _pre_task_announce(msg: str) -> None:
        """Speak pre-task announcement and emit status to Electron."""
        _emit_announcement(msg, priority="polite")
        if voice_controller and voice_output_enabled:
            try:
                voice_controller.speak(msg, blocking=True)
            except Exception:
                pass

    runtime.set_pre_task_callback(_pre_task_announce)

    if blind_mode_enabled:
        _apply_blind_mode_voice_requirements()
        guidance = _blind_mode_availability_guidance()
        if guidance:
            _emit_announcement(guidance, priority="assertive")

    def _speak_pre_task(result: dict[str, Any]) -> None:
        """Speak the pre-task announcement before executing.
        Skips if pre-task was already announced via callback.
        """
        if not voice_controller or not voice_output_enabled:
            return

        # Skip if the pre-task callback already spoke this
        if result.get("pre_task_announced"):
            return

        pre_msg = str(result.get("pre_task_message", "")).strip()
        if not pre_msg:
            return

        try:
            voice_controller.speak(pre_msg, blocking=True)
        except Exception:
            pass

    def _speak_response(result: dict[str, Any]) -> None:
        """Speak the response text. Uses blocking=True for sequential state management."""
        if not voice_controller or not voice_output_enabled:
            return

        text = ""
        if result.get("pending_clarification") and result.get("clarification_prompt"):
            text = str(result.get("clarification_prompt", "")).strip()
        else:
            text = str(result.get("message", "")).strip()

        if not text:
            return

        try:
            # Use blocking=True to ensure sequential operation (speaking finishes before listening can start)
            ok = voice_controller.speak(text, blocking=True)
            if not ok:
                result.setdefault("warnings", []).append("VOICE_OUTPUT_FAILED")
        except Exception as exc:
            result.setdefault("warnings", []).append("VOICE_OUTPUT_FAILED")
            result.setdefault("warning_details", []).append(str(exc))

    def _apply_accessibility_side_effects(result: dict[str, Any]) -> None:
        nonlocal blind_mode_enabled, narration_level, screen_reader_hints_enabled
        intent_payload = result.get("intent") if isinstance(result.get("intent"), dict) else {}
        if intent_payload.get("name") == "set_blind_mode":
            entities = intent_payload.get("entities") if isinstance(intent_payload.get("entities"), dict) else {}
            enabled = bool(entities.get("enabled"))
            blind_mode_enabled = enabled
            runtime.set_preferences(blind_mode_enabled=enabled)
            if enabled:
                _apply_blind_mode_voice_requirements()
                _emit_announcement("Blind mode enabled. Voice guidance is active.", priority="assertive")
                guidance = _blind_mode_availability_guidance()
                if guidance:
                    result.setdefault("warnings", []).append("BLIND_MODE_VOICE_UNAVAILABLE")
                    result.setdefault("warning_details", []).append(guidance)
                    _emit_announcement(guidance, priority="assertive")
            else:
                _emit_announcement("Blind mode disabled.", priority="polite")

        if isinstance(result.get("accessibility"), dict):
            runtime_acc = result["accessibility"]
            blind_mode_enabled = bool(runtime_acc.get("blind_mode_enabled", blind_mode_enabled))
            narration_level = _normalize_narration_level(runtime_acc.get("narration_level", narration_level))
            screen_reader_hints_enabled = bool(
                runtime_acc.get("screen_reader_hints_enabled", screen_reader_hints_enabled)
            )

    running = True

    def shutdown_handler(*_) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    _write_json(
        {
            "status": "ready",
            "message": "Maes bridge online",
            "dry_run": dry_run,
            "speed": speed,
            "voice": _voice_state(),
            "accessibility": _current_accessibility_state(),
        }
    )

    if voice_controller and voice_input_enabled:
        voice_controller.warm_stt_async(status_callback=_emit_voice_model_status)

    try:
        while running:
            try:
                payload = _read_json_line()
            except json.JSONDecodeError as error:
                _write_json(
                    _build_error(
                        message="Invalid JSON input.",
                        code="INVALID_JSON",
                        error=error,
                    )
                )
                continue
            except ValueError as error:
                _write_json(
                    _build_error(
                        message="Invalid request payload.",
                        code="INVALID_PAYLOAD",
                        error=error,
                    )
                )
                continue

            if payload is None:
                break
            if not payload:
                continue

            request_id = str(payload.get("request_id", "")).strip() or None
            action = payload.get("action")

            if action == "process_input":
                # Block input during action/output states (no interruptions)
                if _is_input_blocked():
                    _write_json(
                        _build_error(
                            message="System is busy. Please wait until the current task finishes.",
                            code="INPUT_BLOCKED",
                            request_id=request_id,
                            extra={
                                **_runtime_state(runtime),
                                "voice": _voice_state(),
                                "pipeline_state": _get_pipeline_state(),
                                "accessibility": _current_accessibility_state(),
                            },
                        )
                    )
                    continue

                text = str(payload.get("text", ""))
                source = str(payload.get("source", "text"))
                try:
                    _set_pipeline_state("processing")
                    result = runtime.handle_input(text, source=source)

                    # Speak pre-task announcement before action
                    _speak_pre_task(result)

                    # Action phase
                    _set_pipeline_state("action")

                    # Output phase - speak the response
                    _set_pipeline_state("output")
                    _speak_response(result)
                    _apply_accessibility_side_effects(result)

                    result["voice"] = _voice_state()
                    result["accessibility"] = _current_accessibility_state()
                    result["pipeline_state"] = "idle"
                    if request_id is not None:
                        result["request_id"] = request_id
                    _write_json(result)
                except Exception as exc:
                    _write_json(
                        _build_error(
                            message="Failed to process input.",
                            code="PROCESS_INPUT_FAILED",
                            request_id=request_id,
                            error=exc,
                            extra={
                                **_runtime_state(runtime),
                                "voice": _voice_state(),
                                "accessibility": _current_accessibility_state(),
                            },
                        )
                    )
                finally:
                    _set_pipeline_state("idle")
                continue

            if action == "capture_voice_input":
                # Block input during action/output states (no interruptions)
                if _is_input_blocked():
                    _write_json(
                        _build_error(
                            message="System is busy. Please wait until the current task finishes.",
                            code="INPUT_BLOCKED",
                            request_id=request_id,
                            extra={
                                **_runtime_state(runtime),
                                "voice": _voice_state(),
                                "pipeline_state": _get_pipeline_state(),
                                "accessibility": _current_accessibility_state(),
                            },
                        )
                    )
                    continue

                if not voice_controller or not voice_input_enabled:
                    _write_json(
                        _build_voice_error(
                            code="VOICE_INPUT_UNAVAILABLE",
                            request_id=request_id,
                            extra={
                                **_runtime_state(runtime),
                                "voice": _voice_state(),
                                "accessibility": _current_accessibility_state(),
                            },
                        )
                    )
                    continue

                # LISTEN phase
                _set_pipeline_state("listen")
                prompt = str(payload.get("prompt", "")).strip()
                try:
                    if prompt and voice_output_enabled:
                        voice_controller.speak(prompt, blocking=True)
                    transcript = voice_controller.listen(
                        allow_text_fallback=False,
                        status_callback=lambda _status: None,
                    ).strip()
                except Exception as exc:
                    _set_pipeline_state("idle")
                    _write_json(
                        _build_voice_error(
                            code="VOICE_INPUT_FAILED",
                            request_id=request_id,
                            error=exc,
                            details=str(exc),
                            extra={
                                **_runtime_state(runtime),
                                "voice": _voice_state(),
                                "accessibility": _current_accessibility_state(),
                            },
                        )
                    )
                    continue

                if not transcript:
                    _set_pipeline_state("idle")
                    stt_error = voice_controller.last_stt_error if voice_controller else ""
                    if stt_error:
                        _write_json(
                            _build_voice_error(
                                code="VOICE_INPUT_FAILED",
                                request_id=request_id,
                                details=stt_error,
                                extra={
                                    **_runtime_state(runtime),
                                    "voice": _voice_state(),
                                    "source": "voice",
                                    "transcript": "",
                                    "accessibility": _current_accessibility_state(),
                                    "error": {
                                        "code": "VOICE_INPUT_FAILED",
                                        "type": "SpeechToTextError",
                                        "details": stt_error,
                                    },
                                },
                            )
                        )
                        continue
                    _write_json(
                        _build_voice_error(
                            code="VOICE_INPUT_EMPTY",
                            request_id=request_id,
                            extra={
                                **_runtime_state(runtime),
                                "voice": _voice_state(),
                                "source": "voice",
                                "transcript": "",
                                "accessibility": _current_accessibility_state(),
                            },
                        )
                    )
                    continue

                try:
                    # PROCESSING phase
                    _set_pipeline_state("processing")
                    result = runtime.handle_input(transcript, source="voice")

                    # Speak pre-task announcement before action
                    _speak_pre_task(result)

                    # ACTION phase
                    _set_pipeline_state("action")

                    # OUTPUT phase - speak result
                    _set_pipeline_state("output")
                    result["transcript"] = transcript
                    _speak_response(result)
                    _apply_accessibility_side_effects(result)
                    result["voice"] = _voice_state()
                    result["accessibility"] = _current_accessibility_state()
                    result["pipeline_state"] = "idle"
                    if request_id is not None:
                        result["request_id"] = request_id
                    _write_json(result)
                except Exception as exc:
                    _write_json(
                        _build_error(
                            message="Voice command processing failed.",
                            code="VOICE_COMMAND_FAILED",
                            request_id=request_id,
                            error=exc,
                            extra={
                                **_runtime_state(runtime),
                                "voice": _voice_state(),
                                "source": "voice",
                                "transcript": transcript,
                                "accessibility": _current_accessibility_state(),
                            },
                        )
                    )
                finally:
                    _set_pipeline_state("idle")
                continue

            if action == "update_preferences":
                try:
                    if "blind_mode_enabled" in payload:
                        blind_mode_enabled = bool(payload.get("blind_mode_enabled"))
                    if "narration_level" in payload:
                        narration_level = _normalize_narration_level(payload.get("narration_level"))
                    if "screen_reader_hints_enabled" in payload:
                        screen_reader_hints_enabled = bool(payload.get("screen_reader_hints_enabled"))

                    runtime.set_preferences(
                        speed=payload.get("speed"),
                        permission_profile=payload.get("permission_profile"),
                        blind_mode_enabled=blind_mode_enabled,
                        narration_level=narration_level,
                        screen_reader_hints_enabled=screen_reader_hints_enabled,
                    )

                    if "blind_mode_enabled" in payload:
                        if blind_mode_enabled:
                            _emit_announcement("Blind mode enabled. Voice guidance is active.", priority="assertive")
                        else:
                            _emit_announcement("Blind mode disabled.", priority="polite")

                    if blind_mode_enabled:
                        _apply_blind_mode_voice_requirements()
                        guidance = _blind_mode_availability_guidance()
                        if guidance:
                            _emit_announcement(guidance, priority="assertive")
                    elif "voice_output_enabled" in payload:
                        requested = bool(payload.get("voice_output_enabled"))
                        requested_voice_output = requested
                        voice_output_enabled = requested and bool(
                            voice_controller and voice_controller.tts_available
                        )

                    if blind_mode_enabled:
                        # In blind mode we always request input/output voice path.
                        requested_voice_input = True
                        requested_voice_output = True
                    elif "voice_input_enabled" in payload:
                        requested = bool(payload.get("voice_input_enabled"))
                        requested_voice_input = requested
                        voice_input_enabled = requested and bool(
                            voice_controller and voice_controller.stt_available
                        )
                        if voice_controller and voice_input_enabled:
                            voice_controller.warm_stt_async(status_callback=_emit_voice_model_status)
                    response = {
                        "status": "updated",
                        "message": "Preferences updated",
                        "voice": _voice_state(),
                        "accessibility": _current_accessibility_state(),
                    }
                    if request_id is not None:
                        response["request_id"] = request_id
                    _write_json(response)
                except Exception as exc:
                    _write_json(
                        _build_error(
                            message="Failed to update preferences.",
                            code="UPDATE_PREFERENCES_FAILED",
                            request_id=request_id,
                            error=exc,
                            extra={"voice": _voice_state(), "accessibility": _current_accessibility_state()},
                        )
                    )
                continue

            if action == "get_state":
                response = {
                    "status": "state",
                    **_runtime_state(runtime),
                    "voice": _voice_state(),
                    "accessibility": _current_accessibility_state(),
                }
                if request_id is not None:
                    response["request_id"] = request_id
                _write_json(response)
                continue

            if action == "shutdown":
                response = {"status": "bye", "message": "Shutting down bridge"}
                if request_id is not None:
                    response["request_id"] = request_id
                _write_json(response)
                break

            _write_json(
                _build_error(
                    message=f"Unknown action: {action}",
                    code="UNKNOWN_ACTION",
                    request_id=request_id,
                    extra={"accessibility": _current_accessibility_state(), "voice": _voice_state()},
                )
            )
    finally:
        runtime.close()
        if voice_controller:
            try:
                voice_controller.cleanup()
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
