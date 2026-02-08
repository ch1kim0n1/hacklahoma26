"""Text-to-Speech module using ElevenLabs API."""

from __future__ import annotations

import io
import logging
import os
import threading
from typing import Optional

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class TextToSpeech:
    """Text-to-Speech engine using ElevenLabs API."""

    # Default voice - Rachel (clear, professional female voice)
    DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"

    # Model options:
    # - "eleven_flash_v2_5" - Fastest, lowest latency (recommended for real-time)
    # - "eleven_turbo_v2_5" - Fast, low latency
    # - "eleven_multilingual_v2" - Higher quality, supports multiple languages
    DEFAULT_MODEL = "eleven_flash_v2_5"

    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: Optional[str] = None,
        model: Optional[str] = None,
    ):
        """Initialize TTS engine.

        Args:
            api_key: ElevenLabs API key. If None, loads from environment.
            voice_id: Voice ID to use. If None, uses default Rachel voice.
            model: Model to use. If None, uses turbo model for low latency.
        """
        self.api_key = api_key or os.getenv("ELEVEN_LABS_API_KEY") or os.getenv("eleven-labs")
        if not self.api_key:
            raise ValueError(
                "ElevenLabs API key not found. Set ELEVEN_LABS_API_KEY in .env file."
            )

        self.voice_id = voice_id or self.DEFAULT_VOICE_ID
        self.model = model or self.DEFAULT_MODEL
        self._client = None
        self._is_speaking = False
        self._speak_lock = threading.Lock()

        logging.info("TextToSpeech initialized with voice_id=%s, model=%s", self.voice_id, self.model)

    @property
    def client(self):
        """Lazy-load ElevenLabs client."""
        if self._client is None:
            from elevenlabs.client import ElevenLabs
            self._client = ElevenLabs(api_key=self.api_key)
        return self._client

    def speak(self, text: str, blocking: bool = True) -> bool:
        """Convert text to speech and play it.

        Args:
            text: The text to speak.
            blocking: If True, wait for speech to complete. If False, return immediately.

        Returns:
            True if speech started/completed successfully, False otherwise.
        """
        if not text or not text.strip():
            return False

        if blocking:
            return self._speak_sync(text)
        else:
            thread = threading.Thread(target=self._speak_sync, args=(text,), daemon=True)
            thread.start()
            return True

    def _speak_sync(self, text: str) -> bool:
        """Synchronously speak the text."""
        with self._speak_lock:
            self._is_speaking = True
            try:
                # Generate audio using ElevenLabs
                audio_generator = self.client.text_to_speech.convert(
                    voice_id=self.voice_id,
                    text=text,
                    model_id=self.model,
                    output_format="mp3_44100_128",
                )

                # Collect audio bytes from generator
                audio_bytes = b"".join(audio_generator)

                # Play the audio
                self._play_audio(audio_bytes)

                logging.info("TTS spoke: %s", text[:50] + "..." if len(text) > 50 else text)
                return True

            except Exception as e:
                logging.error("TTS error: %s", str(e))
                print(f"[TTS Error: {e}]")
                return False
            finally:
                self._is_speaking = False

    def _play_audio(self, audio_bytes: bytes) -> None:
        """Play audio bytes using available audio backend."""
        import platform

        # On macOS, use afplay directly (more reliable, avoids pydub/audioop issues in Python 3.13)
        if platform.system() == "Darwin":
            self._play_with_system(audio_bytes)
            return

        try:
            # Try using pydub + simpleaudio (cross-platform)
            from pydub import AudioSegment
            from pydub.playback import play

            audio = AudioSegment.from_mp3(io.BytesIO(audio_bytes))
            play(audio)

        except (ImportError, ModuleNotFoundError):
            # Fallback: save to temp file and play with system command
            self._play_with_system(audio_bytes)

    def _play_with_system(self, audio_bytes: bytes) -> None:
        """Fallback: play audio using system command."""
        import subprocess
        import tempfile
        import platform

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name

        try:
            system = platform.system()
            if system == "Darwin":  # macOS
                subprocess.run(["afplay", temp_path], check=True, capture_output=True)
            elif system == "Windows":
                # Use Windows Media Player
                subprocess.run(
                    ["powershell", "-c", f"(New-Object Media.SoundPlayer '{temp_path}').PlaySync()"],
                    check=True,
                    capture_output=True,
                )
            else:  # Linux
                # Try common audio players
                for player in ["mpv", "ffplay", "aplay"]:
                    try:
                        subprocess.run([player, temp_path], check=True, capture_output=True)
                        break
                    except FileNotFoundError:
                        continue
        finally:
            os.unlink(temp_path)

    def stop(self) -> None:
        """Stop current speech (if possible)."""
        # Note: Stopping mid-speech is complex with current implementation
        # Would require async audio playback with cancellation
        self._is_speaking = False

    @property
    def is_speaking(self) -> bool:
        """Check if currently speaking."""
        return self._is_speaking

    def list_voices(self) -> list[dict]:
        """List available voices.

        Returns:
            List of voice dictionaries with 'voice_id' and 'name'.
        """
        try:
            response = self.client.voices.get_all()
            return [
                {"voice_id": v.voice_id, "name": v.name}
                for v in response.voices
            ]
        except Exception as e:
            logging.error("Failed to list voices: %s", str(e))
            return []

    def set_voice(self, voice_id: str) -> None:
        """Change the voice.

        Args:
            voice_id: The voice ID to use.
        """
        self.voice_id = voice_id
        logging.info("TTS voice changed to: %s", voice_id)
