"""
LLM Brain for PixelLink Voice Agent.
Uses Google Gemini to understand natural language commands.
"""

import json
import os
import logging
from typing import Optional

from google import genai
from google.genai import types
from dotenv import load_dotenv

from core.nlu.intents import Intent

load_dotenv()

logger = logging.getLogger(__name__)

# System prompt that tells Gemini how to parse commands
SYSTEM_PROMPT = """You are the brain of a voice-controlled computer assistant called PixelLink.
Your job is to understand what the user wants to do and return a structured JSON response.

You must respond with ONLY valid JSON, no other text. The JSON must have this structure:
{
    "intent": "<intent_name>",
    "entities": {<key-value pairs of extracted info>},
    "confidence": <0.0 to 1.0>
}

Available intents and their entities:

1. "open_app" - User wants to open an application
   entities: {"app": "<app name>"}
   Examples: "open Safari", "launch Notes", "fire up the browser", "I need Chrome"

2. "focus_app" - User wants to switch to an already open application
   entities: {"app": "<app name>"}
   Examples: "switch to Safari", "go to Notes", "focus on Terminal"

3. "type_text" - User wants to type something
   entities: {"content": "<text to type>"}
   Examples: "type hello world", "write Dear John", "enter my email"

4. "click" - User wants to click something
   entities: {"target": "<what to click>"}
   Examples: "click the submit button", "click on save"

5. "search_web" - User wants to search the web
   entities: {"query": "<search query>"}
   Examples: "search for Python tutorials", "google how to cook pasta", "look up weather"

6. "close_app" - User wants to close an application
   entities: {"app": "<app name>"}
   Examples: "close Safari", "quit Notes", "exit Chrome"

7. "confirm" - User is confirming an action
   entities: {}
   Examples: "yes", "confirm", "do it", "go ahead", "sure"

8. "cancel" - User is cancelling an action
   entities: {}
   Examples: "no", "cancel", "stop", "nevermind", "abort"

9. "exit" - User wants to stop the voice assistant
   entities: {}
   Examples: "goodbye", "bye", "exit", "quit assistant", "I'm done", "that's all"

10. "unknown" - You cannot understand what the user wants
    entities: {"text": "<original text>"}

Important rules:
- Extract the ACTUAL app/content name, not the literal words. "fire up the browser" means Safari or Chrome, not "the browser"
- For macOS, common apps: Safari, Chrome, Notes, Terminal, Finder, Messages, Mail, Calendar, Music, Photos
- Be flexible with phrasing - "open up", "launch", "start", "fire up", "get me" all mean open_app
- If the user says goodbye/bye/exit in any form, return "exit" intent
- confidence should be high (0.9+) if you're sure, lower if uncertain
- Always return valid JSON, nothing else
"""


class GeminiBrain:
    """LLM-based natural language understanding using Google Gemini."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the Gemini brain.

        Args:
            api_key: Gemini API key. If not provided, reads from GEMINI env var.
        """
        self.api_key = api_key or os.getenv("GEMINI")
        if not self.api_key:
            raise ValueError("Gemini API key not found. Set GEMINI in .env file.")

        self.client = genai.Client(api_key=self.api_key)
        # Use gemini-2.0-flash - fast and good for intent parsing
        # Fall back to gemini-2.0-flash-lite if needed
        self.model_id = "gemini-2.0-flash"
        logger.info(f"Gemini brain initialized with model: {self.model_id}")

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
            # Build the prompt
            prompt = f"User said: \"{text}\"\n\nReturn the JSON response:"

            # Add context if available
            if context and context.get("last_intent"):
                prompt = f"Previous intent: {context['last_intent']}\n\n{prompt}"

            # Call Gemini
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=0.1,
                    max_output_tokens=256,
                ),
            )
            response_text = response.text.strip()

            # Clean up response - remove markdown code blocks if present
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                # Remove first and last lines (```json and ```)
                response_text = "\n".join(lines[1:-1])

            # Parse JSON
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
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            return Intent(name="unknown", entities={"text": text}, confidence=0.0, raw_text=text)
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return Intent(name="unknown", entities={"text": text}, confidence=0.0, raw_text=text)


# Global instance for easy access
_brain: Optional[GeminiBrain] = None


def get_brain() -> GeminiBrain:
    """Get or create the global Gemini brain instance."""
    global _brain
    if _brain is None:
        _brain = GeminiBrain()
    return _brain


def parse_with_llm(text: str, context: Optional[dict] = None) -> Intent:
    """Parse user input using the Gemini LLM brain.

    This is the main function to use for LLM-based parsing.

    Args:
        text: The user's spoken/typed input.
        context: Optional context dictionary.

    Returns:
        Intent object with parsed intent and entities.
    """
    brain = get_brain()
    return brain.parse(text, context)
