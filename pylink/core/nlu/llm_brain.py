"""
LLM Brain for PixelLink Voice Agent.
Uses OpenAI to understand natural language commands and provide conversational interaction.
"""

import json
import os
import logging
from typing import Optional, List, Dict, Any

from openai import OpenAI
from dotenv import load_dotenv

from core.nlu.intents import Intent

load_dotenv()

logger = logging.getLogger(__name__)

# List of sensitive/irreversible actions that require explicit confirmation
SENSITIVE_ACTIONS = {
    "send_email": "sending an email",
    "send_text": "sending a text message",
    "send_message": "sending a message",
    "delete_file": "deleting a file",
    "browser_fill_form": "submitting a form",
    "login": "logging into a service",
    "complete_checkout": "completing a purchase",
    "create_reminder": "creating a reminder",
    "create_note": "creating a note",
    "reply_email": "replying to an email",
}

# System prompt for conversational AI that asks clarifying questions
CONVERSATIONAL_SYSTEM_PROMPT = """You are PixelLink, a friendly and helpful voice-controlled computer assistant.
Your job is to understand user requests and either:
1. Execute the task if you fully understand what they want
2. Ask clarifying questions if anything is unclear

You must respond with ONLY valid JSON. The JSON must have this structure:
{
    "status": "ready" | "needs_clarification" | "confirm_sensitive",
    "intent": "<intent_name>",
    "entities": {<key-value pairs of extracted info>},
    "confidence": <0.0 to 1.0>,
    "clarification_question": "<question to ask user, if status is needs_clarification>",
    "missing_info": ["<list of what's unclear>"],
    "confirmation_summary": "<summary of action for user to confirm, if status is confirm_sensitive>",
    "user_message": "<friendly message to user>"
}

STATUS MEANINGS:
- "ready": You fully understand the task and can execute it
- "needs_clarification": Something is unclear or missing - ask the user
- "confirm_sensitive": This is a sensitive/irreversible action - summarize and ask for confirmation

SENSITIVE ACTIONS (always use confirm_sensitive status):
- Sending emails or text messages
- Submitting forms (especially with payment/personal data)
- Deleting files
- Login actions
- Creating reminders or notes (confirm the content)
- Any action that cannot be easily undone

Available intents:
1. "open_app" - entities: {"app": "<app name>"}
2. "focus_app" - entities: {"app": "<app name>"}
3. "type_text" - entities: {"content": "<text to type>"}
4. "click" - entities: {"target": "<what to click>"}
5. "search_web" - entities: {"query": "<search query>"}
6. "close_app" - entities: {"app": "<app name>"}
7. "send_text" - entities: {"target": "<recipient>", "content": "<message>", "app": "Messages"}
8. "send_email" / "reply_email" - entities: {"content": "<email content>", "app": "Mail"}
9. "browser_task" - entities: {"instruction": "<what to do in browser>", "url": "<optional url>"}
10. "browser_fill_form" - entities: {"instruction": "<form details>", "fields": {}}
11. "browser_click" - entities: {"element": "<what to click>"}
12. "browser_extract" - entities: {"content_type": "<what to extract>"}
13. "create_reminder" - entities: {"name": "<reminder text>", "due_date_iso": "<optional date>"}
14. "create_note" - entities: {"title": "<note title>", "body": "<note content>"}
15. "login" - entities: {"service": "<service name>"}
16. "confirm" - User confirms action
17. "cancel" - User cancels action
18. "exit" - User wants to quit
19. "unknown" - Cannot understand

CLARIFICATION RULES:
- If user says "send a message" but doesn't specify recipient, ask: "Who should I send this message to?"
- If user says "send to John" but no message content, ask: "What would you like me to say to John?"
- If user says "search for something" but query is vague, ask for specifics
- If user says "fill out the form" without details, ask what information to fill in
- If browser action is unclear, ask what website or what to do

CONFIRMATION RULES (for sensitive actions):
- Always repeat back the key details before executing
- For messages: "I'm about to send '{content}' to {recipient}. Should I proceed?"
- For emails: "I'll reply with: '{content}'. Should I send this?"
- For forms: "I'm about to submit this form with your information. Please confirm."
- For login: "I'll log into {service} using your saved credentials. Proceed?"

Be conversational and helpful in your user_message. Don't be robotic.
"""

