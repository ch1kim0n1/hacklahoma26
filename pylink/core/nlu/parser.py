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

_CLEANER_WORDS_PATTERN = re.compile(r"\b(can you|could you|please|the|a|an|for me)\b")
_FILE_SEARCH_PATTERN = re.compile(r"\b(find file|search file|locate file|find document|search for file|search document)\b")
_LOGIN_PATTERN = re.compile(r"\b(login|log in|sign in|signin|authenticate)\b")
_LOGIN_TAIL_PATTERN = re.compile(r"(\w+)\s+(?:login|log in|sign in)")
_YOUTUBE_SEARCH_PATTERN = re.compile(r"\b(search youtube for|find on youtube|look up on youtube)\b")
_WEB_SEARCH_PATTERN = re.compile(
    r"\b(search|browse|find|look up|google|search for|browse for|find on internet|search internet|search online|look online)\b"
)
_OPEN_SITE_PATTERN = re.compile(r"\b(open|visit|go to|launch|load)\b")
_SITE_HINT_PATTERN = re.compile(r"\b(browser|website|web|youtube|google|github|reddit|linkedin|gmail)\b")
_OPEN_FILE_PATTERN = re.compile(r"\b(open file|open document)\b")
_REPLY_PATTERN = re.compile(r"\b(reply|respond|answer)\b")
_MAIL_OR_MESSAGE_PATTERN = re.compile(r"\b(email|mail|message)\b")
_OPEN_APP_PATTERN = re.compile(r"\b(open|launch|start|run|fire up|boot)\b")
_FOCUS_APP_PATTERN = re.compile(r"\b(focus|switch to|go to|bring up|activate)\b")
_CLOSE_APP_PATTERN = re.compile(r"\b(close app|quit app|exit app|close application|quit)\b")
_NOTE_ACTION_PATTERN = re.compile(r"\b(create|add|make|write)\b")
_NOTE_PATTERN = re.compile(r"\b(note|notes)\b")
_TYPE_PATTERN = re.compile(r"\b(type|write|enter|input|dictate)\b")
_DOUBLE_CLICK_PATTERN = re.compile(r"\b(double click|double tap)\b")
_RIGHT_CLICK_PATTERN = re.compile(r"\b(right click|secondary click)\b")
_CLICK_PATTERN = re.compile(r"\b(click|tap|press here)\b")
_SCROLL_PATTERN = re.compile(r"\b(scroll up|scroll down|page up|page down)\b")
_SCROLL_UP_PATTERN = re.compile(r"\b(scroll up|page up)\b")
_DIGITS_PATTERN = re.compile(r"\b(\d+)\b")
_NEW_TAB_PATTERN = re.compile(r"\b(new tab|open tab)\b")
_CLOSE_TAB_PATTERN = re.compile(r"\b(close tab|remove tab)\b")
_NEXT_TAB_PATTERN = re.compile(r"\b(next tab|tab right)\b")
_PREV_TAB_PATTERN = re.compile(r"\b(previous tab|prev tab|tab left)\b")
_REFRESH_PATTERN = re.compile(r"\b(refresh|reload page)\b")
_BACK_PATTERN = re.compile(r"\b(go back|navigate back|back page)\b")
_FORWARD_PATTERN = re.compile(r"\b(go forward|navigate forward|forward page)\b")
_COPY_PATTERN = re.compile(r"\b(copy|copy this)\b")
_PASTE_PATTERN = re.compile(r"\b(paste|insert clipboard)\b")
_CUT_PATTERN = re.compile(r"\b(cut|cut this)\b")
_UNDO_PATTERN = re.compile(r"\b(undo|go undo)\b")
_REDO_PATTERN = re.compile(r"\b(redo|do again)\b")
_SELECT_ALL_PATTERN = re.compile(r"\b(select all|highlight all)\b")
_VOLUME_UP_PATTERN = re.compile(r"\b(volume up|increase volume|louder)\b")
_VOLUME_DOWN_PATTERN = re.compile(r"\b(volume down|decrease volume|quieter)\b")
_MUTE_PATTERN = re.compile(r"\b(mute|silence)\b")
_PRESS_KEY_PATTERN = re.compile(r"\b(press|hit)\s+([a-z0-9_-]+)\b")
_MINIMIZE_PATTERN = re.compile(r"\b(minimize window|minimize)\b")
_MAXIMIZE_PATTERN = re.compile(r"\b(maximize window|maximize)\b")
_WAIT_PATTERN = re.compile(r"\b(wait|pause)\b")
_SECONDS_PATTERN = re.compile(r"(\d+(?:\.\d+)?)")
_REMINDER_ACTION_PATTERN = re.compile(r"\b(create|add|make|set)\b")
_REMINDER_PATTERN = re.compile(r"\b(reminder|reminders)\b")


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
    lowered = text.lower().strip()
    cleaned = _CLEANER_WORDS_PATTERN.sub("", lowered).strip()

    if lowered in {"confirm", "yes", "y", "ok", "okay", "sure", "proceed", "go ahead", "do it"}:
        return Intent(name="confirm", confidence=1.0, raw_text=text)

    if lowered in {"cancel", "stop", "abort", "no", "n", "nevermind", "nope", "never mind"}:
        return Intent(name="cancel", confidence=1.0, raw_text=text)

    # File search - check early before general search patterns
    if _FILE_SEARCH_PATTERN.search(cleaned):
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
    if _LOGIN_PATTERN.search(cleaned):
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
            match = _LOGIN_TAIL_PATTERN.search(cleaned)
            if match:
                service = match.group(1)
        
        if service:
            return Intent(
                name="login",
                entities={"service": service.strip()},
                confidence=0.87,
                raw_text=text,
            )

    if _YOUTUBE_SEARCH_PATTERN.search(cleaned):
        query = _extract_after_keywords(text, lowered, ["search youtube for ", "find on youtube ", "look up on youtube "])
        if query:
            return Intent(
                name="search_youtube",
                entities={"query": query},
                confidence=0.9,
                raw_text=text,
            )

    # Enhanced web search patterns
    if _WEB_SEARCH_PATTERN.search(cleaned):
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

    if _OPEN_SITE_PATTERN.search(cleaned) and _SITE_HINT_PATTERN.search(cleaned):
        url = _extract_website_url(text, lowered)
        if url:
            return Intent(name="open_website", entities={"url": url}, confidence=0.92, raw_text=text)

    if _OPEN_FILE_PATTERN.search(cleaned):
        file_path = _extract_after_keywords(text, lowered, ["open file ", "open document "])
        if file_path:
            return Intent(name="open_file", entities={"path": file_path.strip()}, confidence=0.8, raw_text=text)

    send_text_intent = _parse_send_text(text, lowered)
    if send_text_intent:
        return send_text_intent

    if _REPLY_PATTERN.search(cleaned) and _MAIL_OR_MESSAGE_PATTERN.search(cleaned):
        content = _extract_after_keywords(text, lowered, ["saying ", "that ", "with ", ":"])
        entities = {
            "target": "last_email" if "last" in lowered or "previous" in lowered else "email",
            "content": content or "",
        }
        return Intent(name="reply_email", entities=entities, confidence=0.82, raw_text=text)

    if _OPEN_APP_PATTERN.search(cleaned) and not _NEW_TAB_PATTERN.search(cleaned):
        app = _extract_after_keywords(text, lowered, ["open ", "launch ", "start ", "run ", "fire up ", "boot "])
        if app:
            app = re.sub(r"\s+(app|application)$", "", app.strip(), flags=re.IGNORECASE)
            return Intent(name="open_app", entities={"app": app}, confidence=0.88, raw_text=text)

    if _FOCUS_APP_PATTERN.search(cleaned):
        app = _extract_after_keywords(text, lowered, ["focus ", "switch to ", "go to ", "bring up ", "activate "])
        if app:
            app = re.sub(r"\s+(app|application)$", "", app.strip(), flags=re.IGNORECASE)
            return Intent(name="focus_app", entities={"app": app}, confidence=0.86, raw_text=text)

    if _CLOSE_APP_PATTERN.search(cleaned):
        app = _extract_after_keywords(text, lowered, ["close app ", "quit app ", "exit app ", "close application ", "quit "])
        return Intent(name="close_app", entities={"app": (app or "").strip()}, confidence=0.84, raw_text=text)

    # Note creation - check before type_text to avoid conflicts
    if _NOTE_ACTION_PATTERN.search(cleaned) and _NOTE_PATTERN.search(cleaned):
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

    if _TYPE_PATTERN.search(cleaned):
        content = _extract_after_keywords(text, lowered, ["type ", "write ", "enter ", "input ", "dictate "])
        if content:
            content = re.sub(r"^:\s*", "", content)
            return Intent(name="type_text", entities={"content": content}, confidence=0.84, raw_text=text)

    if _DOUBLE_CLICK_PATTERN.search(cleaned):
        return Intent(name="double_click", confidence=0.84, raw_text=text)

    if _RIGHT_CLICK_PATTERN.search(cleaned):
        return Intent(name="right_click", confidence=0.84, raw_text=text)

    if _CLICK_PATTERN.search(cleaned):
        target = _extract_after_keywords(text, lowered, ["click ", "tap ", "press here "]) or ""
        return Intent(name="click", entities={"target": target}, confidence=0.8, raw_text=text)

    if _SCROLL_PATTERN.search(cleaned):
        direction = "up" if _SCROLL_UP_PATTERN.search(cleaned) else "down"
        amount_match = _DIGITS_PATTERN.search(cleaned)
        amount = int(amount_match.group(1)) if amount_match else 450
        return Intent(name="scroll", entities={"direction": direction, "amount": amount}, confidence=0.9, raw_text=text)

    if _NEW_TAB_PATTERN.search(cleaned):
        return Intent(name="new_tab", confidence=0.9, raw_text=text)

    if _CLOSE_TAB_PATTERN.search(cleaned):
        return Intent(name="close_tab", confidence=0.9, raw_text=text)

    if _NEXT_TAB_PATTERN.search(cleaned):
        return Intent(name="next_tab", confidence=0.88, raw_text=text)

    if _PREV_TAB_PATTERN.search(cleaned):
        return Intent(name="previous_tab", confidence=0.88, raw_text=text)

    if _REFRESH_PATTERN.search(cleaned):
        return Intent(name="refresh_page", confidence=0.9, raw_text=text)

    if _BACK_PATTERN.search(cleaned):
        return Intent(name="navigate_back", confidence=0.86, raw_text=text)

    if _FORWARD_PATTERN.search(cleaned):
        return Intent(name="navigate_forward", confidence=0.86, raw_text=text)

    if _COPY_PATTERN.search(cleaned):
        return Intent(name="copy", confidence=0.9, raw_text=text)
    if _PASTE_PATTERN.search(cleaned):
        return Intent(name="paste", confidence=0.9, raw_text=text)
    if _CUT_PATTERN.search(cleaned):
        return Intent(name="cut", confidence=0.9, raw_text=text)
    if _UNDO_PATTERN.search(cleaned):
        return Intent(name="undo", confidence=0.9, raw_text=text)
    if _REDO_PATTERN.search(cleaned):
        return Intent(name="redo", confidence=0.9, raw_text=text)
    if _SELECT_ALL_PATTERN.search(cleaned):
        return Intent(name="select_all", confidence=0.9, raw_text=text)

    if _VOLUME_UP_PATTERN.search(cleaned):
        return Intent(name="volume_up", confidence=0.84, raw_text=text)
    if _VOLUME_DOWN_PATTERN.search(cleaned):
        return Intent(name="volume_down", confidence=0.84, raw_text=text)
    if _MUTE_PATTERN.search(cleaned):
        return Intent(name="mute", confidence=0.84, raw_text=text)

    press_match = _PRESS_KEY_PATTERN.search(cleaned)
    if press_match:
        return Intent(name="press_key", entities={"key": press_match.group(2)}, confidence=0.82, raw_text=text)

    if _MINIMIZE_PATTERN.search(cleaned):
        return Intent(name="minimize_window", confidence=0.8, raw_text=text)
    if _MAXIMIZE_PATTERN.search(cleaned):
        return Intent(name="maximize_window", confidence=0.8, raw_text=text)

    if _WAIT_PATTERN.search(cleaned):
        seconds_match = _SECONDS_PATTERN.search(cleaned)
        seconds = float(seconds_match.group(1)) if seconds_match else 1.0
        return Intent(name="wait", entities={"seconds": seconds}, confidence=0.8, raw_text=text)

    # Reminder creation
    if _REMINDER_ACTION_PATTERN.search(cleaned) and _REMINDER_PATTERN.search(cleaned):
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
