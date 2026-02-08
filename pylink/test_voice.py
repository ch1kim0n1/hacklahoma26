"""Test script for voice-controlled PixelLink with TTS and STT."""

import sys
import os

# Add the pylink directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

load_dotenv()

from core.context.session import SessionContext
from core.executor.engine import ExecutionEngine
from core.nlu.parser import parse_intent
from core.planner.action_planner import ActionPlanner
from core.safety.guard import KillSwitch, SafetyGuard


def test_tts():
    """Test text-to-speech."""
    print("=" * 50)
    print("TEST 1: Text-to-Speech (TTS)")
    print("=" * 50)

    from core.voice.tts import TextToSpeech

    tts = TextToSpeech()
    print("TTS initialized successfully!")
    print("Speaking: 'Hello! I am PixelLink, your voice assistant.'")

    success = tts.speak(
        "Hello! I am PixelLink, your voice assistant. What would you like me to do?"
    )

    if success:
        print("TTS test PASSED")
    else:
        print("TTS test FAILED")

    return success


def test_stt():
    """Test speech-to-text."""
    print("\n" + "=" * 50)
    print("TEST 2: Speech-to-Text (STT) - Whisper ONNX")
    print("=" * 50)

    from core.voice.stt import SpeechToText

    print("Loading Whisper model (this may take a moment on first run)...")
    stt = SpeechToText()
    print("STT initialized successfully!")
    print("\nPlease say something (e.g., 'open Safari')...")
    print("You have 10 seconds to start speaking.\n")

    def status_callback(status):
        if status == "listening":
            print("Listening...")
        elif status == "processing":
            print("Processing your speech...")

    text = stt.listen(prompt_callback=status_callback)

    if text:
        print(f"\nYou said: '{text}'")
        print("STT test PASSED")
        return text
    else:
        print("\nNo speech detected or transcription failed.")
        print("STT test FAILED")
        return None


def test_conversation():
    """Test a full conversation loop: TTS -> STT -> TTS response."""
    print("\n" + "=" * 50)
    print("TEST 3: Full Conversation (TTS + STT + Response)")
    print("=" * 50)

    from core.voice import VoiceController

    voice = VoiceController()
    print("VoiceController initialized!")

    # AI speaks first
    voice.speak("I'm listening. Please tell me what you'd like to do.", blocking=True)

    # Listen for user
    print("\nListening for your command...")
    user_input = voice.listen()

    if user_input:
        print(f"\nYou said: '{user_input}'")

        # AI responds acknowledging what was heard
        response = f"I heard you say: {user_input}. I'll work on that."
        print(f"AI responding: '{response}'")
        voice.speak(response, blocking=True)

        print("\nConversation test PASSED")
        return True
    else:
        print("\nNo speech detected.")
        print("Conversation test FAILED")
        return False