# Simple intent parsing prompt (legacy, used as fallback)
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


class ConversationalAI:
    """Conversational AI that asks clarifying questions and handles sensitive actions."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the conversational AI.

        Args:
            api_key: OpenAI API key. If not provided, reads from OPENAI_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY in .env file.")

        self.client = OpenAI(api_key=self.api_key)
        self.model_id = "gpt-4o"  # Use GPT-4o for better conversational understanding
        self.conversation_history: List[Dict[str, str]] = []
        self.pending_action: Optional[Dict[str, Any]] = None
        logger.info(f"ConversationalAI initialized with model: {self.model_id}")

    def reset_conversation(self) -> None:
        """Reset the conversation history."""
        self.conversation_history = []
        self.pending_action = None

    def analyze_request(
        self,
        text: str,
        context: Optional[dict] = None
    ) -> Dict[str, Any]:
        """Analyze user request and determine if clarification or confirmation is needed.

        Args:
            text: The user's input.
            context: Optional context about previous actions.

        Returns:
            Dictionary with analysis results including:
            - status: "ready", "needs_clarification", or "confirm_sensitive"
            - intent: The detected intent name
            - entities: Extracted entities
            - clarification_question: Question to ask (if needs_clarification)
            - confirmation_summary: Summary for confirmation (if confirm_sensitive)
            - user_message: Friendly message to display to user
        """
        if not text or not text.strip():
            return {
                "status": "needs_clarification",
                "intent": "unknown",
                "entities": {},
                "confidence": 0.0,
                "clarification_question": "I didn't catch that. What would you like me to do?",
                "user_message": "I'm listening. What can I help you with?",
            }

        try:
            # Build context message
            context_info = ""
            if context:
                if context.get("last_intent"):
                    context_info += f"Previous intent: {context['last_intent']}\n"
                if context.get("last_app"):
                    context_info += f"Last focused app: {context['last_app']}\n"
                if context.get("pending_clarification"):
                    pending = context["pending_clarification"]
                    context_info += f"Pending clarification for: {pending.get('intent_name', 'unknown')}\n"
                    context_info += f"We were asking: {pending.get('prompt', '')}\n"

            # Add user message to history
            user_message = f"{context_info}User said: \"{text}\""
            self.conversation_history.append({"role": "user", "content": user_message})

            # Build messages for API call
            messages = [
                {"role": "system", "content": CONVERSATIONAL_SYSTEM_PROMPT},
            ] + self.conversation_history[-10:]  # Keep last 10 messages for context

            # Call OpenAI
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=messages,
                temperature=0.3,
                max_tokens=512,
            )
            response_text = response.choices[0].message.content.strip()

            # Clean up response - remove markdown code blocks if present
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1])

            # Parse JSON response
            data = json.loads(response_text)

            # Add assistant response to history
            self.conversation_history.append({"role": "assistant", "content": response_text})

            # Store pending action if it's a sensitive action needing confirmation
            if data.get("status") == "confirm_sensitive":
                self.pending_action = {
                    "intent": data.get("intent"),
                    "entities": data.get("entities", {}),
                    "confirmation_summary": data.get("confirmation_summary", ""),
                }

            logger.debug(f"ConversationalAI analyzed '{text}' -> {data}")
            return data

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse OpenAI response as JSON: {e}")
            return {
                "status": "needs_clarification",
                "intent": "unknown",
                "entities": {"text": text},
                "confidence": 0.0,
                "clarification_question": "I had trouble understanding that. Could you rephrase?",
                "user_message": "Sorry, I didn't quite get that. Could you say it differently?",
            }
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return {
                "status": "needs_clarification",
                "intent": "unknown",
                "entities": {"text": text},
                "confidence": 0.0,
                "clarification_question": "Something went wrong. What would you like me to do?",
                "user_message": f"I encountered an issue. Let's try again - what can I help you with?",
            }

    def get_pending_action(self) -> Optional[Dict[str, Any]]:
        """Get the pending action awaiting confirmation."""
        return self.pending_action

    def clear_pending_action(self) -> None:
        """Clear the pending action."""
        self.pending_action = None

    def generate_completion_message(
        self,
        intent: str,
        success: bool,
        result_message: str = ""
    ) -> str:
        """Generate a friendly completion message after task execution.

        Args:
            intent: The intent that was executed.
            success: Whether the task succeeded.
            result_message: Optional result details.

        Returns:
            A friendly completion message.
        """
        try:
            prompt = f"""Generate a brief, friendly confirmation message for the user.
