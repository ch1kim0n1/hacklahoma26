import re
import logging

from core.nlu.intents import Intent

logger = logging.getLogger(__name__)

WEBSITE_ALIASES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "linkedin": "https://www.linkedin.com",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "reddit": "https://www.reddit.com",
    "notion": "https://www.notion.so",
    "slack": "https://app.slack.com",
}

MESSAGING_APP_PATTERNS = [
    r"(?:i\s*message|imessage|imeesage|imesage)",
    r"messages?",
    r"sms",
    r"texts?",
]


def _extract_after_keyword(original: str, lowered: str, keyword: str) -> str | None:
    index = lowered.find(keyword)
    if index == -1:
        return None
    return original[index + len(keyword):].strip()


def _extract_after_keywords(original: str, lowered: str, keywords: list[str]) -> str | None:
    for keyword in keywords:
        extracted = _extract_after_keyword(original, lowered, keyword)
        if extracted:
            return extracted
    return None

def _normalized_domain_url(raw: str) -> str | None:
    match = re.search(r"([a-z0-9-]+\.(?:com|org|net|io|ai|dev|app|edu)(?:/[^\s]*)?)", raw.lower())
    if not match:
        return None
    domain = match.group(1)
    if domain.startswith("http://") or domain.startswith("https://"):
        return domain
    return f"https://{domain}"


def _extract_website_url(original: str, lowered: str) -> str | None:
    domain_url = _normalized_domain_url(original)
    if domain_url:
        return domain_url

    for name, url in WEBSITE_ALIASES.items():
        if re.search(rf"\b{name}\b", lowered):
            return url

    return None


def _extract_target(lowered: str) -> str | None:
    match = re.search(r"\bto\s+([a-z0-9 ._\-']+?)(?=\s+(?:saying|that|message|text|with)\b|$)", lowered)
    if not match:
        return None
    return match.group(1).strip()


def _extract_message_content(original: str, lowered: str) -> str | None:
    content = _extract_after_keywords(
        original,
        lowered,
        [" saying ", " that ", " with message ", " with text ", ":"],
    )
    if content:
        return content.strip()
    return None


def _strip_wrapping_quotes(value: str) -> str:
    return value.strip().strip('"\'' + "“”").strip()


def _extract_messaging_app(original: str) -> str | None:
    lowered = original.lower()
    for pattern in MESSAGING_APP_PATTERNS:
        if re.search(rf"\b(?:in|on|via)\s+{pattern}\b", lowered):
            return "Messages"
    return None


def _remove_messaging_app_phrase(original: str) -> str:
    cleaned = original
    for pattern in MESSAGING_APP_PATTERNS:
        cleaned = re.sub(rf"\b(?:in|on|via)\s+{pattern}\b", "", cleaned, flags=re.IGNORECASE)
    return " ".join(cleaned.split())


def _clean_target_value(value: str) -> str:
    cleaned = re.sub(r"^\s*to\s+", "", value.strip(), flags=re.IGNORECASE)
    cleaned = _remove_messaging_app_phrase(cleaned)
    cleaned = _strip_wrapping_quotes(cleaned)
    return cleaned


