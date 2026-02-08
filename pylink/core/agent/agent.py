"""
Dynamic AI agent that uses OpenAI tool calling to handle any user request.
The agent can reason, call tools, and iterate until it produces a final answer.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path)

logger = logging.getLogger(__name__)

AGENT_SYSTEM = """You are PixelLink, a capable assistant that can use tools to help the user.
You have access to tools for Gmail, Calendar, Reminders, Notes, and more.
When the user asks for something:
1. Use the appropriate tools to get the information or perform the action
2. For "read my 2nd email's subject" - call gmail_list_messages with max_results=2, then gmail_get_message with the 2nd message's id, then return just the subject
3. For "what are my top 10 emails" - call gmail_list_messages(10), then optionally gmail_get_message for each to show subject/sender
4. Synthesize the results into a clear, concise response
5. If a tool fails, explain what happened and suggest alternatives
Always respond in a helpful, conversational way. Keep responses brief unless the user wants detail."""


def _build_tool_definitions(mcp_tools: dict[str, Any]) -> list[dict]:
    """Build OpenAI tool definitions from MCP tools and built-in actions."""
    tools = [
        {
            "type": "function",
            "function": {
                "name": "gmail_list_messages",
                "description": "List Gmail messages. Returns list of {id, threadId}. Use these ids with gmail_get_message.",
                "parameters": {
                    "type": "object",
                    "properties": {"max_results": {"type": "integer", "description": "Number of messages to fetch", "default": 10}},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "gmail_get_message",
                "description": "Get full Gmail message by id. Returns subject, from, to, date, body, snippet.",
                "parameters": {
                    "type": "object",
                    "properties": {"message_id": {"type": "string", "description": "The message ID from gmail_list_messages"}},
                    "required": ["message_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "gmail_send_message",
                "description": "Send a Gmail email",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "to": {"type": "string"},
                        "subject": {"type": "string"},
                        "body": {"type": "string"},
                    },
                    "required": ["to", "subject", "body"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "calendar_list_events",
                "description": "List upcoming Google Calendar events",
                "parameters": {
                    "type": "object",
                    "properties": {"max_results": {"type": "integer", "default": 10}},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "calendar_create_event",
                "description": "Create a calendar event",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "start_iso": {"type": "string", "description": "ISO datetime"},
                        "end_iso": {"type": "string", "description": "ISO datetime"},
                    },
                    "required": ["summary", "start_iso", "end_iso"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "calendar_delete_event",
                "description": "Delete a calendar event by ID",
                "parameters": {
                    "type": "object",
                    "properties": {"event_id": {"type": "string"}},
                    "required": ["event_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "reminders_list_lists",
                "description": "List Reminders list names",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "reminders_list_reminders",
                "description": "List reminders in a list",
                "parameters": {
                    "type": "object",
                    "properties": {"list_name": {"type": "string", "default": "Reminders"}},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "reminders_create_reminder",
                "description": "Create a reminder",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "list_name": {"type": "string", "default": "Reminders"},
                        "body": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "notes_list_folders",
                "description": "List Apple Notes folder names",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "notes_list_notes",
                "description": "List note titles in a folder",
                "parameters": {
                    "type": "object",
                    "properties": {"folder_name": {"type": "string", "default": "Notes"}},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "notes_create_note",
                "description": "Create a note",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "folder_name": {"type": "string", "default": "Notes"},
                        "body": {"type": "string"},
                    },
                    "required": ["title"],
                },
            },
        },
    ]
    # Only include tools that we actually have
    available = set(mcp_tools.keys())
    return [t for t in tools if t["function"]["name"] in available]


async def _run_tool(name: str, args: dict, mcp_tools: dict) -> str:
    """Execute a tool and return JSON string result."""
    fn = mcp_tools.get(name)
    if not fn:
        return json.dumps({"error": f"Tool {name} not available"})
    try:
        result = await fn(**{k: v for k, v in args.items() if v is not None})
        return json.dumps(result, default=str)
    except Exception as e:
        logger.exception(f"Tool {name} failed")
        return json.dumps({"error": str(e)})


def run_agent(user_message: str, mcp_tools: dict[str, Any]) -> str:
    """
    Run the agent loop: LLM decides which tools to call, we execute, repeat until done.
    Returns the final message to show the user.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "OpenAI API key not configured. Set OPENAI_API_KEY in .env"

    if not mcp_tools:
        return "No tools available. Configure Gmail/Calendar credentials to enable."

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    tools = _build_tool_definitions(mcp_tools)
    if not tools:
        return "No MCP tools are configured. Add credentials.json for Gmail/Calendar."

    messages = [
        {"role": "system", "content": AGENT_SYSTEM},
        {"role": "user", "content": user_message},
    ]
    max_iterations = 10

    for _ in range(max_iterations):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.3,
            max_tokens=1024,
        )
        choice = response.choices[0]
        msg = choice.message

        if not msg.tool_calls:
            # Final text response
            return (msg.content or "").strip()

        # Execute tool calls
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = asyncio.run(_run_tool(name, args, mcp_tools))
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": tc.id, "type": "function", "function": {"name": name, "arguments": tc.function.arguments}}
                    ],
                }
            )
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": result}
            )

    return "I had trouble completing that. Please try rephrasing."
