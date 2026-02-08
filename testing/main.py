import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT))

from bridge import load_plugins

USER_CONFIG = {
    "reminders-mcp": {},
    "notes-mcp": {},
}


def _parse_date_time(date_str: str, time_str: str) -> str | None:
    """Combine date (YYYY-MM-DD) and time (HH:MM or H:MM AM/PM) into ISO-like string for the plugin."""
    if not date_str.strip() or not time_str.strip():
        return None
    from datetime import datetime
    date_str = date_str.strip()
    time_str = time_str.strip()
    try:
        # Accept HH:MM or H:MM
        if " " in time_str and ("am" in time_str.lower() or "pm" in time_str.lower()):
            dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")
        else:
            dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        return dt.strftime("%Y-%m-%dT%H:%M")
    except ValueError:
        return None


async def run_reminder_flow(tool_map, loop):
    """Prompt for reminder details and create reminder (with optional date/time)."""
    list_name = await loop.run_in_executor(
        None, lambda: input("Reminder list name: ").strip()
    )
    if not list_name:
        print("No list name. Exiting.")
        return

    name = await loop.run_in_executor(
        None, lambda: input("Reminder title: ").strip()
    )
    if not name:
        print("No reminder title. Exiting.")
        return

    body = await loop.run_in_executor(
        None, lambda: input("Reminder notes (optional): ").strip()
    )

    date_str = await loop.run_in_executor(
        None, lambda: input("Due date (YYYY-MM-DD, or leave blank): ").strip()
    )
    time_str = await loop.run_in_executor(
        None, lambda: input("Due time (HH:MM or 3:00 PM, or leave blank): ").strip()
    )
    due_date_iso = _parse_date_time(date_str, time_str) if date_str and time_str else None

    result = await tool_map["reminders_create_reminder"](
        list_name=list_name,
        name=name,
        body=body,
        due_date_iso=due_date_iso,
    )
    print(f"Added: \"{result['name']}\" to list \"{result['list']}\".")


async def run_tester(tool_map, loop):
    """Create one reminder and one note, then list both."""
    print("\n--- Tester: Reminders + Notes ---\n")

    # Reminder
    list_name = "Tester"
    await tool_map["reminders_create_reminder"](
        list_name=list_name,
        name="Test reminder from script",
        body="Created by main.py tester",
        due_date_iso=None,
    )
    print("Created reminder: \"Test reminder from script\" in list \"Tester\"")
    lists = await tool_map["reminders_list_lists"]()
    print("Reminder lists:", lists)
    reminders = await tool_map["reminders_list_reminders"](list_name)
    print("Reminders in Tester:", reminders)

    # Note (use first folder or "Notes" which usually exists)
    folders = await tool_map["notes_list_folders"]()
    folder = folders[0] if folders else "Notes"
    await tool_map["notes_create_note"](
        folder_name=folder,
        title="Test note from script",
        body="Created by main.py tester",
    )
    print(f"\nCreated note: \"Test note from script\" in folder \"{folder}\"")
    print("Notes folders:", folders)
    notes = await tool_map["notes_list_notes"](folder)
    print(f"Notes in {folder}:", notes[:10], "..." if len(notes) > 10 else "")

    print("\n--- Tester done ---\n")


async def main():
    tools = load_plugins(ROOT / "plugins", USER_CONFIG)
    tool_map = {tool["name"]: tool["fn"] for tool in tools}
    loop = asyncio.get_event_loop()

    choice = await loop.run_in_executor(
        None, lambda: input("(1) Add reminder  (2) Run tester: ").strip()
    )

    if choice == "2":
        await run_tester(tool_map, loop)
    else:
        await run_reminder_flow(tool_map, loop)


if __name__ == "__main__":
    asyncio.run(main())
