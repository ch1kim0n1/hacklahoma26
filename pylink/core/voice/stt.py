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
import time
from pathlib import Path
from typing import Any, Optional, Callable

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
    MODEL_REPOS = {
        "tiny": "Systran/faster-whisper-tiny",
        "base": "Systran/faster-whisper-base",
        "small": "Systran/faster-whisper-small",
        "medium": "Systran/faster-whisper-medium",
        "large-v1": "Systran/faster-whisper-large-v1",
        "large-v2": "Systran/faster-whisper-large-v2",
        "large-v3": "Systran/faster-whisper-large-v3",
    }

    def __init__(
        self,
        model_size: Optional[str] = None,
        silence_threshold: float = 2.0,
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
        self._model_lock = threading.Lock()
        self._status_lock = threading.Lock()
        self._pyaudio = None
        self.last_error: Optional[str] = None
        self.cache_root = Path(
            os.getenv(
                "PIXELINK_WHISPER_CACHE_DIR",
                str(Path.home() / ".cache" / "pixelink" / "whisper"),
            )
        ).expanduser()
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self._model_status: dict[str, Any] = {
            "model": self.model_size,
            "state": "idle",
            "stage": "idle",
            "message": "Whisper model is idle.",
            "progress": 0,
            "cached": None,
            "error": "",
            "updated_at": time.time(),
        }

        logging.info(
            "SpeechToText initialized with model=%s, device=%s",
            self.model_size,
            self.device,
        )

    @property
    def model(self):
        """Lazy-load Whisper model."""
        if self._model is None and not self.ensure_model_loaded():
            raise RuntimeError("Failed to load Whisper model")
        return self._model

    @property
    def model_status(self) -> dict[str, Any]:
        """Current model loading/downloading status."""
        with self._status_lock:
            return dict(self._model_status)

    def _set_model_status(self, **updates: Any) -> dict[str, Any]:
        with self._status_lock:
            self._model_status.update(updates)
            self._model_status["updated_at"] = time.time()
            return dict(self._model_status)

    def _notify_model_status(
        self, callback: Optional[Callable[[dict[str, Any]], None]]
    ) -> None:
        if not callback:
            return
        try:
            callback(self.model_status)
        except Exception:
            # Status callbacks should never break model loading.
            pass

    def _resolve_model_reference(
        self, progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
    ) -> tuple[str, Optional[bool]]:
        """Resolve a local model reference, downloading if needed.

        Returns:
            Tuple of (model_reference, cached_flag).
            cached_flag is True/False for known repository models, None otherwise.
        """
        repo_id = self.MODEL_REPOS.get(self.model_size)
        if not repo_id:
            return self.model_size, None

        try:
            from huggingface_hub import snapshot_download
            from tqdm.auto import tqdm as base_tqdm
        except Exception:
            # Fall back to faster-whisper's internal downloader.
            return self.model_size, None

        cache_dir = str(self.cache_root)
        try:
            model_path = snapshot_download(
                repo_id=repo_id,
                cache_dir=cache_dir,
                local_files_only=True,
            )
            self._set_model_status(
                state="loading",
                stage="cache_hit",
                message=f"Using cached Whisper model '{self.model_size}'.",
                progress=100,
                cached=True,
                error="",
            )
            self._notify_model_status(progress_callback)
            return model_path, True
        except Exception:
            pass

        self._set_model_status(
            state="loading",
            stage="downloading",
            message=f"Downloading Whisper model '{self.model_size}' (first run can take a minute).",
            progress=0,
            cached=False,
            error="",
        )
        self._notify_model_status(progress_callback)

        outer = self

        class DownloadProgressTqdm(base_tqdm):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._last_percent = -1
                self._emit(force=True)

            def update(self, n=1):
                result = super().update(n)
                self._emit()
                return result

            def close(self):
                self._emit(force=True)
                return super().close()

            def _emit(self, force: bool = False):
                percent: Optional[int] = None
                if self.total:
                    percent = max(0, min(100, int((self.n / self.total) * 100)))
                if not force and percent == self._last_percent:
                    return
                self._last_percent = percent
                outer._set_model_status(
                    state="loading",
                    stage="downloading",
                    message=f"Downloading Whisper model '{outer.model_size}'...",
                    progress=percent if percent is not None else 0,
                    cached=False,
                    error="",
                )
                outer._notify_model_status(progress_callback)

        model_path = snapshot_download(
            repo_id=repo_id,
            cache_dir=cache_dir,
            local_files_only=False,
            tqdm_class=DownloadProgressTqdm,
        )
        return model_path, False

    def ensure_model_loaded(
        self, progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
    ) -> bool:
        """Ensure Whisper model is loaded and ready for transcription."""
        if self._model is not None:
            self._set_model_status(
                state="ready",
                stage="ready",
                message=f"Whisper model '{self.model_size}' is ready.",
                progress=100,
                error="",
            )
            self._notify_model_status(progress_callback)
            return True

        with self._model_lock:
            if self._model is not None:
                self._set_model_status(
                    state="ready",
                    stage="ready",
                    message=f"Whisper model '{self.model_size}' is ready.",
                    progress=100,
                    error="",
                )
                self._notify_model_status(progress_callback)
                return True

            self._set_model_status(
                state="loading",
                stage="checking_cache",
                message=f"Checking cache for Whisper model '{self.model_size}'...",
                progress=5,
                error="",
            )
            self._notify_model_status(progress_callback)

            try:
                model_reference, cached = self._resolve_model_reference(progress_callback)

                from faster_whisper import WhisperModel

                self._set_model_status(
                    state="loading",
                    stage="loading_model",
                    message=f"Loading Whisper model '{self.model_size}' into memory...",
                    progress=95,
                    cached=cached,
                    error="",
                )
                self._notify_model_status(progress_callback)

                self._model = WhisperModel(
                    model_reference,
                    device=self.device,
                    compute_type=self.compute_type,
                    download_root=str(self.cache_root),
                )
                self._set_model_status(
                    state="ready",
                    stage="ready",
                    message=f"Whisper model '{self.model_size}' is ready.",
                    progress=100,
                    cached=cached,
                    error="",
                )
                self._notify_model_status(progress_callback)
                logging.info("Whisper model loaded: %s", self.model_size)
                return True
            except Exception as exc:
                self.last_error = f"{type(exc).__name__}: {exc}"
                self._set_model_status(
                    state="error",
                    stage="failed",
                    message=f"Failed to load Whisper model '{self.model_size}'.",
                    progress=0,
                    error=self.last_error,
                )
                self._notify_model_status(progress_callback)
                logging.exception("Failed to load Whisper model")
                return False

    def warm_up(
        self, progress_callback: Optional[Callable[[dict[str, Any]], None]] = None
    ) -> bool:
        """Warm up STT model ahead of first voice command."""
        return self.ensure_model_loaded(progress_callback=progress_callback)

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
            self.last_error = None

            try:
                if not self.ensure_model_loaded():
                    return ""

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
                self.last_error = f"{type(e).__name__}: {e}"
                logging.info("STT error: %s", str(e))
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
            segments, _info = self.model.transcribe(
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
