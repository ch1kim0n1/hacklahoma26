from __future__ import annotations

import logging
import os
import platform
from datetime import datetime

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


def main() -> None:
    _setup_logging()

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

    print("\nPixelLink started. Type 'exit' to quit. Press ESC for kill switch.")

    while True:
        input_data = read_text_input()
        raw_text = input_data["raw_text"]

        if not raw_text:
            continue
        if raw_text.lower() in {"exit", "quit"}:
            break

        intent = parse_intent(raw_text, session)
        session.record_intent(intent.name, raw_text)

        if session.pending_steps:
            if intent.name == "confirm":
                result = executor.execute_steps(session.pending_steps, guard)
                session.clear_pending()
                if not result.completed:
                    print("Execution halted.")
                continue
            if intent.name == "cancel":
                session.clear_pending()
                print("Pending actions canceled.")
                continue

        if intent.name == "unknown":
            print("Sorry, I didn't understand that.")
            print("Try: 'open <app>', 'type <text>', 'reply email saying <message>'")
            continue

        steps = planner.plan(intent, session, guard)
        print("Planned steps:")
        for index, step in enumerate(steps, start=1):
            print(f"  {index}. {step.action} - {step.description}")
        safety = guard.validate_plan(steps)
        if not safety.allowed:
            print(safety.reason)
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
            print("Awaiting confirmation to proceed. Type 'confirm' or 'cancel'.")
        elif result.completed:
            print("✓ Task completed successfully.")
        else:
            print("✗ Task did not complete.")

    kill_switch.stop()


if __name__ == "__main__":
    main()
