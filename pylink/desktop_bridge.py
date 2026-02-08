from __future__ import annotations

import json
import os
import signal
import sys
from pathlib import Path
from typing import Any

from core.runtime.orchestrator import DEFAULT_PERMISSION_PROFILE, PixelLinkRuntime

# Add parent directory to path to import bridge
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge import load_plugins


def _read_json_line() -> dict[str, Any] | None:
    line = sys.stdin.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return {}
    return json.loads(line)


def _write_json(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def main() -> int:
    dry_run = _as_bool(os.getenv("PIXELINK_DRY_RUN"), default=False)
    speed = float(os.getenv("PIXELINK_SPEED", "1.0"))
    enable_kill_switch = _as_bool(os.getenv("PIXELINK_ENABLE_KILL_SWITCH"), default=False)

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
        }
    )

    try:
        while running:
            try:
                payload = _read_json_line()
            except json.JSONDecodeError as error:
                _write_json({"status": "error", "message": f"Invalid JSON input: {error}"})
                continue

            if payload is None:
                break
            if not payload:
                continue

            action = payload.get("action")
            if action == "process_input":
                text = payload.get("text", "")
                source = payload.get("source", "text")
                result = runtime.handle_input(text, source=source)
                _write_json(result)
                continue

            if action == "update_preferences":
                runtime.set_preferences(
                    speed=payload.get("speed"),
                    permission_profile=payload.get("permission_profile"),
                )
                _write_json({"status": "updated", "message": "Preferences updated"})
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
                continue

            if action == "shutdown":
                _write_json({"status": "bye", "message": "Shutting down bridge"})
                break

            _write_json({"status": "error", "message": f"Unknown action: {action}"})
    finally:
        runtime.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
