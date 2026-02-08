"""
PixelLink Email Reply Demo - Automated Workflow

This demo simulates the full accessibility workflow for Alex:
- Opening the Mail app
- Composing a reply to an email
- Typing the reply content
- Confirming and sending

This is a deterministic, automated demo suitable for live presentations.
"""

import sys
import time
from pathlib import Path

# Allow running this file directly: `python demo/email_reply_demo.py`
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.context.session import SessionContext
from core.executor.engine import ExecutionEngine
from core.nlu.parser import parse_intent
from core.planner.action_planner import ActionPlanner
from core.safety.guard import KillSwitch, SafetyGuard


def print_header(text: str) -> None:
    """Print a formatted header"""
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60 + "\n")


def simulate_user_input(text: str) -> None:
    """Simulate user voice-to-text input"""
    print(f"🗣  Alex (via voice-to-text): \"{text}\"")
    time.sleep(0.5)


def run_automated_demo() -> None:
    """Run the automated email reply demonstration"""
    print_header("PixelLink - Accessibility Demo for Alex")

    print("📋 Scenario:")
    print("   Alex has limited hand mobility and needs to reply to an email")
    print("   without using a keyboard or mouse. Alex will use voice-to-text")
    print("   to control the computer through PixelLink.\n")

    input("Press ENTER to start the demo...")

    # Initialize PixelLink components
    session = SessionContext()
    guard = SafetyGuard()
    kill_switch = KillSwitch()
    kill_switch.start()
    planner = ActionPlanner()
    executor = ExecutionEngine(kill_switch)

    # Demo workflow steps
    demo_steps = [
        {
            "input": "open Mail",
            "description": "Opening the email application"
        },
        {
            "input": "reply email saying I'll send the file by tomorrow afternoon",
            "description": "Composing the email reply"
        },
        {
            "input": "confirm",
            "description": "Confirming to send the email"
        }
    ]

    try:
        for step_num, step in enumerate(demo_steps, 1):
            print_header(f"Step {step_num}: {step['description']}")

            # Simulate user voice input
            simulate_user_input(step["input"])

            # Parse the intent
            intent = parse_intent(step["input"], session)
            session.record_intent(intent.name, step["input"])
            print(f"\n✓ Parsed Intent: {intent.name}")

            # Handle pending confirmation flow
            if session.pending_steps:
                if intent.name == "confirm":
                    print("\n📧 Sending email...")
                    result = executor.execute_steps(session.pending_steps, guard)
                    session.clear_pending()

                    if result.completed:
                        print("\n✓ Email sent successfully!")
                    else:
                        print("\n✗ Email sending was halted.")
                    continue

                elif intent.name == "cancel":
                    session.clear_pending()
                    print("\n⚠ User canceled the action.")
                    continue

            # Skip unknown intents
            if intent.name == "unknown":
                print("\n⚠ Intent not recognized. Skipping...")
                continue

            # Plan the actions
            steps = planner.plan(intent, session, guard)

            if steps:
                print(f"\n📝 Planned Actions:")
                for idx, action_step in enumerate(steps, 1):
                    print(f"   {idx}. {action_step.description or action_step.action}")

                # Validate safety
                safety = guard.validate_plan(steps)
                if not safety.allowed:
                    print(f"\n🚫 {safety.reason}")
                    continue

                # Execute the steps
                print("\n⚙  Executing...")
                time.sleep(0.5)

                result = executor.execute_steps(steps, guard)

                # Track last app for context
                for action_step in steps:
                    if action_step.action in {"open_app", "focus_app"}:
                        session.set_last_app(action_step.params.get("app", ""))
                        break

                # Handle pending confirmation
                if result.pending_steps:
                    session.set_pending(result.pending_steps)
                    print("\n⏸  Awaiting user confirmation to proceed...")
                    print("   (Next step: Alex will say 'confirm' or 'cancel')")
                    input("\nPress ENTER to continue to confirmation step...")
                elif result.completed:
                    print("\n✓ Action completed successfully!")
                else:
                    print("\n⚠ Action did not complete as expected.")
            else:
                print("\n⚠ No actions planned for this intent.")

            # Small pause between steps for readability
            time.sleep(1)

        # Demo complete
        print_header("Demo Complete!")
        print("✓ Alex successfully replied to an email hands-free using PixelLink.")
        print("\n📊 Summary:")
        print("   • Used voice-to-text to control the computer")
        print("   • No keyboard or mouse required")
        print("   • Safe execution with confirmation before sending")
        print("   • Kill switch available at any time (ESC key)")

        print("\n💡 This demonstrates how PixelLink removes physical barriers")
        print("   between people and technology through intent-based control.\n")

    except KeyboardInterrupt:
        print("\n\n⚠ Demo interrupted by user.")
    except Exception as e:
        print(f"\n\n✗ Demo error: {str(e)}")
    finally:
        kill_switch.stop()
        print("\n👋 Demo ended.\n")


def run_manual_demo() -> None:
    """Run an interactive demo where user manually types commands"""
    print_header("PixelLink - Manual Email Reply Demo")

    print("This demo lets you manually test the email reply workflow.")
    print("You'll be prompted to enter each command.\n")

    session = SessionContext()
    guard = SafetyGuard()
    kill_switch = KillSwitch()
    kill_switch.start()
    planner = ActionPlanner()
    executor = ExecutionEngine(kill_switch)

    print("Commands you'll use:")
    print("  1. open Mail")
    print("  2. reply email saying [your message]")
    print("  3. confirm (or cancel)\n")

    try:
        while True:
            user_input = input("\nPixelLink> ").strip()

            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", "done"}:
                print("✓ Demo ended.")
                break

            intent = parse_intent(user_input, session)
            session.record_intent(intent.name, user_input)

            print(f"Intent: {intent.name}")

            if session.pending_steps:
                if intent.name == "confirm":
                    result = executor.execute_steps(session.pending_steps, guard)
                    session.clear_pending()
                    continue
                if intent.name == "cancel":
                    session.clear_pending()
                    print("Pending actions canceled.")
                    continue

            if intent.name == "unknown":
                print("Unknown intent. Try: 'open Mail' or 'reply email saying [message]'")
                continue

            steps = planner.plan(intent, session, guard)
            if steps:
                print("Planned steps:")
                for idx, step in enumerate(steps, 1):
                    print(f"  {idx}. {step.description}")

                safety = guard.validate_plan(steps)
                if not safety.allowed:
                    print(safety.reason)
                    continue

                result = executor.execute_steps(steps, guard)

                for step in steps:
                    if step.action in {"open_app", "focus_app"}:
                        session.set_last_app(step.params.get("app", ""))
                        break

                if result.pending_steps:
                    session.set_pending(result.pending_steps)
                    print("Awaiting confirmation. Type 'confirm' or 'cancel'.")

    except KeyboardInterrupt:
        print("\n\nDemo interrupted.")
    finally:
        kill_switch.stop()


if __name__ == "__main__":
    import sys

    print("\nPixelLink Email Reply Demo\n")
    print("Choose demo mode:")
    print("  1. Automated Demo (recommended for presentations)")
    print("  2. Manual Demo (interactive testing)")
    print()

    choice = input("Enter choice (1 or 2, default=1): ").strip() or "1"

    if choice == "1":
        run_automated_demo()
    elif choice == "2":
        run_manual_demo()
    else:
        print("Invalid choice. Running automated demo.")
        run_automated_demo()
