from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Any, List
from urllib.parse import quote_plus

from core.nlu.intents import Intent
from core.safety.guard import SafetyGuard


@dataclass
class ActionStep:
    action: str
    params: dict[str, Any]
    requires_confirmation: bool = False
    description: str = ""


class ActionPlanner:
    def __init__(self, mcp_tools=None):
        self.mcp_tools = mcp_tools or {}

    def plan(self, intent: Intent, context, guard: SafetyGuard) -> List[ActionStep]:
        steps: List[ActionStep] = []
        name = intent.name

        if name == "open_app":
            app_name = _resolve_app_name(intent.entities.get("app", ""), context)
            steps.append(ActionStep("open_app", {"app": app_name}, False, "Open app"))

        elif name == "focus_app":
            app_name = _resolve_app_name(intent.entities.get("app", ""), context)
            steps.append(ActionStep("focus_app", {"app": app_name}, False, "Focus app"))

        elif name == "close_app":
            app_name = intent.entities.get("app", "") or (context.last_app if context else "")
            steps.append(ActionStep("close_app", {"app": app_name}, False, "Close app"))

        elif name == "open_website":
            steps.append(ActionStep("open_url", {"url": intent.entities.get("url", "")}, False, "Open website"))

        elif name == "search_web":
            query = intent.entities.get("query", "")
            url = f"https://www.google.com/search?q={quote_plus(query)}"
            steps.append(ActionStep("open_url", {"url": url}, False, "Search the web"))

        elif name == "search_youtube":
            query = intent.entities.get("query", "")
            url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
            steps.append(ActionStep("open_url", {"url": url}, False, "Search YouTube"))

        elif name == "open_file":
            steps.append(ActionStep("open_file", {"path": intent.entities.get("path", "")}, False, "Open file"))

        elif name == "type_text":
            steps.append(ActionStep("type_text", {"content": intent.entities.get("content", "")}, False, "Type text"))

        elif name == "click":
            steps.append(ActionStep("click", {"target": intent.entities.get("target", "")}, False, "Click"))

        elif name == "right_click":
            steps.append(ActionStep("right_click", {}, False, "Right click"))

        elif name == "double_click":
            steps.append(ActionStep("double_click", {}, False, "Double click"))

        elif name == "scroll":
            direction = intent.entities.get("direction", "down")
            amount = int(intent.entities.get("amount", 450))
            steps.append(ActionStep("scroll", {"direction": direction, "amount": amount}, False, "Scroll"))

        elif name == "press_key":
            steps.append(ActionStep("press_key", {"key": intent.entities.get("key", "")}, False, "Press key"))

        elif name == "new_tab":
            steps.append(ActionStep("hotkey", {"keys": _new_tab_hotkey()}, False, "Open new tab"))

        elif name == "close_tab":
            steps.append(ActionStep("hotkey", {"keys": _close_tab_hotkey()}, False, "Close current tab"))

        elif name == "next_tab":
            steps.append(ActionStep("hotkey", {"keys": _next_tab_hotkey()}, False, "Go to next tab"))

        elif name == "previous_tab":
            steps.append(ActionStep("hotkey", {"keys": _previous_tab_hotkey()}, False, "Go to previous tab"))

        elif name == "refresh_page":
            steps.append(ActionStep("hotkey", {"keys": _refresh_hotkey()}, False, "Refresh page"))

        elif name == "navigate_back":
            steps.append(ActionStep("hotkey", {"keys": _back_hotkey()}, False, "Navigate back"))

        elif name == "navigate_forward":
            steps.append(ActionStep("hotkey", {"keys": _forward_hotkey()}, False, "Navigate forward"))

        elif name == "copy":
            steps.append(ActionStep("hotkey", {"keys": _copy_hotkey()}, False, "Copy"))
        elif name == "paste":
            steps.append(ActionStep("hotkey", {"keys": _paste_hotkey()}, False, "Paste"))
        elif name == "cut":
            steps.append(ActionStep("hotkey", {"keys": _cut_hotkey()}, False, "Cut"))
        elif name == "undo":
            steps.append(ActionStep("hotkey", {"keys": _undo_hotkey()}, False, "Undo"))
        elif name == "redo":
            steps.append(ActionStep("hotkey", {"keys": _redo_hotkey()}, False, "Redo"))
        elif name == "select_all":
            steps.append(ActionStep("hotkey", {"keys": _select_all_hotkey()}, False, "Select all"))

        elif name == "volume_up":
            steps.append(ActionStep("press_key", {"key": "volumeup"}, False, "Volume up"))
        elif name == "volume_down":
            steps.append(ActionStep("press_key", {"key": "volumedown"}, False, "Volume down"))
        elif name == "mute":
            steps.append(ActionStep("press_key", {"key": "volumemute"}, False, "Mute audio"))

        elif name == "minimize_window":
            steps.append(ActionStep("hotkey", {"keys": _minimize_hotkey()}, False, "Minimize window"))
        elif name == "maximize_window":
            steps.append(ActionStep("hotkey", {"keys": _maximize_hotkey()}, False, "Maximize window"))

        elif name == "send_text":
            target = intent.entities.get("target", "")
            content = intent.entities.get("content", "")
            app_name = intent.entities.get("app", "Messages")
            if _is_mac():
                steps.append(
                    ActionStep(
                        "send_text_native",
                        {"app": app_name, "target": target, "content": content},
                        False,
                        "Send text message",
                    )
                )
            else:
                steps.append(ActionStep("focus_app", {"app": app_name}, False, "Focus messaging app"))
                steps.append(ActionStep("wait", {"seconds": 0.6}, False, "Wait for app"))
                steps.append(ActionStep("hotkey", {"keys": _new_message_hotkey()}, False, "Create new message"))
                steps.append(ActionStep("type_text", {"content": target}, False, "Type recipient"))
                steps.append(ActionStep("press_key", {"key": "tab"}, False, "Move to message input"))
                steps.append(ActionStep("type_text", {"content": content}, False, "Type message"))
                steps.append(
                    ActionStep(
                        "send_message",
                        {"key": "enter"},
                        False,
                        "Send message",
                    )
                )

        elif name == "reply_email":
            app_name = intent.entities.get("app", "Mail")
            content = intent.entities.get("content", "")
            steps.append(ActionStep("focus_app", {"app": app_name}, False, "Focus email app"))
            steps.append(ActionStep("wait", {"seconds": 0.8}, False, "Wait for app"))
            steps.append(ActionStep("hotkey", {"keys": _reply_hotkey()}, False, "Open reply"))
            steps.append(ActionStep("type_text", {"content": content}, False, "Type reply"))
            steps.append(
                ActionStep(
                    "send_email",
                    {"keys": _send_hotkey()},
                    guard.requires_confirmation("send_email"),
                    "Send email",
                )
            )

        elif name == "wait":
            steps.append(ActionStep("wait", {"seconds": float(intent.entities.get("seconds", 1.0))}, False, "Wait"))

        elif name == "create_reminder":
            params = {
                "list_name": intent.entities.get("list_name", "Reminders"),
                "name": intent.entities.get("name", ""),
                "body": intent.entities.get("body", ""),
                "due_date_iso": intent.entities.get("due_date_iso"),
            }
            steps.append(
                ActionStep(
                    "reminders_create_reminder",
                    params,
                    False,
                    f"Create reminder '{params['name']}' in {params['list_name']}",
                )
            )

        elif name == "create_note":
            params = {
                "folder_name": intent.entities.get("folder_name", "Notes"),
                "title": intent.entities.get("title", ""),
                "body": intent.entities.get("body", ""),
            }
            steps.append(
                ActionStep(
                    "notes_create_note",
                    params,
                    False,
                    f"Create note '{params['title']}' in {params['folder_name']}",
                )
            )

        # Plugin tools - use tool name directly for generic dispatch
        elif name == "list_reminder_lists":
            steps.append(ActionStep("reminders_list_lists", {}, False, "List reminder lists"))
        elif name == "list_reminders":
            steps.append(
                ActionStep(
                    "reminders_list_reminders",
                    {"list_name": intent.entities.get("list_name", "Reminders")},
                    False,
                    "List reminders",
                )
            )
        elif name == "list_note_folders":
            steps.append(ActionStep("notes_list_folders", {}, False, "List note folders"))
        elif name == "list_notes":
            steps.append(
                ActionStep(
                    "notes_list_notes",
                    {"folder_name": intent.entities.get("folder_name", "Notes")},
                    False,
                    "List notes",
                )
            )
        elif name == "gmail_list_messages":
            params = {"max_results": int(intent.entities.get("max_results", 10))}
            if intent.entities.get("label_ids"):
                params["label_ids"] = intent.entities["label_ids"]
            steps.append(ActionStep("gmail_list_messages", params, False, "List Gmail messages"))
        elif name == "gmail_get_message":
            steps.append(
                ActionStep(
                    "gmail_get_message",
                    {"message_id": intent.entities.get("message_id", "")},
                    False,
                    "Get Gmail message",
                )
            )
        elif name == "gmail_read_first":
            steps.append(ActionStep("gmail_read_first", {}, False, "Read most recent email"))
        elif name == "gmail_send_email":
            steps.append(
                ActionStep(
                    "gmail_send_message",
                    {
                        "to": intent.entities.get("to", ""),
                        "subject": intent.entities.get("subject", "No subject"),
                        "body": intent.entities.get("body", ""),
                    },
                    False,
                    "Send Gmail email",
                )
            )
        elif name == "calendar_list_events":
            steps.append(
                ActionStep(
                    "calendar_list_events",
                    {"max_results": int(intent.entities.get("max_results", 10))},
                    False,
                    "List calendar events",
                )
            )
        elif name == "calendar_create_event":
            steps.append(
                ActionStep(
                    "calendar_create_event",
                    {
                        "summary": intent.entities.get("summary", ""),
                        "start_iso": intent.entities.get("start_iso", ""),
                        "end_iso": intent.entities.get("end_iso", ""),
                    },
                    False,
                    "Create calendar event",
                )
            )
        elif name == "calendar_delete_event":
            steps.append(
                ActionStep(
                    "calendar_delete_event",
                    {"event_id": intent.entities.get("event_id", "")},
                    False,
                    "Delete calendar event",
                )
            )

        elif name == "login":
            service = intent.entities.get("service", "")
            steps.append(
                ActionStep(
                    "autofill_login",
                    {"service": service},
                    False,
                    f"Login to {service} with saved credentials",
                )
            )

        return steps


