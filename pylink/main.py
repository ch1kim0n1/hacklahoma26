from __future__ import annotations

import argparse
import logging
import os
import platform
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.input.text_input import read_text_input
from core.runtime.orchestrator import DEFAULT_PERMISSION_PROFILE, PixelLinkRuntime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from bridge import load_plugins


def _setup_logging() -> None:
    os.makedirs("logs", exist_ok=True)
    log_file = os.path.join("logs", f"pixelink-{datetime.now().strftime('%Y%m%d')}.log")
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PixelLink")
    parser.add_argument("--cli", "-c", action="store_true", help="Run CLI mode")
    parser.add_argument("--voice", action="store_true", help="Enable voice input/output in CLI mode")
    parser.add_argument("--voice-only", action="store_true", help="Voice input only (no typed input fallback)")
    parser.add_argument("--tts-only", action="store_true", help="Typed input with voice output")
    parser.add_argument("--dry-run", action="store_true", help="Execute without OS automation")
    return parser.parse_args()


def _build_tool_map() -> dict[str, Any]:
    calendar_credentials = os.getenv("PIXELINK_CALENDAR_CREDENTIALS_PATH")
    calendar_token = os.getenv("PIXELINK_CALENDAR_TOKEN_PATH")
    gmail_credentials = os.getenv("PIXELINK_GMAIL_CREDENTIALS_PATH")
    gmail_token = os.getenv("PIXELINK_GMAIL_TOKEN_PATH")

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
        return {tool["name"]: tool["fn"] for tool in mcp_tools}
    except Exception as exc:
        print(f"⚠ Warning: Could not load MCP plugins: {exc}")
        return {}


def launch_electron_ui() -> None:
    electron_dir = ROOT / "electron"
    package_json = electron_dir / "package.json"
    node_modules = electron_dir / "node_modules"

    if not package_json.exists():
        print(f"❌ Error: Electron UI not found at {electron_dir}")
        raise SystemExit(1)

    if not node_modules.exists():
        print("Installing Electron dependencies...")
        try:
            subprocess.run(["npm", "install"], cwd=electron_dir, check=True)
        except Exception as exc:
            print(f"❌ Failed to install dependencies: {exc}")
            raise SystemExit(1)

    print("Launching PixelLink Electron UI...")
    try:
        subprocess.run(["npm", "start"], cwd=electron_dir, check=False)
    except KeyboardInterrupt:
        print("Electron UI closed")


def run_cli_mode(args: argparse.Namespace) -> None:
    _setup_logging()

    system = platform.system()
    print(f"PixelLink - Running on {system}")
    if system == "Darwin":
        print("macOS detected")
    elif system in {"Windows", "Linux"}:
        print(f"{system} support is experimental")

    tool_map = _build_tool_map()
    if tool_map:
        print(f"Loaded {len(tool_map)} MCP tools: {', '.join(tool_map.keys())}")

    runtime = PixelLinkRuntime(
        dry_run=args.dry_run,
        speed=1.0,
        permission_profile=DEFAULT_PERMISSION_PROFILE,
        enable_kill_switch=True,
        verbose=True,
        mcp_tools=tool_map,
    )

    voice_controller = None
    if args.voice or args.voice_only or args.tts_only:
        try:
            from core.voice import VoiceController

            voice_controller = VoiceController(
                enable_tts=True,
                enable_stt=not args.tts_only,
            )
            if voice_controller.stt_available:
                voice_controller.prewarm_stt_async()
        except Exception as exc:
            print(f"Voice initialization failed: {exc}")
            if args.voice_only:
                runtime.close()
                return

    mode_desc = "voice" if (args.voice or args.voice_only) else "text"
    if args.tts_only:
        mode_desc = "text input with voice output"
    print(f"\nPixelLink started in {mode_desc} mode. Type/say 'exit' to quit.")

    try:
        while True:
            if voice_controller and not args.tts_only:
                from core.voice.voice_controller import read_voice_input

                input_data = read_voice_input(voice_controller)
            else:
                input_data = read_text_input()

            raw_text = input_data.get("raw_text", "").strip()
            if not raw_text:
                continue
            if raw_text.lower() in {"exit", "quit", "goodbye", "bye"}:
                print("Goodbye!")
                break

            trace_id = f"cli-{uuid.uuid4().hex[:12]}"
            result = runtime.handle_input(
                raw_text,
                source=input_data.get("source", "text"),
                trace_id=trace_id,
            )

            if result.get("steps"):
                print("Planned steps:")
                for index, step in enumerate(result["steps"], start=1):
                    print(f"  {index}. {step['action']} - {step['description']}")

            print(result.get("message", ""))

            metrics = result.get("metrics", {})
            if metrics:
                print(
                    "Timing: "
                    f"parse={metrics.get('parse_ms', 0)}ms "
                    f"plan={metrics.get('plan_ms', 0)}ms "
                    f"execute={metrics.get('execute_ms', 0)}ms "
                    f"total={metrics.get('total_ms', 0)}ms "
                    f"mode={metrics.get('nlu_mode', 'rules')}"
                )

            suggestions = result.get("suggestions", [])
            if suggestions:
                print("Try:")
                for suggestion in suggestions:
                    print(f"  - {suggestion}")

            if voice_controller and result.get("message"):
                voice_controller.speak(str(result["message"]), blocking=False)

    finally:
        runtime.close()
        if voice_controller:
            voice_controller.cleanup()


def main() -> None:
    args = _parse_args()
    if args.cli:
        run_cli_mode(args)
    else:
        launch_electron_ui()


if __name__ == "__main__":
    main()