def _parse_send_text(original: str, lowered: str) -> Intent | None:
    if "email" in lowered or "mail" in lowered:
        return None

    is_text_command = bool(re.search(r"\b(send text|send message|send sms|text|message)\b", lowered))
    if not is_text_command:
        return None

    app_name = _extract_messaging_app(original)
    working_original = _remove_messaging_app_phrase(original)
    working_lowered = working_original.lower()

    content = None
    target = None

    quoted_content_match = re.search(
        r"(?:saying|that|with message|with text|message)\s+[\"“](.+?)[\"”]\s*$",
        working_original,
        flags=re.IGNORECASE,
    )
    if quoted_content_match:
        content = _strip_wrapping_quotes(quoted_content_match.group(1))
        target_prefix = working_original[:quoted_content_match.start()].strip()
    else:
        marker_match = re.search(r"\b(?:saying|that|with message|with text)\b", working_lowered)
        if marker_match:
            content = _strip_wrapping_quotes(working_original[marker_match.end():])
            target_prefix = working_original[:marker_match.start()].strip()
        else:
            target_prefix = working_original

    target_to_match = re.search(
        r"\bto\s+([a-z0-9 ._\-']+?)(?=\s*$)",
        target_prefix.lower(),
        flags=re.IGNORECASE,
    )
    if target_to_match:
        target = _clean_target_value(target_to_match.group(1))
    else:
        command_prefix_removed = re.sub(
            r"^\s*(?:send\s+)?(?:a\s+)?(?:text|message|sms)\s+",
            "",
            target_prefix,
            flags=re.IGNORECASE,
        )
        command_prefix_removed = command_prefix_removed.strip()
        if content and command_prefix_removed:
            target = _clean_target_value(command_prefix_removed)

    if not content:
        content = _extract_message_content(working_original, working_lowered)
        if content:
            content = _strip_wrapping_quotes(content)

    if target:
        target = _clean_target_value(target)
    if content:
        content = _strip_wrapping_quotes(content)

    # Pattern: "text john hi there"
    if not target and not content:
        trailing = re.sub(
            r"^\s*(?:send\s+)?(?:a\s+)?(?:text|message|sms)\s+",
            "",
            working_original,
            flags=re.IGNORECASE,
        ).strip()
        trailing_word_count = len(trailing.split())
        if trailing_word_count >= 3:
            words = trailing.split()
            target = _clean_target_value(words[0])
            content = _strip_wrapping_quotes(" ".join(words[1:]))
        elif trailing:
            content = _strip_wrapping_quotes(trailing)

    if content and not target:
        entities = {
            "target": "",
            "content": content,
            "requires_clarification": True,
            "clarification_prompt": "Who should receive this text message?",
            "clarification_type": "send_text_target",
        }
        if app_name:
            entities["app"] = app_name
        return Intent(
            name="send_text",
            entities=entities,
            confidence=0.72,
            raw_text=original,
        )

    if target and not content:
        entities = {
            "target": target,
            "content": "",
            "requires_clarification": True,
            "clarification_prompt": f"What message should I send to {target}?",
            "clarification_type": "send_text_content",
        }
        if app_name:
            entities["app"] = app_name
        return Intent(
            name="send_text",
            entities=entities,
            confidence=0.72,
            raw_text=original,
        )

    if target and content:
        entities = {"target": target, "content": content}
        if app_name:
            entities["app"] = app_name
        return Intent(
            name="send_text",
            entities=entities,
            confidence=0.84,
            raw_text=original,
        )

    return None


def parse_intent(text: str, context=None) -> Intent:
    """Parse intent using the LLM. Delegates to parse_with_llm for AI-only parsing."""
    try:
        from core.nlu.llm_brain import parse_with_llm

        ctx = {}
        if context and hasattr(context, "history") and context.history:
            ctx["last_intent"] = context.history[-1].get("intent")
        return parse_with_llm(text, ctx if ctx else None)
    except Exception:
        return Intent(name="unknown", entities={"text": text}, confidence=0.0, raw_text=text)


