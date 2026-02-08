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
                    "mcp_create_reminder",
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
                    "mcp_create_note",
                    params,
                    False,
                    f"Create note '{params['title']}' in {params['folder_name']}",
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

        elif name == "reschedule_tasks":
            # Handled by orchestrator directly (needs emotional intelligence engine)
            steps.append(
                ActionStep(
                    "emotional_reschedule",
                    {
                        "target": intent.entities.get("target", "heavy"),
                        "target_day": intent.entities.get("target_day", "tomorrow"),
                    },
                    False,
                    "Analyze and reschedule tasks based on emotional state",
                )
            )

        elif name == "lighten_load":
            steps.append(
                ActionStep(
                    "emotional_lighten",
                    {"scope": intent.entities.get("scope", "today")},
                    False,
                    "Analyze workload and suggest reductions",
                )
            )

        elif name == "check_schedule":
            steps.append(
                ActionStep(
                    "mcp_get_events",
                    {"timeframe": intent.entities.get("timeframe", "today")},
                    False,
                    "Fetch and display schedule",
                )
            )

        elif name == "emotional_check_in":
            steps.append(
                ActionStep(
                    "emotional_check_in",
                    {},
                    False,
                    "Generate comprehensive emotional intelligence report",
                )
            )

        # Browser automation intents (AI-powered)
        elif name == "browser_task":
            instruction = intent.entities.get("instruction", "")
            url = intent.entities.get("url")
            steps.append(
                ActionStep(
                    "browser_task",
                    {"instruction": instruction, "url": url},
                    False,
                    "Execute browser automation task",
                )
            )

        elif name == "browser_fill_form":
            form_type = intent.entities.get("form_type", "form")
            fields = intent.entities.get("fields", {})
            instruction = intent.entities.get("instruction", "")
            steps.append(
                ActionStep(
                    "browser_fill_form",
                    {"form_type": form_type, "fields": fields, "instruction": instruction},
                    False,
                    f"Fill out {form_type} form",
                )
            )

        elif name == "browser_click":
            element = intent.entities.get("element", "")
            instruction = intent.entities.get("instruction", "")
            steps.append(
                ActionStep(
                    "browser_click",
                    {"element": element, "instruction": instruction},
                    False,
                    f"Click on {element}",
                )
            )

        elif name == "browser_extract":
            content_type = intent.entities.get("content_type", "main content")
            instruction = intent.entities.get("instruction", "")
            steps.append(
                ActionStep(
                    "browser_extract",
                    {"content_type": content_type, "instruction": instruction},
                    False,
                    f"Extract {content_type} from page",
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
