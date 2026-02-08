"""Speech-to-Text module using Whisper ONNX (faster-whisper)."""

from __future__ import annotations

import io
import logging
import os
import struct
import math
import threading
import wave
import tempfile
from typing import Optional, Callable

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class SpeechToText:
    """Speech-to-Text engine using Whisper via faster-whisper (ONNX/CTranslate2)."""

    # Audio recording settings
    SAMPLE_RATE = 16000
    CHANNELS = 1
    CHUNK_SIZE = 1024
    FORMAT_BITS = 16

    # Whisper model options: "tiny", "base", "small", "medium", "large-v3"
    # Smaller = faster, larger = more accurate
    DEFAULT_MODEL = "base"

    def __init__(
        self,
        model_size: Optional[str] = None,
        silence_threshold: float = 1.0,
        max_duration: float = 30.0,
        device: str = "auto",
        compute_type: str = "int8",
    ):
        """Initialize STT engine.

        Args:
            model_size: Whisper model size. Options: tiny, base, small, medium, large-v3.
            silence_threshold: Seconds of silence to stop recording.
            max_duration: Maximum recording duration in seconds.
            device: Device to use ("cpu", "cuda", or "auto").
            compute_type: Computation type ("int8", "float16", "float32").
        """
        self.model_size = model_size or self.DEFAULT_MODEL
        self.silence_threshold = silence_threshold
        self.max_duration = max_duration
        self.device = device
        self.compute_type = compute_type

        self._model = None
        self._is_listening = False
        self._stop_listening = False
        self._listen_lock = threading.Lock()
        self._pyaudio = None

        logging.info(
            "SpeechToText initialized with model=%s, device=%s",
            self.model_size,
            self.device,
        )

    @property
    def model(self):
        """Lazy-load Whisper model."""
        if self._model is None:
            from faster_whisper import WhisperModel

            # Use CPU with int8 for efficiency, or CUDA if available
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
            )
            logging.info("Whisper model loaded: %s", self.model_size)
        return self._model

    def _get_pyaudio(self):
        """Lazy-load PyAudio instance."""
        if self._pyaudio is None:
            import pyaudio

            self._pyaudio = pyaudio.PyAudio()
        return self._pyaudio

    def listen(self, prompt_callback: Optional[Callable[[str], None]] = None) -> str:
        """Listen for speech and transcribe it.

        Args:
            prompt_callback: Optional callback to signal listening state.
                Called with "listening" when ready, "processing" when transcribing.

        Returns:
            Transcribed text, or empty string if nothing detected.
        """
        with self._listen_lock:
            self._is_listening = True
            self._stop_listening = False

            try:
                if prompt_callback:
                    prompt_callback("listening")

                # Record audio
                audio_data = self._record_audio()

                if not audio_data or len(audio_data) < 1000:
                    logging.info("No audio detected or too short")
                    return ""

                if prompt_callback:
                    prompt_callback("processing")

                # Transcribe using Whisper
                text = self._transcribe(audio_data)

                if text:
                    logging.info(
                        "STT transcribed: %s",
                        text[:50] + "..." if len(text) > 50 else text,
                    )
                return text

            except Exception as e:
                logging.error("STT error: %s", str(e))
                print(f"[STT Error: {e}]")
                return ""
            finally:
                self._is_listening = False

    def _record_audio(self) -> bytes:
        """Record audio from microphone until silence or max duration."""
        import pyaudio

        pa = self._get_pyaudio()

        stream = pa.open(
            format=pyaudio.paInt16,
            channels=self.CHANNELS,
            rate=self.SAMPLE_RATE,
            input=True,
            frames_per_buffer=self.CHUNK_SIZE,
        )

        frames = []
        silent_chunks = 0
        max_silent_chunks = int(
            self.silence_threshold * self.SAMPLE_RATE / self.CHUNK_SIZE
        )
        max_chunks = int(self.max_duration * self.SAMPLE_RATE / self.CHUNK_SIZE)
        energy_threshold = 500  # Adjust based on environment

        # Wait for voice activity to start
        voice_started = False
        startup_chunks = 0
        max_startup_wait = int(
            10 * self.SAMPLE_RATE / self.CHUNK_SIZE
        )  # 10 seconds max wait

        try:
            for _ in range(max_chunks + max_startup_wait):
                if self._stop_listening:
                    break

                data = stream.read(self.CHUNK_SIZE, exception_on_overflow=False)

                # Calculate RMS energy
                shorts = struct.unpack(f"{len(data)//2}h", data)
                rms = (
                    math.sqrt(sum(s * s for s in shorts) / len(shorts)) if shorts else 0
                )

                if not voice_started:
                    startup_chunks += 1
                    if rms > energy_threshold:
                        voice_started = True
                        frames.append(data)
                    elif startup_chunks >= max_startup_wait:
                        # Timeout waiting for voice
                        break
                else:
                    frames.append(data)

                    if rms < energy_threshold:
                        silent_chunks += 1
                        if silent_chunks >= max_silent_chunks:
                            # Silence detected, stop recording
                            break
                    else:
                        silent_chunks = 0

                    if len(frames) >= max_chunks:
                        break

        finally:
            stream.stop_stream()
            stream.close()

        if not frames:
            return b""

        # Convert to WAV format
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(b"".join(frames))

        return wav_buffer.getvalue()

    def _transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio using Whisper."""
        # Write audio to temp file (faster-whisper needs a file path)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_data)
            temp_path = f.name

        try:
            # Transcribe with Whisper
            segments, info = self.model.transcribe(
                temp_path,
                language="en",
                beam_size=5,
                vad_filter=True,  # Filter out non-speech
            )

            # Collect all transcribed text
            text_parts = []
            for segment in segments:
                text_parts.append(segment.text.strip())

            return " ".join(text_parts).strip()

        finally:
            # Clean up temp file
            os.unlink(temp_path)

    def listen_continuous(
        self,
        callback: Callable[[str], None],
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        """Continuously listen and call callback with transcribed text.

        Args:
            callback: Function to call with each transcribed text.
            stop_event: Threading event to signal stop. If None, runs until stop() is called.
        """
        while not (stop_event and stop_event.is_set()) and not self._stop_listening:
            text = self.listen()
            if text:
                callback(text)

    def stop(self) -> None:
        """Stop listening."""
        self._stop_listening = True

    @property
    def is_listening(self) -> bool:
        """Check if currently listening."""
        return self._is_listening

    def cleanup(self) -> None:
        """Clean up resources."""
        if self._pyaudio is not None:
            self._pyaudio.terminate()
            self._pyaudio = None
