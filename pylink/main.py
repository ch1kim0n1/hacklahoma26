from __future__ import annotations

import argparse
import logging
import os
import platform
import subprocess
import sys
from datetime import datetime
from typing import Optional
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file (checks current and parent directories)
load_dotenv()

from core.input.text_input import read_text_input
from core.runtime.orchestrator import DEFAULT_PERMISSION_PROFILE, MaesRuntime

# Add parent directory to path to import bridge
ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))
from bridge import load_plugins


def _setup_logging() -> None:
    os.makedirs("logs", exist_ok=True)
    log_file = os.path.join("logs", f"maes-{datetime.now().strftime('%Y%m%d')}.log")
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def _parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Maes - Intent-driven accessibility operating layer"
    )
    parser.add_argument(
        "--cli", "-c",
        action="store_true",
        help="Run in CLI mode instead of launching Electron UI",
    )
    parser.add_argument(
        "--voice",
        action="store_true",
        help="Enable voice mode (speech input/output using ElevenLabs)",
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
    """Output message via print and optionally voice."""
    print(message)
    if voice_controller:
        # Remove emoji/symbols for cleaner speech
        clean_message = message.replace("✓", "").replace("✗", "").replace("⚠", "").strip()
        if clean_message:
            voice_controller.speak(clean_message, blocking=True)


def main() -> None:
    args = _parse_args()
def launch_electron_ui() -> None:
    """Launch the Electron UI"""
    electron_dir = ROOT / "electron"
    
    # Check if electron is installed
    package_json = electron_dir / "package.json"
    node_modules = electron_dir / "node_modules"
    
    if not package_json.exists():
        print(f"❌ Error: Electron UI not found at {electron_dir}")
        print("Please ensure the electron directory exists.")
        sys.exit(1)
    
    # Install dependencies if needed
    if not node_modules.exists():
        print("📦 Installing Electron dependencies...")
        try:
            subprocess.run(
                ["npm", "install"],
                cwd=electron_dir,
                check=True,
                capture_output=True
            )
            print("✓ Dependencies installed")
        except subprocess.CalledProcessError as e:
            print(f"❌ Failed to install dependencies: {e}")
            print("Please run 'npm install' in the electron directory manually.")
            sys.exit(1)
        except FileNotFoundError:
            print("❌ npm not found. Please install Node.js and npm first.")
            print("Download from: https://nodejs.org/")
            sys.exit(1)
    
    # Launch Electron
    print("🚀 Launching Maes Electron UI...")
    try:
        subprocess.run(
            ["npm", "start"],
            cwd=electron_dir,
            check=False  # Don't raise exception on exit
        )
    except KeyboardInterrupt:
        print("\n✓ Electron UI closed")
    except Exception as e:
        print(f"❌ Error launching Electron UI: {e}")
        sys.exit(1)


def run_cli_mode() -> None:
    """Run the original CLI mode"""
    args = _parse_args()
    _setup_logging()

    # Initialize voice controller if voice mode enabled
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

    # OS Detection and Warning
    system = platform.system()
    print(f"Maes MVP - Running on {system}")
    if system == "Darwin":
        print("✓ macOS detected (recommended)")
        print("⚠ Note: Ensure accessibility permissions are enabled for Terminal/Python")
        print("  (System Preferences → Security & Privacy → Accessibility)")
    elif system == "Windows":
        print("⚠ Windows support is experimental and not fully tested")
    elif system == "Linux":
        print("⚠ Linux support is experimental and not fully tested")
    else:
        print(f"⚠ WARNING: Unsupported OS '{system}'. Functionality may be limited.")

    calendar_credentials = os.getenv("MAES_CALENDAR_CREDENTIALS_PATH")
    calendar_token = os.getenv("MAES_CALENDAR_TOKEN_PATH")
    gmail_credentials = os.getenv("MAES_GMAIL_CREDENTIALS_PATH")
    gmail_token = os.getenv("MAES_GMAIL_TOKEN_PATH")

    # Load MCP plugins
    user_config = {
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
        print(f"✓ Loaded {len(mcp_tools)} MCP tools: {', '.join(tool_map.keys())}")
    except Exception as e:
        print(f"⚠ Warning: Could not load MCP plugins: {e}")
        tool_map = {}

    runtime = MaesRuntime(
        dry_run=False,
        speed=1.0,
        permission_profile=DEFAULT_PERMISSION_PROFILE,
        enable_kill_switch=True,
        mcp_tools=tool_map,
    )

    # Startup message
    mode_desc = "voice" if (args.voice or args.voice_only) else "text"
    if args.tts_only:
        mode_desc = "text input with voice output"
    startup_msg = f"\nMaes started in {mode_desc} mode. Say 'exit' to quit. Press ESC for kill switch."
    print(startup_msg)

    if voice_controller:
        voice_controller.speak("Maes is ready. How can I help you?", blocking=True)

    print("\nMaes started. Type 'exit' to quit. Press ESC for kill switch.")
    print("\nℹ️  Features:")
    print("  - Advanced emotional intelligence (Plutchik's 8 emotions, burnout detection, sarcasm awareness)")
    print("  - Calendar & todo-aware mood analysis (auto-suggests rescheduling)")
    print("  - Try: 'check my mood' | 'how am i' | 'lighten my load' | 'reschedule tasks'")
    print("  - Try: 'show my schedule today' | 'move tasks to tomorrow'")
    print("  - Enhanced web search, file context, autofill passwords")
    print("  - Type 'context' to see current context summary")

    try:
        while True:
            input_data = read_text_input()
            raw_text = input_data["raw_text"]
            if not raw_text:
                continue
            if raw_text.lower() in {"exit", "quit"}:
                break
            
            # Special command to show context
            if raw_text.lower() == "context":
                context_summary = runtime.session.get_context_summary()
                print("\n" + "="*60)
                print("Current Context:")
                print("="*60)
                print(context_summary)
                print("="*60 + "\n")
                continue

            result = runtime.handle_input(raw_text, source=input_data.get("source", "text"))
            if result.get("steps"):
                print("Planned steps:")
                for index, step in enumerate(result["steps"], start=1):
                    print(f"  {index}. {step['action']} - {step['description']}")
            print(result.get("message", ""))
            suggestions = result.get("suggestions", [])
            if suggestions:
                print("Try:")
                for suggestion in suggestions:
                    print(f"  - {suggestion}")
            logging.info("Runtime result: %s", result)
    finally:
        runtime.close()


def main() -> None:
    """Main entry point - launches Electron UI by default, CLI with --cli flag"""
    # Check for CLI mode flag
    if "--cli" in sys.argv or "-c" in sys.argv:
        run_cli_mode()
    else:
        launch_electron_ui()


if __name__ == "__main__":
    main()
