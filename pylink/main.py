from __future__ import annotations

import argparse
import logging
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from core.input.text_input import read_text_input
from core.runtime.orchestrator import DEFAULT_PERMISSION_PROFILE, PixelLinkRuntime

# Add parent directory to path to import bridge
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
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
    parser = argparse.ArgumentParser(
        description="PixelLink - Intent-driven accessibility operating layer"
    )
    parser.add_argument(
        "--cli",
        "-c",
        action="store_true",
        help="Run CLI mode (default launches Electron UI)",
    )
    parser.add_argument(
        "--voice",
        action="store_true",
        help="Enable voice mode (speech input/output)",
    )
    parser.add_argument(
        "--voice-only",
        action="store_true",
        help="Use voice-only mode (no text fallback)",
    )
    parser.add_argument(
        "--tts-only",
        action="store_true",
        help="Enable text-to-speech output only (type input, voice output)",
    )
    return parser.parse_args()


def _output(message: str, voice_controller=None) -> None:
    print(message)
    if voice_controller:
        clean_message = message.replace("✓", "").replace("✗", "").replace("⚠", "").strip()
        if clean_message:
            voice_controller.speak(clean_message, blocking=True)


def _load_mcp_tools() -> dict[str, Any]:
    calendar_credentials = os.getenv("PIXELINK_CALENDAR_CREDENTIALS_PATH")
    calendar_token = os.getenv("PIXELINK_CALENDAR_TOKEN_PATH")
    gmail_credentials = os.getenv("PIXELINK_GMAIL_CREDENTIALS_PATH")
    gmail_token = os.getenv("PIXELINK_GMAIL_TOKEN_PATH")

    user_config: dict[str, dict[str, str]] = {
        "reminders-mcp": {},
        "notes-mcp": {},
    }
    if calendar_credentials:
        user_config["calendar-mcp"] = {
            "credentials_path": calendar_credentials,
            **({"token_path": calendar_token} if calendar_token else {}),
        }
    if gmail_credentials:
        user_config["gmail-mcp"] = {
            "credentials_path": gmail_credentials,
            **({"token_path": gmail_token} if gmail_token else {}),
        }

    try:
        mcp_tools = load_plugins(ROOT / "plugins", user_config)
        tool_map = {tool["name"]: tool["fn"] for tool in mcp_tools}
        print(f"Loaded {len(mcp_tools)} MCP tools: {', '.join(tool_map.keys())}")
        return tool_map
    except Exception as e:
        print(f"Warning: Could not load MCP plugins: {e}")
        return {}


def launch_electron_ui() -> None:
    """Launch the Electron UI."""
    electron_dir = ROOT / "electron"

    package_json = electron_dir / "package.json"
    node_modules = electron_dir / "node_modules"

    if not package_json.exists():
        print(f"Error: Electron UI not found at {electron_dir}")
        print("Please ensure the electron directory exists.")
        sys.exit(1)

    if not node_modules.exists():
        print("Installing Electron dependencies...")
        try:
            subprocess.run(
                ["npm", "install"],
                cwd=electron_dir,
                check=True,
                capture_output=True,
            )
            print("Dependencies installed")
        except subprocess.CalledProcessError as e:
            print(f"Failed to install dependencies: {e}")
            print("Please run 'npm install' in the electron directory manually.")
            sys.exit(1)
        except FileNotFoundError:
            print("npm not found. Please install Node.js and npm first.")
            print("Download from: https://nodejs.org/")
            sys.exit(1)

    print("Launching PixelLink Electron UI...")
    try:
        subprocess.run(
            ["npm", "start"],
            cwd=electron_dir,
            check=False,
        )
    except KeyboardInterrupt:
        print("\nElectron UI closed")
    except Exception as e:
        print(f"Error launching Electron UI: {e}")
        sys.exit(1)


def run_cli_mode(args: argparse.Namespace) -> None:
    """Run the CLI mode."""
    _setup_logging()

    voice_controller = None
    if args.voice or args.voice_only or args.tts_only:
        try:
            from core.voice import VoiceController

            voice_controller = VoiceController(
                enable_tts=True,
                enable_stt=not args.tts_only,
            )
            logging.info("Voice controller initialized")
        except Exception as e:
            print(f"Failed to initialize voice: {e}")
            if args.voice_only:
                print("Voice-only mode requested but voice init failed. Exiting.")
                return
            print("Falling back to text mode.")
            voice_controller = None

    system = platform.system()
    print(f"PixelLink MVP - Running on {system}")
    if system == "Darwin":
        print("macOS detected (recommended)")
        print("Note: Ensure accessibility permissions are enabled for Terminal/Python")
        print("(System Preferences -> Security & Privacy -> Accessibility)")
    elif system == "Windows":
        print("Windows support is experimental and not fully tested")
    elif system == "Linux":
        print("Linux support is experimental and not fully tested")
    else:
        print(f"WARNING: Unsupported OS '{system}'. Functionality may be limited.")

    tool_map = _load_mcp_tools()

    runtime = PixelLinkRuntime(
        dry_run=False,
        speed=1.0,
        permission_profile=DEFAULT_PERMISSION_PROFILE,
        enable_kill_switch=True,
        mcp_tools=tool_map,
    )

    mode_desc = "voice" if (args.voice or args.voice_only) else "text"
    if args.tts_only:
        mode_desc = "text input with voice output"

    print(f"\nPixelLink started in {mode_desc} mode. Say 'exit' to quit. Press ESC for kill switch.")
    print("Try: check my mood | show my schedule today | create reminder Buy milk")
    print("Type 'context' to see current context summary")

    if voice_controller:
        voice_controller.speak("PixelLink is ready. How can I help you?", blocking=True)

    try:
        while True:
            if voice_controller and not args.tts_only:
                from core.voice.voice_controller import read_voice_input

                input_data = read_voice_input(voice_controller)
            else:
                input_data = read_text_input()

            raw_text = str(input_data.get("raw_text", "")).strip()
            if not raw_text:
                continue

            lowered = raw_text.lower()
            if lowered in {"exit", "quit", "goodbye", "bye"}:
                _output("Goodbye!", voice_controller)
                break

            if lowered == "context":
                context_summary = runtime.session.get_context_summary()
                print("\n" + "=" * 60)
                print("Current Context:")
                print("=" * 60)
                print(context_summary)
                print("=" * 60 + "\n")
                continue

            result = runtime.handle_input(raw_text, source=input_data.get("source", "text"))

            if result.get("steps"):
                print("Planned steps:")
                for index, step in enumerate(result["steps"], start=1):
                    print(f"  {index}. {step['action']} - {step['description']}")

            message = str(result.get("message", "")).strip()
            if message:
                _output(message, voice_controller)

            suggestions = result.get("suggestions", [])
            if suggestions:
                print("Try:")
                for suggestion in suggestions:
                    print(f"  - {suggestion}")

            logging.info("Runtime result: %s", result)
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
