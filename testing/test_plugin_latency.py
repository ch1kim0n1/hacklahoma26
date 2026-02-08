from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plugins.notes_mcp import tools as notes_tools
from plugins.reminders_mcp import tools as reminders_tools


def test_reminders_list_cache_reduces_roundtrips(monkeypatch) -> None:
    calls = {"list": 0, "create": 0}

    def fake_run(script: str) -> str:
        if "name of every list" in script:
            calls["list"] += 1
            return "Reminders"
        if "make new list" in script:
            return ""
        if "make new reminder" in script:
            calls["create"] += 1
            return ""
        return ""

    monkeypatch.setattr(reminders_tools, "_run_applescript", fake_run)
    reminders_tools._LISTS_CACHE["expires_at"] = 0.0
    reminders_tools._LISTS_CACHE["lists"] = []

    tool = reminders_tools.create_reminder_tool()["fn"]
    asyncio.run(tool(list_name="Reminders", name="A", body="", due_date_iso=None))
    asyncio.run(tool(list_name="Reminders", name="B", body="", due_date_iso=None))

    assert calls["create"] == 2
    # First call fetches lists, second call should use cache.
    assert calls["list"] == 1


def test_notes_folder_cache_reduces_roundtrips(monkeypatch) -> None:
    calls = {"folders": 0, "create": 0}

    def fake_run(script: str) -> str:
        if "name of every folder" in script:
            calls["folders"] += 1
            return "Notes, Work"
        if "make new folder" in script:
            return ""
        if "make new note" in script:
            calls["create"] += 1
            return ""
        return ""

    monkeypatch.setattr(notes_tools, "_run_applescript", fake_run)
    notes_tools._FOLDERS_CACHE["expires_at"] = 0.0
    notes_tools._FOLDERS_CACHE["folders"] = []

    tool = notes_tools.create_note_tool()["fn"]
    asyncio.run(tool(folder_name="Notes", title="A", body=""))
    asyncio.run(tool(folder_name="Notes", title="B", body=""))

    assert calls["create"] == 2
    assert calls["folders"] == 1
