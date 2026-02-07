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


def list_folders_tool():
    async def list_folders():
        script = 'tell application "Notes" to get name of every folder of account 1'
        out = await asyncio.to_thread(_run_applescript, script)
        if not out:
            return []
        return [n.strip() for n in out.split(", ")]

    return {
        "name": "notes_list_folders",
        "description": "List Apple Notes folder names (account 1)",
        "fn": list_folders,
    }


def list_notes_tool():
    async def list_notes(folder_name: str):
        escaped = _escape(folder_name)
        script = f'tell application "Notes" to get name of every note of folder "{escaped}" of account 1'
        out = await asyncio.to_thread(_run_applescript, script)
        if not out:
            return []
        return [n.strip() for n in out.split(", ")]

    return {
        "name": "notes_list_notes",
        "description": "List note titles in an Apple Notes folder",
        "fn": list_notes,
    }


def create_note_tool():
    async def create_note(folder_name: str, title: str, body: str = ""):
        escaped_folder = _escape(folder_name)
        escaped_title = _escape(title)
        escaped_body = _escape(body) if body else ""
        script = (
            f'tell application "Notes" to make new note at folder "{escaped_folder}" of account 1 '
            f'with properties {{name:"{escaped_title}", body:"{escaped_body}"}}'
        )
        await asyncio.to_thread(_run_applescript, script)
        return {"created": True, "folder": folder_name, "title": title}

    return {
        "name": "notes_create_note",
        "description": "Create a new note in an Apple Notes folder",
        "fn": create_note,
    }
