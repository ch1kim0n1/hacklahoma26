"""LLM fallback parser for PixelLink intent extraction."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Optional

from dotenv import load_dotenv

from core.nlu.intents import Intent

load_dotenv()

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the intent parser for PixelLink.
Return ONLY JSON in this format:
{
  "intent": "<intent_name>",
  "entities": {"key": "value"},
  "confidence": 0.0
}

Supported intents:
open_app, focus_app, close_app, open_website, search_web, search_youtube,
open_file, type_text, click, right_click, double_click, scroll, press_key,
new_tab, close_tab, next_tab, previous_tab, refresh_page, navigate_back,
navigate_forward, copy, paste, cut, undo, redo, select_all,
volume_up, volume_down, mute, minimize_window, maximize_window,
reply_email, send_text, create_note, create_reminder, login,
search_file, confirm, cancel, unknown.

Rules:
- Keep entities minimal and precise.
- If unclear, return unknown with low confidence.
- Never output markdown.
"""


class _LRUTTLCache:
    def __init__(self, max_entries: int = 1000, ttl_seconds: int = 900) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._data: OrderedDict[str, tuple[float, Intent]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Intent | None:
        now = time.monotonic()
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            expires_at, intent = item
            if expires_at <= now:
                self._data.pop(key, None)
                return None
            self._data.move_to_end(key)
            return Intent(
                name=intent.name,
                entities=dict(intent.entities),
                confidence=float(intent.confidence),
                raw_text=intent.raw_text,
            )

    def set(self, key: str, value: Intent) -> None:
        now = time.monotonic()
        stored = Intent(
            name=value.name,
            entities=dict(value.entities),
            confidence=float(value.confidence),
            raw_text=value.raw_text,
        )
        with self._lock:
            self._data[key] = (now + self.ttl_seconds, stored)
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)


class GeminiBrain:
    """LLM-based natural language understanding using Gemini SDK."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI") or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("Gemini API key not found. Set GEMINI or GOOGLE_API_KEY.")

        try:
            import google.generativeai as genai
        except Exception as exc:  # pragma: no cover - import availability depends on env
            raise RuntimeError(
                "google-generativeai is unavailable. Install dependency 'google-generativeai'."
            ) from exc

        self._genai = genai
        self._genai.configure(api_key=self.api_key)
        self.model_id = os.getenv("PIXELINK_GEMINI_MODEL", "gemini-1.5-flash")
        self._model = genai.GenerativeModel(
            model_name=self.model_id,
            system_instruction=SYSTEM_PROMPT,
        )
        logger.info("Gemini brain initialized with model=%s", self.model_id)

    def parse(self, text: str, context: Optional[dict] = None) -> Intent:
        if not text or not text.strip():
            return Intent(name="unknown", entities={"text": ""}, confidence=0.0, raw_text="")

        prompt = f'User input: "{text}"\nReturn JSON only.'
        if context and context.get("last_intent"):
            prompt = f"Previous intent: {context['last_intent']}\n{prompt}"

        try:
            response = self._model.generate_content(
                prompt,
                generation_config=self._genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=256,
                ),
            )
            response_text = (response.text or "").strip()
            if response_text.startswith("```"):
                lines = response_text.splitlines()
                if len(lines) >= 3:
                    response_text = "\n".join(lines[1:-1]).strip()

            data = json.loads(response_text)
            intent_name = str(data.get("intent", "unknown"))
            entities = data.get("entities", {})
            confidence = float(data.get("confidence", 0.5))
            if not isinstance(entities, dict):
                entities = {}
            return Intent(name=intent_name, entities=entities, confidence=confidence, raw_text=text)
        except Exception as exc:
            logger.info("Gemini parse failed: %s", exc)
            return Intent(name="unknown", entities={"text": text}, confidence=0.0, raw_text=text)


_executor = ThreadPoolExecutor(max_workers=2)
_cache = _LRUTTLCache(max_entries=1000, ttl_seconds=900)
_brain: GeminiBrain | None = None
_brain_lock = threading.Lock()


def get_brain() -> GeminiBrain:
    global _brain
    with _brain_lock:
        if _brain is None:
            _brain = GeminiBrain()
    return _brain


def parse_with_llm(
    text: str,
    context: Optional[dict] = None,
    *,
    timeout_ms: int = 450,
) -> Intent:
    """Parse user input using LLM with strict timeout and LRU+TTL caching.

    Returns unknown intent on timeout/failure (fail-closed behavior).
    """
    normalized = " ".join((text or "").strip().split()).lower()
    cache_key = f"{normalized}|{(context or {}).get('last_intent', '')}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        brain = get_brain()
    except Exception as exc:
        logger.info("LLM unavailable: %s", exc)
        return Intent(name="unknown", entities={"text": text}, confidence=0.0, raw_text=text)

    future = _executor.submit(brain.parse, text, context)
    try:
        result = future.result(timeout=max(0.001, timeout_ms / 1000.0))
    except FutureTimeoutError:
        future.cancel()
        logger.info("LLM parse timed out after %sms", timeout_ms)
        return Intent(name="unknown", entities={"text": text}, confidence=0.0, raw_text=text)
    except Exception as exc:
        logger.info("LLM parse error: %s", exc)
        return Intent(name="unknown", entities={"text": text}, confidence=0.0, raw_text=text)

    _cache.set(cache_key, result)
    return result
