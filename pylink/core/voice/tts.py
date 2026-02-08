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
    """Text-to-Speech engine using ElevenLabs API with natural voice settings."""

    # Voice options for more natural, less robotic speech:
    # - "pNInz6obpgDQGcFmaJgB" - Adam (deep, warm male voice)
    # - "EXAVITQu4vr4xnSDxMaL" - Bella (soft, friendly female voice)
    # - "ErXwobaYiN019PkySvjV" - Antoni (warm, conversational male voice)
    # - "MF3mGyEYCl7XYWbV9V6O" - Elli (young, friendly female voice)
    # - "jsCqWAovK2LkecY7zXl4" - Freya (warm, expressive female voice)
    # Default: Freya - warm, expressive, natural-sounding female voice
    DEFAULT_VOICE_ID = "jsCqWAovK2LkecY7zXl4"

    # Model options:
    # - "eleven_flash_v2_5" - Fastest, lowest latency (can sound robotic)
    # - "eleven_turbo_v2_5" - Fast with better quality
    # - "eleven_multilingual_v2" - Highest quality, most natural
    # Using turbo for good balance of speed and quality
    DEFAULT_MODEL = "eleven_turbo_v2_5"

    # Voice settings for more natural speech
    # stability: Lower = more expressive/variable, Higher = more consistent
    # similarity_boost: How closely to match the original voice
    # style: Speaking style intensity (0-1)
    # use_speaker_boost: Enhances voice clarity
    DEFAULT_VOICE_SETTINGS = {
        "stability": 0.5,  # Balanced - not too robotic, not too variable
        "similarity_boost": 0.75,  # Good voice matching
        "style": 0.4,  # Moderate expressiveness
        "use_speaker_boost": True,  # Enhanced clarity
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        voice_id: Optional[str] = None,
        model: Optional[str] = None,
        voice_settings: Optional[dict] = None,
    ):
        """Initialize TTS engine with natural voice settings.

        Args:
            api_key: ElevenLabs API key. If None, loads from environment.
            voice_id: Voice ID to use. If None, uses default Freya voice.
            model: Model to use. If None, uses turbo model for balanced quality/speed.
            voice_settings: Voice settings dict with stability, similarity_boost, style, use_speaker_boost.
        """
        self.api_key = api_key or os.getenv("ELEVEN_LABS_API_KEY") or os.getenv("eleven-labs")
        if not self.api_key:
            raise ValueError(
                "ElevenLabs API key not found. Set ELEVEN_LABS_API_KEY in .env file."
            )

        self.voice_id = voice_id or self.DEFAULT_VOICE_ID
        self.model = model or self.DEFAULT_MODEL
        self.voice_settings = voice_settings or self.DEFAULT_VOICE_SETTINGS.copy()
        self._client = None
        self._is_speaking = False
        self._speak_lock = threading.Lock()

        logging.info(
            "TextToSpeech initialized with voice_id=%s, model=%s, settings=%s",
            self.voice_id, self.model, self.voice_settings
        )

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
        """Synchronously speak the text with natural voice settings."""
        with self._speak_lock:
            self._is_speaking = True
            try:
                from elevenlabs import VoiceSettings

                # Create voice settings for more natural speech
                settings = VoiceSettings(
                    stability=self.voice_settings.get("stability", 0.5),
                    similarity_boost=self.voice_settings.get("similarity_boost", 0.75),
                    style=self.voice_settings.get("style", 0.4),
                    use_speaker_boost=self.voice_settings.get("use_speaker_boost", True),
                )

                # Generate audio using ElevenLabs with voice settings
                audio_generator = self.client.text_to_speech.convert(
                    voice_id=self.voice_id,
                    text=text,
                    model_id=self.model,
                    output_format="mp3_44100_128",
                    voice_settings=settings,
                )

                # Collect audio bytes from generator
                audio_bytes = b"".join(audio_generator)

                # Play the audio
                self._play_audio(audio_bytes)

                logging.info("TTS spoke: %s", text[:50] + "..." if len(text) > 50 else text)
                return True

            except Exception as e:
                logging.error("TTS error: %s", str(e))
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

    def set_voice_settings(
        self,
        stability: Optional[float] = None,
        similarity_boost: Optional[float] = None,
        style: Optional[float] = None,
        use_speaker_boost: Optional[bool] = None,
    ) -> None:
        """Adjust voice settings for more natural speech.

        Args:
            stability: 0.0-1.0, lower = more expressive, higher = more consistent
            similarity_boost: 0.0-1.0, how closely to match original voice
            style: 0.0-1.0, speaking style intensity
            use_speaker_boost: Whether to enhance voice clarity
        """
        if stability is not None:
            self.voice_settings["stability"] = max(0.0, min(1.0, stability))
        if similarity_boost is not None:
            self.voice_settings["similarity_boost"] = max(0.0, min(1.0, similarity_boost))
        if style is not None:
            self.voice_settings["style"] = max(0.0, min(1.0, style))
        if use_speaker_boost is not None:
            self.voice_settings["use_speaker_boost"] = use_speaker_boost
        logging.info("TTS voice settings updated: %s", self.voice_settings)

    def use_preset(self, preset: str) -> None:
        """Apply a voice preset for different speaking styles.

        Args:
            preset: One of 'natural', 'calm', 'energetic', 'professional', 'friendly'
        """
        presets = {
            "natural": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.4,
                "use_speaker_boost": True,
            },
            "calm": {
                "stability": 0.7,
                "similarity_boost": 0.8,
                "style": 0.2,
                "use_speaker_boost": True,
            },
            "energetic": {
                "stability": 0.3,
                "similarity_boost": 0.7,
                "style": 0.7,
                "use_speaker_boost": True,
            },
            "professional": {
                "stability": 0.65,
                "similarity_boost": 0.85,
                "style": 0.3,
                "use_speaker_boost": True,
            },
            "friendly": {
                "stability": 0.45,
                "similarity_boost": 0.7,
                "style": 0.5,
                "use_speaker_boost": True,
            },
        }
        if preset in presets:
            self.voice_settings = presets[preset].copy()
            logging.info("TTS preset applied: %s -> %s", preset, self.voice_settings)
        else:
            logging.warning("Unknown TTS preset: %s. Available: %s", preset, list(presets.keys()))

    def set_model(self, model: str) -> None:
        """Change the TTS model.

        Args:
            model: One of 'eleven_flash_v2_5', 'eleven_turbo_v2_5', 'eleven_multilingual_v2'
        """
        valid_models = ["eleven_flash_v2_5", "eleven_turbo_v2_5", "eleven_multilingual_v2"]
        if model in valid_models:
            self.model = model
            logging.info("TTS model changed to: %s", model)
        else:
            logging.warning("Unknown TTS model: %s. Available: %s", model, valid_models)