def _parse_intent_regex(text: str, context=None) -> Intent:
    """Legacy regex-based parser - kept for reference/testing. Use parse_intent (LLM) instead."""
    lowered = text.lower().strip()
    cleaned = re.sub(r"\b(can you|could you|please|the|a|an|for me)\b", "", lowered).strip()

    if lowered in {"confirm", "yes", "y", "ok", "okay", "sure", "proceed", "go ahead", "do it"}:
        return Intent(name="confirm", confidence=1.0, raw_text=text)

    if lowered in {"cancel", "stop", "abort", "no", "n", "nevermind", "nope", "never mind"}:
        return Intent(name="cancel", confidence=1.0, raw_text=text)

    # File search - check early before general search patterns
    if re.search(r"\b(find file|search file|locate file|find document|search for file|search document)\b", cleaned):
        query = _extract_after_keywords(
            text, lowered,
            ["find file ", "search file ", "locate file ", "find document ", "search for file ", "search document "]
        )
        if query:
            return Intent(
                name="search_file",
                entities={"query": query},
                confidence=0.85,
                raw_text=text,
            )

    # Login intent - autofill passwords
    if re.search(r"\b(login|log in|sign in|signin|authenticate)\b", cleaned):
        # Extract service/website name
        service = None
        
        # Try "login to <service>"
        service = _extract_after_keywords(
            text, lowered,
            ["login to ", "log in to ", "sign in to ", "signin to ", "authenticate to ",
             "login on ", "log in on ", "sign in on "]
        )
        
        if not service:
            # Try "<service> login"
            match = re.search(r"(\w+)\s+(?:login|log in|sign in)", cleaned)
            if match:
                service = match.group(1)
        
        if service:
            return Intent(
                name="login",
                entities={"service": service.strip()},
                confidence=0.87,
                raw_text=text,
            )

    if re.search(r"\b(search youtube for|find on youtube|look up on youtube)\b", cleaned):
        query = _extract_after_keywords(text, lowered, ["search youtube for ", "find on youtube ", "look up on youtube "])
        if query:
            return Intent(
                name="search_youtube",
                entities={"query": query},
                confidence=0.9,
                raw_text=text,
            )

    # Enhanced web search patterns
    if re.search(r"\b(search|browse|find|look up|google|search for|browse for|find on internet|search internet|search online|look online)\b", cleaned):
        # Extract query with more patterns
        query = _extract_after_keywords(
            text,
            lowered,
            ["search web for ", "search for ", "look up ", "find online ", "google for ", "google ",
             "browse for ", "find on internet ", "search internet for ", "search online for ",
             "look online for ", "browse ", "search ", "find "],
        )
        if query and "youtube" not in query.lower():
            return Intent(name="search_web", entities={"query": query}, confidence=0.86, raw_text=text)

    if re.search(r"\b(open|visit|go to|launch|load)\b", cleaned) and re.search(
        r"\b(browser|website|web|youtube|google|github|reddit|linkedin|gmail)\b", cleaned
    ):
        url = _extract_website_url(text, lowered)
        if url:
            return Intent(name="open_website", entities={"url": url}, confidence=0.92, raw_text=text)

    if re.search(r"\b(open file|open document)\b", cleaned):
        file_path = _extract_after_keywords(text, lowered, ["open file ", "open document "])
        if file_path:
            return Intent(name="open_file", entities={"path": file_path.strip()}, confidence=0.8, raw_text=text)

    send_text_intent = _parse_send_text(text, lowered)
    if send_text_intent:
        return send_text_intent

    if re.search(r"\b(reply|respond|answer)\b", cleaned) and re.search(r"\b(email|mail|message)\b", cleaned):
        content = _extract_after_keywords(text, lowered, ["saying ", "that ", "with ", ":"])
        entities = {
            "target": "last_email" if "last" in lowered or "previous" in lowered else "email",
            "content": content or "",
        }
        return Intent(name="reply_email", entities=entities, confidence=0.82, raw_text=text)

    # Open/focus app - flexible triggers for casual speech ("open Safari", "get into Safari", "show me Notes")
    _OPEN_KEYWORDS = [
        "open ", "launch ", "start ", "run ", "fire up ", "boot ", "open up ",
        "get into ", "get me ", "show me ", "take me to ", "let me see ",
        "bring up ", "need to open ", "want to open ", "wanna open ",
        "need to launch ", "want to launch ", "need ", "want ", "wanna ",
    ]
    app = _extract_after_keywords(text, lowered, _OPEN_KEYWORDS)
    if app:
        # Strip trailing "app/application" and filter out non-app extractions
        app = re.sub(r"\s+(app|application)$", "", app.strip(), flags=re.IGNORECASE)
        # Skip if it looks like a sentence, not an app name (e.g. "to send an email")
        if app and not re.match(r"^(to|the|a|an)\s+", app, flags=re.IGNORECASE) and len(app.split()) <= 3:
            if re.search(r"\b(open|launch|start|run|fire up|boot|get into|show me|take me to|need|want|wanna)\b", cleaned):
                return Intent(name="open_app", entities={"app": app}, confidence=0.88, raw_text=text)

    if re.search(r"\b(focus|switch to|go to|bring up|activate)\b", cleaned):
        app = _extract_after_keywords(text, lowered, ["focus ", "switch to ", "go to ", "bring up ", "activate "])
        if app:
            app = re.sub(r"\s+(app|application)$", "", app.strip(), flags=re.IGNORECASE)
            return Intent(name="focus_app", entities={"app": app}, confidence=0.86, raw_text=text)

    if re.search(r"\b(close app|quit app|exit app|close application|quit)\b", cleaned):
        app = _extract_after_keywords(text, lowered, ["close app ", "quit app ", "exit app ", "close application ", "quit "])
        return Intent(name="close_app", entities={"app": (app or "").strip()}, confidence=0.84, raw_text=text)

    # Note creation - check before type_text to avoid conflicts
    if re.search(r"\b(create|add|make|write)\b", cleaned) and re.search(r"\b(note|notes)\b", cleaned):
        # Extract note title
        title_match = re.search(r"(?:note|notes)\s+(?:called|named|titled)?\s*([^,]+?)(?=\s+(?:in|to|with|saying)|$)", cleaned)
        if title_match:
            title = title_match.group(1).strip()
        else:
            title = _extract_after_keywords(text, lowered, ["note ", "notes "])
        
        # Extract folder name
        folder_match = re.search(r"(?:in|to)\s+(?:folder\s+)?([a-z0-9 ]+?)(?:\s+folder)?(?=\s+(?:called|named|with|saying)|$)", cleaned)
        folder_name = folder_match.group(1).strip() if folder_match else "Notes"
        
        # Extract body
        body = ""
        body_match = re.search(r"(?:saying|that|with|body)\s+(.+?)$", lowered)
        if body_match:
            body = body_match.group(1).strip()
        
        return Intent(
            name="create_note",
            entities={"title": title or "", "folder_name": folder_name, "body": body},
            confidence=0.88,
            raw_text=text,
        )

    if re.search(r"\b(type|write|enter|input|dictate)\b", cleaned):
        content = _extract_after_keywords(text, lowered, ["type ", "write ", "enter ", "input ", "dictate "])
        if content:
            content = re.sub(r"^:\s*", "", content)
            return Intent(name="type_text", entities={"content": content}, confidence=0.84, raw_text=text)

    if re.search(r"\b(double click|double tap)\b", cleaned):
        return Intent(name="double_click", confidence=0.84, raw_text=text)

    if re.search(r"\b(right click|secondary click)\b", cleaned):
        return Intent(name="right_click", confidence=0.84, raw_text=text)

    if re.search(r"\b(click|tap|press here)\b", cleaned):
        target = _extract_after_keywords(text, lowered, ["click ", "tap ", "press here "]) or ""
        return Intent(name="click", entities={"target": target}, confidence=0.8, raw_text=text)

    if re.search(r"\b(scroll up|scroll down|page up|page down)\b", cleaned):
        direction = "up" if re.search(r"\b(scroll up|page up)\b", cleaned) else "down"
        amount_match = re.search(r"\b(\d+)\b", cleaned)
        amount = int(amount_match.group(1)) if amount_match else 450
        return Intent(name="scroll", entities={"direction": direction, "amount": amount}, confidence=0.9, raw_text=text)

    if re.search(r"\b(new tab|open tab)\b", cleaned):
        return Intent(name="new_tab", confidence=0.9, raw_text=text)

    if re.search(r"\b(close tab|remove tab)\b", cleaned):
        return Intent(name="close_tab", confidence=0.9, raw_text=text)

    if re.search(r"\b(next tab|tab right)\b", cleaned):
        return Intent(name="next_tab", confidence=0.88, raw_text=text)

    if re.search(r"\b(previous tab|prev tab|tab left)\b", cleaned):
        return Intent(name="previous_tab", confidence=0.88, raw_text=text)

    if re.search(r"\b(refresh|reload page)\b", cleaned):
        return Intent(name="refresh_page", confidence=0.9, raw_text=text)

    if re.search(r"\b(go back|navigate back|back page)\b", cleaned):
        return Intent(name="navigate_back", confidence=0.86, raw_text=text)

    if re.search(r"\b(go forward|navigate forward|forward page)\b", cleaned):
        return Intent(name="navigate_forward", confidence=0.86, raw_text=text)

    if re.search(r"\b(copy|copy this)\b", cleaned):
        return Intent(name="copy", confidence=0.9, raw_text=text)
    if re.search(r"\b(paste|insert clipboard)\b", cleaned):
        return Intent(name="paste", confidence=0.9, raw_text=text)
    if re.search(r"\b(cut|cut this)\b", cleaned):
        return Intent(name="cut", confidence=0.9, raw_text=text)
    if re.search(r"\b(undo|go undo)\b", cleaned):
        return Intent(name="undo", confidence=0.9, raw_text=text)
    if re.search(r"\b(redo|do again)\b", cleaned):
        return Intent(name="redo", confidence=0.9, raw_text=text)
    if re.search(r"\b(select all|highlight all)\b", cleaned):
        return Intent(name="select_all", confidence=0.9, raw_text=text)

    if re.search(r"\b(volume up|increase volume|louder)\b", cleaned):
        return Intent(name="volume_up", confidence=0.84, raw_text=text)
    if re.search(r"\b(volume down|decrease volume|quieter)\b", cleaned):
        return Intent(name="volume_down", confidence=0.84, raw_text=text)
    if re.search(r"\b(mute|silence)\b", cleaned):
        return Intent(name="mute", confidence=0.84, raw_text=text)

    press_match = re.search(r"\b(press|hit)\s+([a-z0-9_-]+)\b", cleaned)
    if press_match:
        return Intent(name="press_key", entities={"key": press_match.group(2)}, confidence=0.82, raw_text=text)

    if re.search(r"\b(minimize window|minimize)\b", cleaned):
        return Intent(name="minimize_window", confidence=0.8, raw_text=text)
    if re.search(r"\b(maximize window|maximize)\b", cleaned):
        return Intent(name="maximize_window", confidence=0.8, raw_text=text)

    if re.search(r"\b(wait|pause)\b", cleaned):
        seconds_match = re.search(r"(\d+(?:\.\d+)?)", cleaned)
        seconds = float(seconds_match.group(1)) if seconds_match else 1.0
        return Intent(name="wait", entities={"seconds": seconds}, confidence=0.8, raw_text=text)

    # Reminder creation
    if re.search(r"\b(create|add|make|set)\b", cleaned) and re.search(r"\b(reminder|reminders)\b", cleaned):
        # Extract reminder name/title
        name_match = re.search(r"(?:reminder|reminders)\s+(?:to\s+|for\s+|called\s+|named\s+)?([^,]+)", cleaned)
        if name_match:
            name = name_match.group(1).strip()
        else:
            name = _extract_after_keywords(text, lowered, ["reminder ", "reminders "])
        
        # Extract list name
        list_match = re.search(r"(?:in|to)\s+(?:list\s+)?([a-z0-9 ]+?)(?:\s+list)?(?=\s+(?:to|for|called|named|reminder)|$)", cleaned)
        list_name = list_match.group(1).strip() if list_match else "Reminders"
        
        # Extract notes/body
        body = ""
        body_match = re.search(r"(?:saying|that|with note|with notes|note)\s+(.+?)$", lowered)
        if body_match:
            body = body_match.group(1).strip()
        
        return Intent(
            name="create_reminder",
            entities={"name": name or "", "list_name": list_name, "body": body},
            confidence=0.88,
            raw_text=text,
        )

    return Intent(name="unknown", entities={"text": text}, confidence=0.0, raw_text=text)
