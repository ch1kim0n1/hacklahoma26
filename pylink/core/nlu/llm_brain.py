"""
LLM Brain for PixelLink Voice Agent.
Uses OpenAI to understand natural language commands and generate responses.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from openai import OpenAI
from dotenv import load_dotenv

from core.nlu.intents import Intent

# Load .env from pylink/ so it works when bridge runs with cwd=repo root
_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path)

logger = logging.getLogger(__name__)

# System prompt that tells the LLM how to parse commands - covers all PixelLink intents
SYSTEM_PROMPT = """You are the brain of a voice-controlled computer assistant called PixelLink on macOS.
Parse the user's input and return ONLY valid JSON with this structure:
{"intent": "<intent_name>", "entities": {...}, "confidence": <0.0-1.0>}

AVAILABLE INTENTS (use these exact names):

Apps: open_app, focus_app, close_app - entities: {"app": "<name>"}
  "open Safari", "launch Notes", "switch to Chrome", "quit Mail", "fire up the browser" -> Safari

Web: search_web, search_youtube, open_website
  search_web: {"query": "<search terms>"} - "search for Python", "google weather"
  search_youtube: {"query": "<search>"} - "search youtube for cats"
  open_website: {"url": "<full url>"} - "open github.com", "go to mail.google.com" -> https://mail.google.com

Files: search_file, open_file
  search_file: {"query": "<filename or terms>"} - "find file report.pdf"
  open_file: {"path": "<path>"} - "open file document.pdf"

Text/messaging:
  send_text: {"target": "<contact>", "content": "<message>", "app": "Messages"}
    "text John saying hi", "message Sarah that I'm on my way"
    If target missing: add "requires_clarification": true, "clarification_prompt": "Who should receive this?", "clarification_type": "send_text_target"
    If content missing: add "requires_clarification": true, "clarification_prompt": "What should I say?"
  reply_email: {"content": "<reply text>", "app": "Mail"} - "reply email saying I'll send it tomorrow"

Typing/input: type_text {"content": "<text>"} - "type hello world", "write Dear John"

Click/scroll: click {"target": "<what>"}, right_click {}, double_click {}
  scroll: {"direction": "up|down", "amount": 450}

Keys: press_key {"key": "<key>"} - "press enter", "hit tab"
  volume_up, volume_down, mute - no entities

Tabs: new_tab, close_tab, next_tab, previous_tab
  refresh_page, navigate_back, navigate_forward

Clipboard: copy, paste, cut, undo, redo, select_all

Window: minimize_window, maximize_window

Reminders (Apple): create_reminder {"name": "<title>", "list_name": "Reminders", "body": ""}
  list_reminder_lists {}, list_reminders {"list_name": "<list>"}

Notes (Apple): create_note {"title": "<title>", "folder_name": "Notes", "body": ""}
  list_note_folders {}, list_notes {"folder_name": "<folder>"}

Gmail (Google): gmail_list_messages {"max_results": 10} - "show my emails", "list emails"
  gmail_get_message {"message_id": "<id>"} - "read email X" (need message id from list)
  gmail_read_first {} - "read first email", "read latest email", "read my last email"
  gmail_send_email {"to": "<email>", "subject": "<subj>", "body": "<text>"} - "send email to X saying Y"

Calendar (Google): calendar_list_events {"max_results": 10} - "what's on my calendar", "show my events"
  calendar_create_event {"summary": "<title>", "start_iso": "<ISO datetime>", "end_iso": "<ISO>"}
  calendar_delete_event {"event_id": "<id>"}

Other: login {"service": "<site>"} - "login to github"
  wait {"seconds": 1.0}
  confirm {}, cancel {}, exit {}

unknown: when you cannot determine intent - entities: {"text": "<original>"}

RULES:
- Use proper macOS app names: Safari, Notes, Chrome, Mail, Terminal, Finder, Messages, Calendar
- For open_website use full URLs: github.com -> https://github.com, gmail -> https://mail.google.com
- Be flexible: "I need Safari", "show me Notes", "text vlad saying hey" all valid
- confidence 0.9+ when sure, lower when uncertain
- Return ONLY valid JSON, no markdown or extra text
"""

# System prompt for conversational responses when the user's intent is unclear
CHAT_SYSTEM_PROMPT = """You are PixelLink, a helpful voice-controlled computer assistant. The user said something that wasn't recognized as a command.

