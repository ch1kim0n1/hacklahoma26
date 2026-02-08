from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from core.agent import run_agent
from core.context.session import SessionContext
from core.executor.engine import ExecutionEngine
from core.nlu.intents import Intent
from core.nlu.llm_brain import parse_with_llm, respond_with_llm
from core.planner.action_planner import ActionPlanner
from core.safety.guard import KillSwitch, SafetyGuard

# Intents that benefit from the agent's dynamic tool calling (multi-step reasoning)
AGENT_INTENTS = frozenset({
    "unknown",
    "gmail_list_messages", "gmail_get_message", "gmail_send_email", "gmail_read_first",
    "calendar_list_events", "calendar_create_event", "calendar_delete_event",
    "create_reminder", "list_reminder_lists", "list_reminders",
    "create_note", "list_note_folders", "list_notes",
})


DEFAULT_PERMISSION_PROFILE = {
    "open_app": True,
    "focus_app": True,
    "close_app": True,
    "open_url": True,
    "open_file": True,
    "send_text_native": True,
    "type_text": True,
    "click": True,
    "right_click": True,
    "double_click": True,
    "scroll": True,
    "press_key": True,
    "hotkey": True,
    "send_email": True,
    "send_message": True,
    "wait": True,
    # MCP plugin tools
    "reminders_create_reminder": True,
    "reminders_list_lists": True,
    "reminders_list_reminders": True,
    "notes_create_note": True,
    "notes_list_folders": True,
    "notes_list_notes": True,
    "gmail_list_messages": True,
    "gmail_get_message": True,
    "gmail_send_message": True,
    "calendar_list_events": True,
    "calendar_create_event": True,
    "calendar_delete_event": True,
    "gmail_read_first": True,
    "autofill_login": True,
}


