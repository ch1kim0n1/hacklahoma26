"""Voice Controller - Unified interface for TTS and STT."""

from __future__ import annotations

import logging
import threading
from typing import Optional, Callable

from core.voice.tts import TextToSpeech
from core.voice.stt import SpeechToText


class VoiceController:
    """Unified controller for voice input and output.

    This class manages the voice interaction loop:
    1. Listen for user speech (STT)
    2. Process the command (handled by caller)
    3. Speak the response (TTS)

    Provides both synchronous and asynchronous interfaces.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: Optional[str] = None,
        enable_tts: bool = True,
        enable_stt: bool = True,
        whisper_model: str = "base",
    ):
        """Initialize VoiceController.

        Args:
            api_key: ElevenLabs API key for TTS. If None, loads from environment.
            voice_id: Voice ID for TTS. If None, uses default.
            enable_tts: Whether to enable text-to-speech.
            enable_stt: Whether to enable speech-to-text.
            whisper_model: Whisper model size for STT (tiny, base, small, medium, large-v3).
        """
        self.enable_tts = enable_tts
        self.enable_stt = enable_stt
        self._init_errors: dict[str, str] = {}

        self._tts: Optional[TextToSpeech] = None
        self._stt: Optional[SpeechToText] = None

        if enable_tts:
            try:
                self._tts = TextToSpeech(api_key=api_key, voice_id=voice_id)
            except Exception as exc:
                self._tts = None
                self.enable_tts = False
                self._init_errors["tts"] = str(exc)
                logging.info("Failed to initialize TTS: %s", exc)

        if enable_stt:
            try:
                self._stt = SpeechToText(model_size=whisper_model)
            except Exception as exc:
                self._stt = None
                self.enable_stt = False
                self._init_errors["stt"] = str(exc)
                logging.info("Failed to initialize STT: %s", exc)

        self._is_active = False
        self._stop_event = threading.Event()

        logging.info(
            "VoiceController initialized (TTS=%s, STT=%s)",
            "enabled" if self._tts else "disabled",
            "enabled" if self._stt else "disabled",
        )

    def speak(self, text: str, blocking: bool = True) -> bool:
        """Speak text using TTS.

        Args:
            text: Text to speak.
            blocking: If True, wait for speech to complete.

        Returns:
            True if successful, False otherwise.
        """
        if not self.enable_tts or not self._tts:
            print(f"[Voice]: {text}")
            return True

        return self._tts.speak(text, blocking=blocking)

    def listen(
        self,
        allow_text_fallback: bool = True,
        status_callback: Optional[Callable[[str], None]] = None,
        immediate_feedback: Optional[Callable[[str], None]] = None,
    ) -> str:
        """Listen for speech and return transcribed text.

        Args:
            allow_text_fallback: If True and STT is unavailable, fallback to stdin.
                Set False for non-interactive environments (like desktop bridge).

        Returns:
            Transcribed text, or empty string if nothing detected.
        """
        if immediate_feedback:
            immediate_feedback("Listening")

        if not self.enable_stt or not self._stt:
            if allow_text_fallback:
                # Fallback to text input
                return input("Voice> ").strip()
            return ""

        callback = status_callback
        if callback is None:
            def default_status_callback(status: str):
                if immediate_feedback:
                    if status == "listening":
                        immediate_feedback("Listening")
                    elif status == "processing":
                        immediate_feedback("Understanding")
                if status == "listening":
                    print("🎤 Listening...")
                elif status == "processing":
                    print("⏳ Processing...")

            callback = default_status_callback

        return self._stt.listen(prompt_callback=callback)

    def listen_and_respond(
        self,
        process_callback: Callable[[str], str],
        greeting: Optional[str] = None,
    ) -> None:
        """Run a voice interaction loop.

        Args:
            process_callback: Function that takes user speech and returns response.
            greeting: Optional greeting to speak at start.
        """
        self._is_active = True
        self._stop_event.clear()

        try:
            if greeting:
                self.speak(greeting)

            while not self._stop_event.is_set():
                # Listen for user input
                user_input = self.listen()

                if not user_input:
                    continue

                # Check for exit commands
                if user_input.lower() in {"exit", "quit", "goodbye", "bye"}:
                    self.speak("Goodbye!")
                    break

                # Process and respond
                response = process_callback(user_input)
                if response:
                    self.speak(response)

        finally:
            self._is_active = False

    def say_and_listen(self, prompt: str) -> str:
        """Speak a prompt and listen for response.

        Args:
            prompt: Text to speak before listening.

        Returns:
            User's spoken response.
        """
        self.speak(prompt)
        return self.listen()

    def confirm(self, question: str) -> bool:
        """Ask a yes/no question and get confirmation.

        Args:
            question: The question to ask.

        Returns:
            True if user confirms, False otherwise.
        """
        response = self.say_and_listen(question)
        affirmative = {"yes", "yeah", "yep", "confirm", "ok", "okay", "sure", "do it", "go ahead"}
        return response.lower().strip() in affirmative

    def stop(self) -> None:
        """Stop the voice controller."""
        self._stop_event.set()
        if self._tts:
            self._tts.stop()
        if self._stt:
            self._stt.stop()

    def cleanup(self) -> None:
        """Clean up resources."""
        self.stop()
        if self._stt:
            self._stt.cleanup()

    @property
    def is_speaking(self) -> bool:
        """Check if currently speaking."""
        return self._tts.is_speaking if self._tts else False

    @property
    def is_listening(self) -> bool:
        """Check if currently listening."""
        return self._stt.is_listening if self._stt else False

    @property
    def is_active(self) -> bool:
        """Check if voice loop is active."""
        return self._is_active

    def set_voice(self, voice_id: str) -> None:
        """Change the TTS voice.

        Args:
            voice_id: The ElevenLabs voice ID to use.
        """
        if self._tts:
            self._tts.set_voice(voice_id)

    def list_voices(self) -> list[dict]:
        """List available TTS voices.

        Returns:
            List of voice dictionaries with 'voice_id' and 'name'.
        """
        if self._tts:
            return self._tts.list_voices()
        return []

    @property
    def tts_available(self) -> bool:
        """Whether TTS is available."""
        return self._tts is not None and self.enable_tts

    @property
    def stt_available(self) -> bool:
        """Whether STT is available."""
        return self._stt is not None and self.enable_stt

    @property
    def init_errors(self) -> dict[str, str]:
        """Initialization errors keyed by subsystem name."""
        return dict(self._init_errors)

    @property
    def last_stt_error(self) -> str:
        """Last STT error message, if any."""
        if self._stt and getattr(self._stt, "last_error", None):
            return str(self._stt.last_error)
        return ""

    def prewarm_stt_async(self) -> None:
        """Preload STT model in background."""
        if self._stt:
            self._stt.prewarm_async()


def read_voice_input(voice: VoiceController, prompt: str = "") -> dict:
    """Read input from voice (drop-in replacement for read_text_input).

    Args:
        voice: VoiceController instance.
        prompt: Optional prompt to speak before listening.

    Returns:
        Input dictionary compatible with text_input format.
    """
    import time

    if prompt:
        voice.speak(prompt, blocking=True)

    raw_text = voice.listen()
    normalized = " ".join(raw_text.split())

    return {
        "raw_text": normalized,
        "timestamp": time.time(),
        "source": "voice",
    }
