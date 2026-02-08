from __future__ import annotations

import json
import os
import signal
import sys
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load environment variables from .env file (checks current and parent directories)
load_dotenv()

from core.runtime.orchestrator import DEFAULT_PERMISSION_PROFILE, PixelLinkRuntime

# Add parent directory to path to import bridge
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge import load_plugins


_WRITE_LOCK = threading.Lock()


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


def _runtime_state(runtime: PixelLinkRuntime) -> dict[str, Any]:
    return {
        "pending_confirmation": bool(runtime.session.pending_steps),
        "pending_clarification": bool(runtime.session.pending_clarification),
        "clarification_prompt": (runtime.session.pending_clarification or {}).get("prompt", ""),
        "last_app": runtime.session.last_app,
        "history_count": len(runtime.session.history),
    }


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
                "If microphone permission changed recently, restart PixelLink.",
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
                "Restart PixelLink after granting permission.",
            ],
        )
    if "pyaudio" in detail or "portaudio" in detail:
        return (
            "Microphone audio backend is unavailable.",
            [
                "Install or repair PyAudio/PortAudio dependencies.",
                "Restart PixelLink after installation.",
            ],
        )
    if "network" in detail or "connection" in detail:
        return (
            "Voice model download failed due to a network issue.",
            [
                "Check your internet connection and try again.",
                "Keep PixelLink open until model preparation completes.",
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
            "If the issue continues, restart PixelLink.",
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
    dry_run = _as_bool(os.getenv("PIXELINK_DRY_RUN"), default=False)
    speed = float(os.getenv("PIXELINK_SPEED", "1.0"))
    enable_kill_switch = _as_bool(os.getenv("PIXELINK_ENABLE_KILL_SWITCH"), default=False)
    requested_voice_output = _as_bool(os.getenv("PIXELINK_VOICE_OUTPUT"), default=True)
    requested_voice_input = _as_bool(os.getenv("PIXELINK_VOICE_INPUT"), default=True)

    calendar_credentials = os.getenv("PIXELINK_CALENDAR_CREDENTIALS_PATH")
    calendar_token = os.getenv("PIXELINK_CALENDAR_TOKEN_PATH")
    gmail_credentials = os.getenv("PIXELINK_GMAIL_CREDENTIALS_PATH")
    gmail_token = os.getenv("PIXELINK_GMAIL_TOKEN_PATH")

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

    runtime = PixelLinkRuntime(
        dry_run=dry_run,
        speed=speed,
        permission_profile=DEFAULT_PERMISSION_PROFILE,
        enable_kill_switch=enable_kill_switch,
        verbose=False,
        mcp_tools=tool_map,
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

    running = True

    def shutdown_handler(*_) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    _write_json(
        {
            "status": "ready",
            "message": "PixelLink bridge online",
            "dry_run": dry_run,
            "speed": speed,
            "voice": _voice_state(),
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
                text = str(payload.get("text", ""))
                source = str(payload.get("source", "text"))
                try:
                    result = runtime.handle_input(text, source=source)
                    _speak_response(result)
                    result["voice"] = _voice_state()
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
                            extra={**_runtime_state(runtime), "voice": _voice_state()},
                        )
                    )
                continue

            if action == "capture_voice_input":
                if not voice_controller or not voice_input_enabled:
                    _write_json(
                        _build_voice_error(
                            code="VOICE_INPUT_UNAVAILABLE",
                            request_id=request_id,
                            extra={**_runtime_state(runtime), "voice": _voice_state()},
                        )
                    )
                    continue

                prompt = str(payload.get("prompt", "")).strip()
                try:
                    if prompt and voice_output_enabled:
                        # Use blocking=True to ensure speaking completes before listening
                        voice_controller.speak(prompt, blocking=True)
                    transcript = voice_controller.listen(
                        allow_text_fallback=False,
                        status_callback=lambda _status: None,
                    ).strip()
                except Exception as exc:
                    _write_json(
                        _build_voice_error(
                            code="VOICE_INPUT_FAILED",
                            request_id=request_id,
                            error=exc,
                            details=str(exc),
                            extra={**_runtime_state(runtime), "voice": _voice_state()},
                        )
                    )
                    continue

                if not transcript:
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
                            },
                        )
                    )
                    continue

                try:
                    result = runtime.handle_input(transcript, source="voice")
                    result["transcript"] = transcript
                    result["voice"] = _voice_state()
                    _speak_response(result)
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
                            },
                        )
                    )
                continue

            if action == "update_preferences":
                try:
                    runtime.set_preferences(
                        speed=payload.get("speed"),
                        permission_profile=payload.get("permission_profile"),
                    )
                    if "voice_output_enabled" in payload:
                        requested = bool(payload.get("voice_output_enabled"))
                        voice_output_enabled = requested and bool(
                            voice_controller and voice_controller.tts_available
                        )
                    if "voice_input_enabled" in payload:
                        requested = bool(payload.get("voice_input_enabled"))
                        voice_input_enabled = requested and bool(
                            voice_controller and voice_controller.stt_available
                        )
                        if voice_controller and voice_input_enabled:
                            voice_controller.warm_stt_async(status_callback=_emit_voice_model_status)
                    response = {
                        "status": "updated",
                        "message": "Preferences updated",
                        "voice": _voice_state(),
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
                            extra={"voice": _voice_state()},
                        )
                    )
                continue

            if action == "get_state":
                _write_json(
                    {
                        "status": "state",
                        "pending_confirmation": bool(runtime.session.pending_steps),
                        "pending_clarification": bool(runtime.session.pending_clarification),
                        "clarification_prompt": (runtime.session.pending_clarification or {}).get("prompt", ""),
                        "last_app": runtime.session.last_app,
                        "history_count": len(runtime.session.history),
                        "affection": runtime.session.last_affection,
                    }
                )
                response = {
                    "status": "state",
                    **_runtime_state(runtime),
                    "voice": _voice_state(),
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
