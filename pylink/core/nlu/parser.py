"""
Intent parser for PixelLink.
Uses Gemini LLM as the brain for natural language understanding.
"""

import logging
from typing import Optional

from core.nlu.intents import Intent

logger = logging.getLogger(__name__)

# Flag to control whether to use LLM or fallback to regex
USE_LLM = True


def parse_intent(text: str, context=None) -> Intent:
    """Parse user input and return an Intent.

    Uses Gemini LLM for intelligent natural language understanding.

    Args:
        text: The user's spoken/typed input.
        context: Optional context about the session.

    Returns:
        Intent object with parsed intent and entities.
    """
    if not text or not text.strip():
        return Intent(name="unknown", entities={"text": ""}, confidence=0.0, raw_text="")

    if USE_LLM:
        try:
            from core.nlu.llm_brain import parse_with_llm

            # Convert context to dict if it has relevant info
            context_dict = None
            if context and hasattr(context, "last_intent"):
                context_dict = {"last_intent": context.last_intent}

            result = parse_with_llm(text, context_dict)

            # If LLM returned a valid result, use it
            # Otherwise fall back to regex (confidence 0 means LLM failed)
            if result.confidence > 0:
                return result
            else:
                logger.warning("LLM returned low confidence, falling back to regex")
        except ImportError as e:
            logger.warning(f"LLM brain not available, falling back to regex: {e}")
        except Exception as e:
            logger.error(f"LLM parsing failed, falling back to regex: {e}")

    # Fallback to simple regex parsing (legacy)
    return _parse_with_regex(text)


def _parse_with_regex(text: str) -> Intent:
    """Fallback regex-based parser (legacy).

    Only used if LLM is unavailable.
    """
    import re

    lowered = text.lower().strip()
    words = set(re.findall(r"\b\w+\b", lowered))

    # Open app - check this first to avoid false matches
    match = re.search(r"(?:open|launch|start)\s+(.+)", lowered)
    if match:
        app = re.sub(r"[?.!,;:]+$", "", match.group(1)).strip()
        return Intent(name="open_app", entities={"app": app}, confidence=0.7, raw_text=text)

    # Type text
    match = re.search(r"(?:type|write|enter)\s+(.+)", lowered)
    if match:
        return Intent(name="type_text", entities={"content": match.group(1)}, confidence=0.7, raw_text=text)

    # Simple keyword matching - use word boundaries to avoid partial matches
    exit_words = {"bye", "goodbye", "exit", "quit"}
    if words & exit_words:
        return Intent(name="exit", confidence=0.8, raw_text=text)

    confirm_words = {"yes", "confirm", "ok", "okay", "sure"}
    if words & confirm_words:
        return Intent(name="confirm", confidence=0.8, raw_text=text)

    cancel_words = {"no", "cancel", "stop", "nevermind"}
    if words & cancel_words and not (words & {"notes", "note"}):
        return Intent(name="cancel", confidence=0.8, raw_text=text)

    return Intent(name="unknown", entities={"text": text}, confidence=0.0, raw_text=text)