def run_voice_assistant():
    """Run the full voice-controlled assistant with command execution."""
    print("\n" + "=" * 60)
    print("  PIXELLINK VOICE ASSISTANT")
    print("  Voice-controlled computer automation")
    print("=" * 60 + "\n")

    # Check API key for TTS
    api_key = os.getenv("ELEVEN_LABS_API_KEY")
    if not api_key:
        print("ERROR: ELEVEN_LABS_API_KEY not found in .env file!")
        print("TTS will not work without the API key.")
        return

    print(f"ElevenLabs API Key: {api_key[:10]}...{api_key[-4:]}")
    print()

    # Initialize all components
    from core.voice import VoiceController

    print("Initializing voice controller...")
    voice = VoiceController(whisper_model="base")
    print("Voice controller ready!")

    print("Initializing execution engine...")
    session = SessionContext()
    guard = SafetyGuard()
    kill_switch = KillSwitch()
    kill_switch.start()
    planner = ActionPlanner()
    executor = ExecutionEngine(kill_switch)
    print("Execution engine ready!")

    print("\n" + "-" * 50)
    print("Voice assistant is now active!")
    print("Say commands like:")
    print("  - 'Open Safari'")
    print("  - 'Open Notes'")
    print("  - 'Type hello world'")
    print("Say 'exit' or 'goodbye' to quit.")
    print("Press ESC at any time for emergency stop.")
    print("-" * 50 + "\n")

    # Greeting
    voice.speak("PixelLink is ready. What would you like me to do?", blocking=True)

    while True:
        # Listen for user command
        print("\nListening...")
        user_input = voice.listen()

        if not user_input:
            voice.speak("I didn't catch that. Please try again.", blocking=True)
            continue

        print(f"You said: '{user_input}'")

        # Check for exit commands
        if user_input.lower().strip() in {"exit", "quit", "goodbye", "bye", "stop"}:
            voice.speak("Goodbye! Have a great day.", blocking=True)
            break

        # Parse the intent
        intent = parse_intent(user_input, session)
        session.record_intent(intent.name, user_input)

        print(f"Parsed intent: {intent.name}")

        # Handle confirmation/cancellation for pending actions
        if session.pending_steps:
            if intent.name == "confirm":
                voice.speak("Confirming action.", blocking=True)
                result = executor.execute_steps(session.pending_steps, guard)
                session.clear_pending()
                if result.completed:
                    voice.speak("Done.", blocking=True)
                else:
                    voice.speak("Execution was halted.", blocking=True)
                continue
            if intent.name == "cancel":
                session.clear_pending()
                voice.speak("Cancelled.", blocking=True)
                continue

        # Handle exit intent
        if intent.name == "exit":
            voice.speak("Goodbye! Have a great day.", blocking=True)
            break

        # Handle unknown intent
        if intent.name == "unknown":
            voice.speak(
                "Sorry, I didn't understand that. Try saying open Safari, or type hello.",
                blocking=True,
            )
            continue

        # Plan the action
        steps = planner.plan(intent, session, guard)
        print(f"Planned {len(steps)} step(s)")

        # Validate safety
        safety = guard.validate_plan(steps)
        if not safety.allowed:
            voice.speak(f"I cannot do that. {safety.reason}", blocking=True)
            continue

        # Execute the steps
        result = executor.execute_steps(steps, guard)

        # Track last app for context
        for step in steps:
            if step.action in {"open_app", "focus_app"}:
                session.set_last_app(step.params.get("app", ""))
                break

        # Respond based on result
        if result.pending_steps:
            session.set_pending(result.pending_steps)
            voice.speak(
                "This action requires confirmation. Say confirm or cancel.",
                blocking=True,
            )
        elif result.completed:
            # Generate a friendly response based on what was done
            response = _generate_response(intent, steps)
            voice.speak(response, blocking=True)
        else:
            voice.speak("Something went wrong. The task did not complete.", blocking=True)

    # Cleanup
    kill_switch.stop()
    voice.cleanup()
    print("\nVoice assistant stopped.")


def _generate_response(intent, steps) -> str:
    """Generate a spoken response based on the completed action."""
    if intent.name == "open_app":
        app = intent.entities.get("app", "the application")
        return f"{app} is now open."
    elif intent.name == "focus_app":
        app = intent.entities.get("app", "the application")
        return f"Switched to {app}."
    elif intent.name == "type_text":
        return "Text has been typed."
    elif intent.name == "click":
        return "Clicked."
    elif intent.name == "reply_email":
        return "Email reply is ready."
    else:
        return "Done."


def main():
    print("\n" + "=" * 60)
    print("  PIXELLINK VOICE TEST SUITE")
    print("  TTS: ElevenLabs Flash v2.5")
    print("  STT: Whisper ONNX (faster-whisper)")
    print("=" * 60 + "\n")

    # Check API key
    api_key = os.getenv("ELEVEN_LABS_API_KEY")
    if not api_key:
        print("ERROR: ELEVEN_LABS_API_KEY not found in .env file!")
        print("TTS features will not work.")
    else:
        print(f"API Key found: {api_key[:10]}...{api_key[-4:]}")
    print()

    # Menu
    print("Select a test to run:")
    print("  1. Test TTS only (AI speaks to you)")
    print("  2. Test STT only (You speak, AI transcribes)")
    print("  3. Test full conversation (TTS + STT + Response)")
    print("  4. Run voice assistant with command execution")
    print("  5. Run all tests")
    print("  q. Quit")
    print()

    choice = input("Enter choice (1-5 or q): ").strip().lower()

    if choice == "1":
        test_tts()
    elif choice == "2":
        test_stt()
    elif choice == "3":
        test_conversation()
    elif choice == "4":
        run_voice_assistant()
    elif choice == "5":
        tts_ok = test_tts()
        if tts_ok:
            stt_result = test_stt()
            if stt_result:
                test_conversation()
    elif choice == "q":
        print("Goodbye!")
    else:
        print("Invalid choice.")


if __name__ == "__main__":
    main()
