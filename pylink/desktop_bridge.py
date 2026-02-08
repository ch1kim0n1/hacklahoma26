from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.runtime.orchestrator import DEFAULT_PERMISSION_PROFILE, PixelLinkRuntime

# Add parent directory to path to import bridge
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge import load_plugins


def _setup_logging() -> None:
    logs_dir = Path(__file__).resolve().parent / "logs"
    logs_dir.mkdir(exist_ok=True)
    log_file = logs_dir / f"pixelink-bridge-{datetime.now().strftime('%Y%m%d')}.log"
    logging.basicConfig(
        filename=str(log_file),
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


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
    trace_id: str | None = None,
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
    if trace_id is not None:
        payload["trace_id"] = trace_id
    if extra:
        payload.update(extra)
    return payload


def main() -> int:
    _setup_logging()

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
            if voice_controller.stt_available:
                voice_controller.prewarm_stt_async()
    except Exception as exc:
        voice_errors["voice"] = str(exc)
        voice_controller = None

    voice_input_enabled = bool(voice_controller and voice_controller.stt_available)
    voice_output_enabled = bool(voice_controller and voice_controller.tts_available)

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
            trace_id = request_id or f"trace-{uuid.uuid4().hex[:12]}"
            action = payload.get("action")

            if action == "process_input":
                text = str(payload.get("text", ""))
                source = str(payload.get("source", "text"))
                request_start = time.perf_counter()
                try:
                    result = runtime.handle_input(text, source=source, trace_id=trace_id)
                    _speak_response(result)
                    result["voice"] = _voice_state()
                    if request_id is not None:
                        result["request_id"] = request_id
                    _write_json(result)
                    logging.info(
                        json.dumps(
                            {
                                "event": "bridge.process_input",
                                "trace_id": trace_id,
                                "source": source,
                                "action": action,
                                "status": result.get("status"),
                                "elapsed_ms": round((time.perf_counter() - request_start) * 1000.0, 3),
                                "metrics": result.get("metrics", {}),
                            },
                            sort_keys=True,
                        )
                    )
                except Exception as exc:
                    _write_json(
                        _build_error(
                            message="Failed to process input.",
                            code="PROCESS_INPUT_FAILED",
                            request_id=request_id,
                            trace_id=trace_id,
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
                            trace_id=trace_id,
                            extra={**_runtime_state(runtime), "voice": _voice_state()},
                        )
                    )
                    continue

                prompt = str(payload.get("prompt", "")).strip()
                request_start = time.perf_counter()
                try:
                    if prompt and voice_output_enabled:
                        voice_controller.speak(prompt, blocking=False)
                    phase = {"state": "listening"}

                    def _status_callback(status: str) -> None:
                        if status == "listening":
                            phase["state"] = "listening"
                        elif status == "processing":
                            phase["state"] = "understanding"

                    transcript = voice_controller.listen(
                        allow_text_fallback=False,
                        status_callback=_status_callback,
                        immediate_feedback=lambda state: phase.update({"state": state.lower()}),
                    ).strip()
                except Exception as exc:
                    _write_json(
                        _build_error(
                            message="Voice input failed.",
                            code="VOICE_INPUT_FAILED",
                            request_id=request_id,
                            trace_id=trace_id,
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
                                trace_id=trace_id,
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
                            trace_id=trace_id,
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
                    result = runtime.handle_input(transcript, source="voice", trace_id=trace_id)
                    result["transcript"] = transcript
                    result["voice"] = _voice_state()
                    _speak_response(result)
                    result["voice_stage"] = "executing"
                    if request_id is not None:
                        result["request_id"] = request_id
                    _write_json(result)
                    logging.info(
                        json.dumps(
                            {
                                "event": "bridge.capture_voice_input",
                                "trace_id": trace_id,
                                "source": "voice",
                                "status": result.get("status"),
                                "elapsed_ms": round((time.perf_counter() - request_start) * 1000.0, 3),
                                "metrics": result.get("metrics", {}),
                            },
                            sort_keys=True,
                        )
                    )
                except Exception as exc:
                    _write_json(
                        _build_error(
                            message="Voice command processing failed.",
                            code="VOICE_COMMAND_FAILED",
                            request_id=request_id,
                            trace_id=trace_id,
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
                            trace_id=trace_id,
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
                    trace_id=trace_id,
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