class PixelLinkRuntime:
    def __init__(
        self,
        *,
        dry_run: bool = False,
        speed: float = 1.0,
        permission_profile: dict[str, bool] | None = None,
        enable_kill_switch: bool = True,
        verbose: bool = True,
        mcp_tools: dict[str, Any] | None = None,
    ) -> None:
        self.session = SessionContext()
        self.guard = SafetyGuard()
        self.kill_switch = KillSwitch()
        if enable_kill_switch:
            self.kill_switch.start()
        self.enable_kill_switch = enable_kill_switch
        self.mcp_tools = mcp_tools or {}
        self.planner = ActionPlanner(mcp_tools=self.mcp_tools)
        self.executor = ExecutionEngine(self.kill_switch, dry_run=dry_run, verbose=verbose)
        self.executor.set_speed(speed)
        self.guard.set_allowed_actions(permission_profile or DEFAULT_PERMISSION_PROFILE)
        
        # Initialize file system context in background
        import threading
        threading.Thread(target=self.session.filesystem.index_files, daemon=True).start()

    def close(self) -> None:
        if self.enable_kill_switch:
            self.kill_switch.stop()

    def set_preferences(
        self,
        *,
        speed: float | None = None,
        permission_profile: dict[str, bool] | None = None,
    ) -> None:
        if speed is not None:
            self.executor.set_speed(speed)
        if permission_profile is not None:
            self.guard.set_allowed_actions(permission_profile)

    def handle_input(self, raw_text: str, source: str = "text") -> dict[str, Any]:
        cleaned_text = " ".join((raw_text or "").strip().split())
        if not cleaned_text:
            return self._response("idle", "No input provided.", source=source)

        if self.session.pending_clarification:
            return self._handle_clarification(cleaned_text, source)

        try:
            context = {"last_intent": self.session.history[-1].get("intent") if self.session.history else None}
            intent = parse_with_llm(cleaned_text, context)
        except Exception:
            intent = Intent(name="unknown", entities={"text": cleaned_text}, confidence=0.0, raw_text=cleaned_text)

        self.session.record_intent(intent.name, cleaned_text)

        if self.session.pending_steps:
            return self._handle_pending(intent.name, source)

        # Use the dynamic agent for tool-heavy intents (email, calendar, reminders, notes)
        # so it can reason and call tools in sequence (e.g. list emails → get 2nd → return subject)
        if intent.name in AGENT_INTENTS and self.mcp_tools:
            try:
                agent_response = run_agent(cleaned_text, self.mcp_tools)
                if agent_response:
                    return self._response(
                        "completed",
                        agent_response,
                        source=source,
                        intent=intent,
                    )
            except Exception as exc:
                pass  # Fall through to intent-specific handling

        if intent.name == "unknown":
            message = "Sorry, I didn't understand that."
            try:
                prev = self.session.history[-2] if len(self.session.history) >= 2 else None
                context = {"last_intent": prev.get("intent") if prev else None}
                message = respond_with_llm(cleaned_text, context)
            except Exception:
                pass  # Fall back to static message if LLM fails or is not configured
            return self._response(
                "unknown",
                message,
                source=source,
                intent=intent,
                suggestions=[
                    "open Notes",
                    "type Hello world",
                    "reply email saying I'll send the file tomorrow",
                    "create reminder Buy milk",
                    "create note Meeting notes in Work",
                    "browse for machine learning tutorials",
                    "find file report.pdf",
                    "login to github",
                ],
            )
        
        # Handle file search
        if intent.name == "search_file":
            query = intent.entities.get("query", "")
            matches = self.session.filesystem.search_files(query, limit=10)
            if matches:
                message = f"Found {len(matches)} file(s) matching '{query}':\n"
                for i, file_info in enumerate(matches[:5], 1):
                    message += f"  {i}. {file_info.name} ({file_info.path})\n"
                if len(matches) > 5:
                    message += f"  ... and {len(matches) - 5} more"
                return self._response("completed", message, source=source, intent=intent)
            else:
                return self._response(
                    "completed",
                    f"No files found matching '{query}'.",
                    source=source,
                    intent=intent,
                )        
        # Handle login/autofill
        if intent.name == "login":
            service = intent.entities.get("service", "")
            from core.context.password_manager import get_password_manager
            
            pm = get_password_manager()
            cred = pm.get_credential(service)
            
            if cred:
                # Create steps for autofill
                from core.planner.action_planner import ActionStep
                
                steps = [
                    ActionStep("type_text", {"content": cred.username}, False, "Enter username"),
                    ActionStep("press_key", {"key": "tab"}, False, "Move to password field"),
                    ActionStep("type_text", {"content": cred.password}, False, "Enter password"),
                ]
                
                result = self.executor.execute_steps(steps, self.guard)
                
                if result.completed:
                    return self._response(
                        "completed",
                        f"Autofilled credentials for {service} ({cred.username})",
                        source=source,
                        intent=intent,
                        steps=steps,
                    )
                else:
                    return self._response("error", "Failed to autofill credentials", source=source, intent=intent)
            else:
                return self._response(
                    "error",
                    f"No credentials found for '{service}' in password manager. Please add them to your Keychain first.",
                    source=source,
                    intent=intent,
                )
        if intent.name == "send_text":
            recipient = str(intent.entities.get("target", "")).strip()
            content = str(intent.entities.get("content", "")).strip()
            if not recipient:
                prompt = "Who should receive this text message?"
                self.session.set_pending_clarification(
                    {
                        "intent_name": "send_text",
                        "clarification_type": "send_text_target",
                        "target": "",
                        "content": content,
                        "app": intent.entities.get("app", "Messages"),
                        "prompt": prompt,
                        "original_text": cleaned_text,
                    }
                )
                return self._response(
                    "awaiting_clarification",
                    prompt,
                    source=source,
                    intent=intent,
                    pending_clarification=True,
                )
            if not content:
                prompt = f"What message should I send to {recipient}?"
                self.session.set_pending_clarification(
                    {
                        "intent_name": "send_text",
                        "clarification_type": "send_text_content",
                        "target": recipient,
                        "content": "",
                        "app": intent.entities.get("app", "Messages"),
                        "prompt": prompt,
                        "original_text": cleaned_text,
                    }
                )
                return self._response(
                    "awaiting_clarification",
                    prompt,
                    source=source,
                    intent=intent,
                    pending_clarification=True,
                )

        if intent.entities.get("requires_clarification"):
            prompt = intent.entities.get("clarification_prompt", "Please provide more details.")
            self.session.set_pending_clarification(
                {
                    "intent_name": intent.name,
                    "clarification_type": intent.entities.get("clarification_type", ""),
                    "target": intent.entities.get("target", ""),
                    "content": intent.entities.get("content", ""),
                    "app": intent.entities.get("app", "Messages"),
                    "prompt": prompt,
                    "original_text": cleaned_text,
                }
            )
            return self._response(
                "awaiting_clarification",
                prompt,
                source=source,
                intent=intent,
                pending_clarification=True,
            )

        return self._execute_intent(intent, source)

    def _execute_intent(self, intent: Intent, source: str) -> dict[str, Any]:
        steps = self.planner.plan(intent, self.session, self.guard)
        safety = self.guard.validate_plan(steps)
        if not safety.allowed:
            return self._response("blocked", safety.reason, source=source, intent=intent, steps=steps)

        # Track browsing history for search intents
        if intent.name in {"search_web", "search_youtube", "open_website"}:
            for step in steps:
                if step.action == "open_url":
                    url = step.params.get("url", "")
                    search_query = intent.entities.get("query", "")
                    self.session.add_browsing_entry(url, search_query=search_query)

        # Handle MCP plugin actions (async tools)
        mcp_actions = {"gmail_read_first"} | set(self.mcp_tools)
        if any(step.action in mcp_actions for step in steps):
            import asyncio
            result = asyncio.run(self._execute_mcp_steps(steps))
            if result.get("error"):
                return self._response("error", result["error"], source=source, intent=intent, steps=steps)
            return self._response(
                "completed",
                result.get("message", "Task completed successfully."),
                source=source,
                intent=intent,
                steps=steps,
            )

        result = self.executor.execute_steps(steps, self.guard)
        self._record_last_app(steps)

        if result.pending_steps:
            self.session.set_pending(result.pending_steps)
            return self._response(
                "awaiting_confirmation",
                "Awaiting confirmation to proceed.",
                source=source,
                intent=intent,
                steps=steps,
                pending_confirmation=True,
            )

        if result.completed:
            return self._response(
                "completed",
                "Task completed successfully.",
                source=source,
                intent=intent,
                steps=steps,
            )

        return self._response("error", "Task did not complete.", source=source, intent=intent, steps=steps)

    def _handle_clarification(self, user_reply: str, source: str) -> dict[str, Any]:
        if user_reply.lower() in {"cancel", "stop", "abort", "no", "nevermind", "never mind"}:
            self.session.clear_pending_clarification()
            return self._response("canceled", "Clarification canceled.", source=source)

        pending = self.session.pending_clarification or {}
        intent_name = pending.get("intent_name", "")
        clarification_type = pending.get("clarification_type", "")

        if intent_name == "send_text":
            target = (pending.get("target", "") or "").strip()
            content = (pending.get("content", "") or "").strip()
            app_name = (pending.get("app", "") or "Messages").strip()

            if clarification_type == "send_text_target":
                target = _clean_clarified_target(user_reply)
            elif clarification_type == "send_text_content":
                content = user_reply.strip()

            resolved_intent = Intent(
                name="send_text",
                entities={"target": target, "content": content, "app": app_name},
                confidence=0.9,
                raw_text=f"{pending.get('original_text', '')} | {user_reply}",
            )
            self.session.clear_pending_clarification()
            self.session.record_intent(resolved_intent.name, resolved_intent.raw_text)
            return self._execute_intent(resolved_intent, source)

        self.session.clear_pending_clarification()
        return self._response("error", "Unable to resolve clarification context.", source=source)

    def _handle_pending(self, intent_name: str, source: str) -> dict[str, Any]:
        if intent_name == "confirm":
            result = self.executor.execute_steps(self.session.pending_steps, self.guard)
            self.session.clear_pending()
            if result.completed:
                return self._response("completed", "Confirmed and completed.", source=source)
            return self._response("error", "Execution halted during confirmation.", source=source)
        if intent_name == "cancel":
            self.session.clear_pending()
            return self._response("canceled", "Pending actions canceled.", source=source)
        return self._response(
            "awaiting_confirmation",
            "Type confirm or cancel to continue.",
            source=source,
            pending_confirmation=True,
        )

    async def _execute_mcp_steps(self, steps: list[Any]) -> dict[str, Any]:
        """Execute MCP tool calls asynchronously."""
        try:
            for step in steps:
                if step.action == "gmail_read_first":
                    # Synthetic: list(1) then get first message
                    list_fn = self.mcp_tools.get("gmail_list_messages")
                    get_fn = self.mcp_tools.get("gmail_get_message")
                    if not list_fn or not get_fn:
                        return {"error": "Gmail tools not available"}
                    messages = await list_fn(max_results=1)
                    if not messages:
                        return {"message": "No emails found."}
                    msg_id = messages[0].get("id")
                    if not msg_id:
                        return {"message": "Could not get email."}
                    result = await get_fn(message_id=msg_id)
                    return {"message": _format_mcp_dict_result("gmail_get_message", result)}

                tool = self.mcp_tools.get(step.action)
                if not tool:
                    continue
                result = await tool(**step.params)
                # Format user-friendly message from tool result
                if isinstance(result, list):
                    return {"message": _format_mcp_list_result(step.action, result)}
                if isinstance(result, dict):
                    return {"message": _format_mcp_dict_result(step.action, result)}
                return {"message": str(result)}
            return {"message": "Task completed"}
        except Exception as e:
            return {"error": f"MCP execution failed: {str(e)}"}

    def _record_last_app(self, steps: list[Any]) -> None:
        for step in steps:
            if step.action in {"open_app", "focus_app"}:
                self.session.set_last_app(step.params.get("app", ""))
                break

    def _response(
        self,
        status: str,
        message: str,
        *,
        source: str,
        intent=None,
        steps=None,
        pending_confirmation: bool = False,
        pending_clarification: bool = False,
        suggestions: list[str] | None = None,
    ) -> dict[str, Any]:
        serialized_steps = []
        for step in steps or []:
            serialized_steps.append(
                {
                    "action": step.action,
                    "params": step.params,
                    "requires_confirmation": step.requires_confirmation,
                    "description": step.description,
                }
            )

        serialized_intent = None
        if intent is not None:
            serialized_intent = asdict(intent)

        return {
            "status": status,
            "message": message,
            "source": source,
            "intent": serialized_intent,
            "steps": serialized_steps,
            "pending_confirmation": pending_confirmation or bool(self.session.pending_steps),
            "pending_clarification": pending_clarification or bool(self.session.pending_clarification),
            "clarification_prompt": (self.session.pending_clarification or {}).get("prompt", ""),
            "last_app": self.session.last_app,
            "history_count": len(self.session.history),
            "suggestions": suggestions or [],
        }


