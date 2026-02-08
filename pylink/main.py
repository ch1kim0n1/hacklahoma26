from __future__ import annotations

import argparse
import logging
import os
import platform
from datetime import datetime
from typing import Optional

from core.context.session import SessionContext
from core.executor.engine import ExecutionEngine
from core.input.text_input import read_text_input
from core.nlu.parser import parse_intent
from core.planner.action_planner import ActionPlanner
from core.safety.guard import KillSwitch, SafetyGuard


def _setup_logging() -> None:
    os.makedirs("logs", exist_ok=True)
    log_file = os.path.join("logs", f"pixelink-{datetime.now().strftime('%Y%m%d')}.log")
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def _parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="PixelLink - Intent-driven accessibility operating layer"
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
    print(f"PixelLink MVP - Running on {system}")
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

    session = SessionContext()
    guard = SafetyGuard()
    kill_switch = KillSwitch()
    kill_switch.start()
    planner = ActionPlanner()
    executor = ExecutionEngine(kill_switch)

    # Startup message
    mode_desc = "voice" if (args.voice or args.voice_only) else "text"
    if args.tts_only:
        mode_desc = "text input with voice output"
    startup_msg = f"\nPixelLink started in {mode_desc} mode. Say 'exit' to quit. Press ESC for kill switch."
    print(startup_msg)

    if voice_controller:
        voice_controller.speak("PixelLink is ready. How can I help you?", blocking=True)

    while True:
        # Get input (voice or text)
        if voice_controller and not args.tts_only:
            from core.voice.voice_controller import read_voice_input
            input_data = read_voice_input(voice_controller)
        else:
            input_data = read_text_input()

        raw_text = input_data["raw_text"]

        if not raw_text:
            continue
        if raw_text.lower() in {"exit", "quit", "goodbye", "bye"}:
            _output("Goodbye!", voice_controller)
            break

        intent = parse_intent(raw_text, session)
        session.record_intent(intent.name, raw_text)

        if session.pending_steps:
            if intent.name == "confirm":
                result = executor.execute_steps(session.pending_steps, guard)
                session.clear_pending()
                if not result.completed:
                    _output("Execution halted.", voice_controller)
                continue
            if intent.name == "cancel":
                session.clear_pending()
                _output("Pending actions canceled.", voice_controller)
                continue

        if intent.name == "unknown":
            _output("Sorry, I didn't understand that.", voice_controller)
            _output("Try: 'open Notes', 'type hello', or 'reply email saying I'll send it tomorrow'", voice_controller)
            continue

        steps = planner.plan(intent, session, guard)
        print("Planned steps:")
        for index, step in enumerate(steps, start=1):
            print(f"  {index}. {step.action} - {step.description}")

        safety = guard.validate_plan(steps)
        if not safety.allowed:
            _output(safety.reason, voice_controller)
            continue

        logging.info("Intent: %s | Steps: %s", intent.name, [s.action for s in steps])
        result = executor.execute_steps(steps, guard)

        # Track last app for context
        for step in steps:
            if step.action in {"open_app", "focus_app"}:
                session.set_last_app(step.params.get("app", ""))
                break

        if result.pending_steps:
            session.set_pending(result.pending_steps)
            _output("Awaiting confirmation to proceed. Say 'confirm' or 'cancel'.", voice_controller)
        elif result.completed:
            _output("Task completed successfully.", voice_controller)
        else:
            _output("Task did not complete.", voice_controller)

    kill_switch.stop()
    if voice_controller:
        voice_controller.cleanup()


if __name__ == "__main__":
    main()
