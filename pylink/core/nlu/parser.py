import re
from typing import Optional

from core.nlu.intents import Intent


def _extract_after_keyword(original: str, lowered: str, keyword: str) -> Optional[str]:
    index = lowered.find(keyword)
    if index == -1:
        return None
    return original[index + len(keyword):].strip()


def _extract_after_keywords(original: str, lowered: str, keywords: list[str]) -> Optional[str]:
    for keyword in keywords:
        extracted = _extract_after_keyword(original, lowered, keyword)
        if extracted:
            return extracted
    return None


def parse_intent(text: str, context=None) -> Intent:
    lowered = text.lower().strip()

    # Remove common filler words for more flexible parsing
    cleaned = re.sub(r'\b(can you|could you|please|the|a|an)\b', '', lowered).strip()

    # Confirmation intents
    if lowered in {"confirm", "yes", "y", "ok", "okay", "sure", "proceed"}:
        return Intent(name="confirm", confidence=1.0, raw_text=text)

    # Cancellation intents
    if lowered in {"cancel", "stop", "abort", "no", "n", "nevermind", "nope"}:
        return Intent(name="cancel", confidence=1.0, raw_text=text)

    # Open app - flexible matching
    open_keywords = ["open", "launch", "start", "run"]
    for keyword in open_keywords:
        if keyword in cleaned:
            # Extract app name after the keyword
            app = _extract_after_keyword(text, lowered, keyword)
            if app:
                # Clean up common suffixes
                app = re.sub(r'\s+(app|application)$', '', app.strip(), flags=re.IGNORECASE)
                return Intent(name="open_app", entities={"app": app}, confidence=0.9, raw_text=text)

    # Focus/switch app
    focus_patterns = [
        (r'(?:focus|switch to|go to)\s+(.+)', 0.85),
        (r'(?:switch|change)\s+to\s+(.+)', 0.85),
    ]
    for pattern, confidence in focus_patterns:
        match = re.search(pattern, lowered)
        if match:
            app = match.group(1).strip()
            app = re.sub(r'\s+(app|application)$', '', app, flags=re.IGNORECASE)
            return Intent(name="focus_app", entities={"app": app}, confidence=confidence, raw_text=text)

    # Type text - flexible matching
    type_keywords = ["type", "write", "enter"]
    for keyword in type_keywords:
        if keyword in cleaned:
            content = _extract_after_keyword(text, lowered, keyword)
            if content:
                # Remove trailing punctuation like colons
                content = re.sub(r'^:\s*', '', content)
                return Intent(name="type_text", entities={"content": content}, confidence=0.85, raw_text=text)

    # Click
    if "click" in cleaned:
        target = _extract_after_keyword(text, lowered, "click") or ""
        return Intent(name="click", entities={"target": target}, confidence=0.8, raw_text=text)

    # Reply to email - flexible matching
    if ("reply" in cleaned or "respond" in cleaned) and ("email" in cleaned or "mail" in cleaned or "message" in cleaned):
        content = _extract_after_keywords(text, lowered, ["saying", "that", "with", ":"])
        entities = {
            "target": "last_email" if "last" in lowered or "previous" in lowered else "email",
            "content": content or "",
        }
        return Intent(name="reply_email", entities=entities, confidence=0.8, raw_text=text)

    return Intent(name="unknown", entities={"text": text}, confidence=0.0, raw_text=text)