def _format_mcp_list_result(action: str, items: list) -> str:
    """Format MCP list results for display."""
    if not items:
        return "No items found."
    if action == "gmail_list_messages":
        return f"Found {len(items)} email(s). Say 'read first email' or 'read email' to open one."
    if action == "calendar_list_events":
        lines = [f"• {e.get('summary', 'No title')} at {e.get('start', '?')}" for e in items[:5]]
        return "\n".join(lines) if lines else "No upcoming events."
    if action in ("reminders_list_lists", "notes_list_folders"):
        return "Available: " + ", ".join(str(x) for x in items[:15])
    if action in ("reminders_list_reminders", "notes_list_notes"):
        return "Found: " + ", ".join(str(x) for x in items[:10])
    return f"Found {len(items)} item(s)."


def _format_mcp_dict_result(action: str, result: dict) -> str:
    """Format MCP dict results for display."""
    if action == "gmail_get_message":
        return f"From: {result.get('from', '?')}\nSubject: {result.get('subject', '?')}\n{result.get('snippet', result.get('body', ''))[:500]}"
    if action in ("reminders_create_reminder", "notes_create_note"):
        return f"Created '{result.get('name', result.get('title', '?'))}' successfully."
    if action == "calendar_create_event":
        return f"Event created: {result.get('htmlLink', 'Done')}"
    if action == "gmail_send_message":
        return "Email sent."
    return str(result)


def _clean_clarified_target(value: str) -> str:
    cleaned = re.sub(r"^\s*to\s+", "", value.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\b(?:in|on|via)\s+(?:i\s*message|imessage|imeesage|imesage|messages?)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = " ".join(cleaned.split())
    return cleaned.strip().strip('"').strip("'").strip("“”")
