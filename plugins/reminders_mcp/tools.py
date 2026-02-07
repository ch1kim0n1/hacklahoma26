import asyncio
import subprocess

def _run_applescript(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout or "AppleScript failed")
    return (result.stdout or "").strip()


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def list_lists_tool():
    async def list_lists():
        script = 'tell application "Reminders" to get name of every list'
        out = await asyncio.to_thread(_run_applescript, script)
        if not out:
            return []
        return [n.strip() for n in out.split(", ")]

    return {
        "name": "reminders_list_lists",
        "description": "List all Apple Reminders list names",
        "fn": list_lists,
    }


def list_reminders_tool():
    async def list_reminders(list_name: str):
        escaped = _escape(list_name)
        script = f'tell application "Reminders" to get name of every reminder in list "{escaped}"'
        out = await asyncio.to_thread(_run_applescript, script)
        if not out:
            return []
        return [n.strip() for n in out.split(", ")]

    return {
        "name": "reminders_list_reminders",
        "description": "List reminder titles in an Apple Reminders list",
        "fn": list_reminders,
    }


def _ensure_list(list_name: str) -> None:
    """Create the list if it doesn't exist."""
    lists_script = 'tell application "Reminders" to get name of every list'
    out = _run_applescript(lists_script)
    existing = [n.strip() for n in out.split(", ")] if out else []
    if list_name in existing:
        return
    escaped = _escape(list_name)
    create_script = f'tell application "Reminders" to make new list with properties {{name:"{escaped}"}}'
    _run_applescript(create_script)


def create_reminder_tool():
    async def create_reminder(
        list_name: str,
        name: str,
        body: str = "",
        due_date_iso: str | None = None,
    ):
        await asyncio.to_thread(_ensure_list, list_name)
        escaped_list = _escape(list_name)
        escaped_name = _escape(name)
        escaped_body = _escape(body) if body else ""
        props = [f'name:"{escaped_name}"']
        if escaped_body:
            props.append(f'body:"{escaped_body}"')
        if due_date_iso:
            # AppleScript date format: "Thursday, December 19, 2019 at 12:00:00 PM"
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(due_date_iso.replace("Z", "+00:00"))
                # Use local time for Reminders
                date_str = dt.strftime("%A, %B %d, %Y at %I:%M:%S %p")
                props.append(f'due date:(date "{date_str}")')
            except ValueError:
                pass
        props_str = ", ".join(props)
        script = (
            f'tell application "Reminders" to make new reminder at end of list "{escaped_list}" '
            f'with properties {{{props_str}}}'
        )
        await asyncio.to_thread(_run_applescript, script)
        return {"created": True, "list": list_name, "name": name}

    return {
        "name": "reminders_create_reminder",
        "description": "Create a new reminder in an Apple Reminders list (optional due_date_iso)",
        "fn": create_reminder,
    }