Respond in 1-2 short, friendly sentences. Be helpful and suggest what they can try. Examples of what PixelLink can do:
- Open apps: "open Safari", "launch Notes"
- Type text: "type hello world"
- Search the web: "search for Python tutorials"
- Create reminders/notes: "create reminder Buy milk", "create note Meeting notes"
- Send messages: "text John saying hi there"
- Find files: "find file report.pdf"
- Reply to email: "reply email saying I'll send it tomorrow"
- Autofill login: "login to github"

Keep your response concise and actionable. Don't use markdown or bullet points in your reply."""


class LLMBrain:
    """LLM-based natural language understanding using OpenAI."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the LLM brain.

        Args:
            api_key: OpenAI API key. If not provided, reads from OPENAI_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY in .env file.")

        self.client = OpenAI(api_key=self.api_key)
        self.model_id = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        logger.info(f"LLM brain initialized with model: {self.model_id}")

    def _generate(self, system_prompt: str, user_prompt: str, temperature: float = 0.1, max_tokens: int = 256) -> str:
        """Call OpenAI chat completions and return the response text."""
        response = self.client.chat.completions.create(
            model=self.model_id,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (response.choices[0].message.content or "").strip()

    def parse(self, text: str, context: Optional[dict] = None) -> Intent:
        """Parse user input and return an Intent.

        Args:
            text: The user's spoken/typed input.
            context: Optional context about previous actions.

        Returns:
            Intent object with parsed intent and entities.
        """
        if not text or not text.strip():
            return Intent(name="unknown", entities={"text": ""}, confidence=0.0, raw_text="")

        try:
            user_prompt = f"User said: \"{text}\"\n\nReturn the JSON response:"
            if context and context.get("last_intent"):
                user_prompt = f"Previous intent: {context['last_intent']}\n\n{user_prompt}"

            response_text = self._generate(SYSTEM_PROMPT, user_prompt, temperature=0.1, max_tokens=512)

            # Clean up response - remove markdown code blocks if present
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1]) if len(lines) > 2 else response_text

            data = json.loads(response_text)
            intent_name = data.get("intent", "unknown")
            entities = data.get("entities", {})
            confidence = float(data.get("confidence", 0.5))

            logger.debug(f"Parsed '{text}' -> intent={intent_name}, entities={entities}")

            return Intent(
                name=intent_name,
                entities=entities,
                confidence=confidence,
                raw_text=text,
            )

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return Intent(name="unknown", entities={"text": text}, confidence=0.0, raw_text=text)
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return Intent(name="unknown", entities={"text": text}, confidence=0.0, raw_text=text)

    def respond(self, text: str, context: Optional[dict] = None) -> str:
        """Generate a conversational response for unclear or chat-like user input.

        Args:
            text: The user's message.
            context: Optional context (e.g., last intent, recent actions).

        Returns:
            A helpful, conversational response.
        """
        if not text or not text.strip():
            return "I didn't catch that. Could you try again?"

        try:
            user_prompt = f"User said: \"{text}\""
            if context and context.get("last_intent"):
                user_prompt = f"Context: User's last action was '{context['last_intent']}'.\n\n{user_prompt}"

            reply = self._generate(CHAT_SYSTEM_PROMPT, user_prompt, temperature=0.7)
            if reply:
                return reply
            return "I'm not sure how to help with that. Try saying something like 'open Notes' or 'search for Python tutorials'."
        except Exception as e:
            logger.error(f"OpenAI chat error: {e}")
            raise


# Global instance for easy access
_brain: Optional[LLMBrain] = None


def get_brain() -> LLMBrain:
    """Get or create the global LLM brain instance."""
    global _brain
    if _brain is None:
        _brain = LLMBrain()
    return _brain


def parse_with_llm(text: str, context: Optional[dict] = None) -> Intent:
    """Parse user input using the LLM brain.

    Args:
        text: The user's spoken/typed input.
        context: Optional context dictionary.

    Returns:
        Intent object with parsed intent and entities.
    """
    brain = get_brain()
    return brain.parse(text, context)


def respond_with_llm(text: str, context: Optional[dict] = None) -> str:
    """Generate a conversational response using the LLM.

    Use this when the user's input wasn't recognized as a command.
    Raises ValueError if OPENAI_API_KEY is not set. Caller should catch
    exceptions and fall back to a static message if needed.

    Args:
        text: The user's message.
        context: Optional context dictionary.

    Returns:
        A helpful response from the LLM.
    """
    brain = get_brain()
    return brain.respond(text, context)