Task: {intent}
Success: {success}
Details: {result_message}

Respond with just the message text, no JSON. Keep it concise (1-2 sentences).
If successful, confirm what was done. If failed, explain briefly and offer to help."""

            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # Use mini for quick responses
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Be concise and friendly."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=100,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"Error generating completion message: {e}")
            if success:
                return f"Done! {result_message}" if result_message else "Task completed successfully."
            else:
                return f"Sorry, there was an issue. {result_message}" if result_message else "Task could not be completed."

    def is_sensitive_action(self, intent: str) -> bool:
        """Check if an intent is a sensitive action requiring confirmation."""
        return intent in SENSITIVE_ACTIONS

    def get_sensitive_action_description(self, intent: str) -> str:
        """Get a human-readable description of a sensitive action."""
        return SENSITIVE_ACTIONS.get(intent, "performing this action")


class OpenAIBrain:
    """LLM-based natural language understanding using OpenAI."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize the OpenAI brain.

        Args:
            api_key: OpenAI API key. If not provided, reads from OPENAI_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY in .env file.")

        self.client = OpenAI(api_key=self.api_key)
        # Use gpt-4o-mini - fast and good for intent parsing
        self.model_id = "gpt-4o-mini"
        logger.info(f"OpenAI brain initialized with model: {self.model_id}")

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

            # Call OpenAI
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=256,
            )
            response_text = response.choices[0].message.content.strip()

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
            logger.error(f"Failed to parse OpenAI response as JSON: {e}")
            return Intent(name="unknown", entities={"text": text}, confidence=0.0, raw_text=text)
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return Intent(name="unknown", entities={"text": text}, confidence=0.0, raw_text=text)


# Global instance for easy access
_brain: Optional[OpenAIBrain] = None


def get_brain() -> OpenAIBrain:
    """Get or create the global OpenAI brain instance."""
    global _brain
    if _brain is None:
        _brain = OpenAIBrain()
    return _brain


def parse_with_llm(text: str, context: Optional[dict] = None) -> Intent:
    """Parse user input using the OpenAI LLM brain.

    This is the main function to use for LLM-based parsing.

    Args:
        text: The user's spoken/typed input.
        context: Optional context dictionary.

    Returns:
        Intent object with parsed intent and entities.
    """
    brain = get_brain()
    return brain.parse(text, context)


# Global conversational AI instance
_conversational_ai: Optional[ConversationalAI] = None


def get_conversational_ai() -> ConversationalAI:
    """Get or create the global ConversationalAI instance."""
    global _conversational_ai
    if _conversational_ai is None:
        _conversational_ai = ConversationalAI()
    return _conversational_ai


def analyze_with_conversation(
    text: str,
    context: Optional[dict] = None
) -> Dict[str, Any]:
    """Analyze user input using conversational AI.

    This function uses the conversational AI to:
    1. Understand the user's intent
    2. Ask clarifying questions if needed
    3. Request confirmation for sensitive actions
    4. Provide friendly responses

    Args:
        text: The user's spoken/typed input.
        context: Optional context dictionary with session info.

    Returns:
        Dictionary with analysis results.
    """
    ai = get_conversational_ai()
    return ai.analyze_request(text, context)


def generate_completion_message(intent: str, success: bool, result: str = "") -> str:
    """Generate a friendly completion message after task execution.

    Args:
        intent: The intent that was executed.
        success: Whether the task succeeded.
        result: Optional result details.

    Returns:
        A friendly completion message.
    """
    ai = get_conversational_ai()
    return ai.generate_completion_message(intent, success, result)