def _resolve_app_name(app_name: str, context) -> str:
    if app_name in {"last", "previous"} and context and context.last_app:
        return context.last_app
    return app_name


def _is_mac() -> bool:
    return platform.system().lower() == "darwin"


def _primary_modifier() -> str:
    return "command" if _is_mac() else "ctrl"


def _reply_hotkey() -> list[str]:
    return [_primary_modifier(), "r"]


def _send_hotkey() -> list[str]:
    if _is_mac():
        return ["command", "shift", "d"]
    return ["ctrl", "enter"]


def _new_message_hotkey() -> list[str]:
    return [_primary_modifier(), "n"]


def _new_tab_hotkey() -> list[str]:
    return [_primary_modifier(), "t"]


def _close_tab_hotkey() -> list[str]:
    return [_primary_modifier(), "w"]


def _next_tab_hotkey() -> list[str]:
    return [_primary_modifier(), "tab"]


def _previous_tab_hotkey() -> list[str]:
    return [_primary_modifier(), "shift", "tab"]


def _refresh_hotkey() -> list[str]:
    return [_primary_modifier(), "r"]


def _back_hotkey() -> list[str]:
    if _is_mac():
        return ["command", "["]
    return ["alt", "left"]


def _forward_hotkey() -> list[str]:
    if _is_mac():
        return ["command", "]"]
    return ["alt", "right"]


def _copy_hotkey() -> list[str]:
    return [_primary_modifier(), "c"]


def _paste_hotkey() -> list[str]:
    return [_primary_modifier(), "v"]


def _cut_hotkey() -> list[str]:
    return [_primary_modifier(), "x"]


def _undo_hotkey() -> list[str]:
    return [_primary_modifier(), "z"]


def _redo_hotkey() -> list[str]:
    if _is_mac():
        return ["command", "shift", "z"]
    return ["ctrl", "y"]


def _select_all_hotkey() -> list[str]:
    return [_primary_modifier(), "a"]


def _minimize_hotkey() -> list[str]:
    if _is_mac():
        return ["command", "m"]
    return ["alt", "space", "n"]


def _maximize_hotkey() -> list[str]:
    if _is_mac():
        return ["control", "command", "f"]
    return ["alt", "space", "x"]
