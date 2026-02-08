from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path
from typing import Any

import pyautogui

from core.runtime.orchestrator import DEFAULT_PERMISSION_PROFILE, PixelLinkRuntime

# Add parent directory to path to import bridge
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge import load_plugins

# Optional eye control (opencv + mediapipe)
try:
    from core.eye.eye_control import (
        BlinkType,
        is_eye_control_available,
        start_eye_loop as _eye_start,
        stop_eye_loop as _eye_stop,
    )
except Exception:
    _eye_start = None  # type: ignore[assignment]
    _eye_stop = None  # type: ignore[assignment]
    BlinkType = None  # type: ignore[assignment]
    is_eye_control_available = lambda: False  # type: ignore[assignment]


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
    sys.stdout.write(json.dumps(payload, default=str) + "\n")
    sys.stdout.flush()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _resolve_blink_action(blink_value: str, pending: bool) -> str | None:
    """Map blink events to high-level actions."""
    if pending:
        if blink_value == "single":
            return "confirm"
        if blink_value == "double":
            return "cancel"
        return None
    if blink_value == "double":
        return "left_click"
    return None


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

    # Eye control state (updated by eye loop callbacks)
    eye_control_state: dict[str, Any] = {
        "active": False,
        "available": is_eye_control_available() if callable(is_eye_control_available) else False,
        "last_gaze": None,
        "last_blink": None,
        "last_ear": None,
        "blink_state": "open",
        "gaze_norm": None,
        "iris_tracking": False,
        "control_mode": "face",
        "backend": None,
        "preview_active": False,
        "last_error": None,
    }

    def _eye_payload() -> dict[str, Any]:
        return {
            "active": eye_control_state.get("active", False),
            "available": eye_control_state.get("available", False),
            "last_gaze": eye_control_state.get("last_gaze"),
            "last_blink": eye_control_state.get("last_blink"),
            "last_ear": eye_control_state.get("last_ear"),
            "blink_state": eye_control_state.get("blink_state"),
            "gaze_norm": eye_control_state.get("gaze_norm"),
            "iris_tracking": eye_control_state.get("iris_tracking"),
            "control_mode": eye_control_state.get("control_mode"),
            "backend": eye_control_state.get("backend"),
            "preview_active": eye_control_state.get("preview_active"),
            "last_error": eye_control_state.get("last_error"),
        }

    def _get_screen_size() -> tuple[int, int]:
        try:
            w, h = pyautogui.size()
            return (int(w), int(h))
        except Exception:
            return (1920, 1080)

    def _on_gaze(x: int, y: int) -> None:
        eye_control_state["last_gaze"] = (x, y)
        try:
            runtime.move_cursor(x, y)
            eye_control_state["last_error"] = None
        except Exception as exc:
            eye_control_state["last_error"] = str(exc)

    def _on_metrics(metrics: dict[str, Any]) -> None:
        eye_control_state["last_ear"] = metrics.get("ear")
        eye_control_state["blink_state"] = metrics.get("blink_state", "open")
        eye_control_state["gaze_norm"] = metrics.get("gaze_norm")
        eye_control_state["iris_tracking"] = bool(metrics.get("iris_tracking", False))
        eye_control_state["control_mode"] = metrics.get("control_mode", "face")
        eye_control_state["backend"] = metrics.get("backend")
        eye_control_state["preview_active"] = bool(metrics.get("preview_active", False))
        if metrics.get("last_gaze") is not None:
            eye_control_state["last_gaze"] = metrics.get("last_gaze")
        if metrics.get("last_blink") is not None:
            eye_control_state["last_blink"] = metrics.get("last_blink")

    def _on_blink(blink_type: Any) -> None:
        bval = blink_type.value if hasattr(blink_type, "value") else str(blink_type)
        eye_control_state["last_blink"] = bval
        pending = bool(runtime.session.pending_steps or runtime.session.pending_clarification)
        action = _resolve_blink_action(bval, pending)
        if action == "confirm":
            runtime.handle_input("confirm", source="blink")
        elif action == "cancel":
            runtime.handle_input("cancel", source="blink")
        elif action == "left_click":
            try:
                cx, cy = pyautogui.position()
                runtime.executor.mouse.click(int(cx), int(cy), button="left")
            except Exception:
                pass

    def _eye_control_start() -> bool:
        if not _eye_start or not (eye_control_state.get("available")):
            return False
        if eye_control_state.get("active"):
            return True
        ok = _eye_start(
            _on_gaze,
            _on_blink,
            _get_screen_size,
            None,
            _on_metrics,
        )
        eye_control_state["active"] = ok
        return ok

    def _eye_control_stop() -> None:
        if _eye_stop:
            _eye_stop()
        eye_control_state["active"] = False
        eye_control_state["preview_active"] = False

    def _voice_state() -> dict[str, Any]:
        return {
            "requested_input": requested_voice_input,
            "requested_output": requested_voice_output,
            "input_enabled": voice_input_enabled,
            "output_enabled": voice_output_enabled,
            "errors": voice_errors,
        }

    def _speak_response(result: dict[str, Any]) -> None:
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
            ok = voice_controller.speak(text, blocking=False)
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
            "eye_control": _eye_payload(),
        }
    )

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
                        _build_error(
                            message="Voice input is unavailable.",
                            code="VOICE_INPUT_UNAVAILABLE",
                            request_id=request_id,
                            extra={**_runtime_state(runtime), "voice": _voice_state()},
                        )
                    )
                    continue

                prompt = str(payload.get("prompt", "")).strip()
                try:
                    if prompt and voice_output_enabled:
                        voice_controller.speak(prompt, blocking=False)
                    transcript = voice_controller.listen(
                        allow_text_fallback=False,
                        status_callback=lambda _status: None,
                    ).strip()
                except Exception as exc:
                    _write_json(
                        _build_error(
                            message="Voice input failed.",
                            code="VOICE_INPUT_FAILED",
                            request_id=request_id,
                            error=exc,
                            extra={**_runtime_state(runtime), "voice": _voice_state()},
                        )
                    )
                    continue

                if not transcript:
                    stt_error = voice_controller.last_stt_error if voice_controller else ""
                    if stt_error:
                        _write_json(
                            _build_error(
                                message="Voice input failed.",
                                code="VOICE_INPUT_FAILED",
                                request_id=request_id,
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
                        _build_error(
                            message="No speech detected. Please try again.",
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
                response = {
                    "status": "state",
                    **_runtime_state(runtime),
                    "voice": _voice_state(),
                    "eye_control": _eye_payload(),
                }
                if request_id is not None:
                    response["request_id"] = request_id
                _write_json(response)
                continue

            if action == "eye_control_start":
                if not eye_control_state.get("available"):
                    _write_json(
                        _build_error(
                            message="Eye control unavailable (camera or dependencies missing).",
                            code="EYE_CONTROL_UNAVAILABLE",
                            request_id=request_id,
                            extra={"eye_control": _eye_payload()},
                        )
                    )
                    continue
                ok = _eye_control_start()
                response = {
                    "status": "ok" if ok else "error",
                    "message": "Eye control started." if ok else "Failed to start eye control.",
                    "eye_control": _eye_payload(),
                }
                if request_id is not None:
                    response["request_id"] = request_id
                _write_json(response)
                continue

            if action == "eye_control_stop":
                _eye_control_stop()
                response = {
                    "status": "ok",
                    "message": "Eye control stopped.",
                    "eye_control": _eye_payload(),
                }
                if request_id is not None:
                    response["request_id"] = request_id
                _write_json(response)
                continue

            if action == "eye_control_get_state":
                response = {
                    "status": "state",
                    "eye_control": _eye_payload(),
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
        _eye_control_stop()
        runtime.close()
        if voice_controller:
            try:
                voice_controller.cleanup()
            except Exception:
                pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
