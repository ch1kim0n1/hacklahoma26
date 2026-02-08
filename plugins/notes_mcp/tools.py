import asyncio
import subprocess
import time

_FOLDERS_CACHE: dict[str, object] = {"expires_at": 0.0, "folders": []}
_CACHE_TTL_SECONDS = 30.0


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


def _read_folders_uncached() -> list[str]:
    script = 'tell application "Notes" to get name of every folder of account 1'
    out = _run_applescript(script)
    if not out:
        return []
    return [n.strip() for n in out.split(", ")]


def _read_folders_cached(force: bool = False) -> list[str]:
    now = time.monotonic()
    if not force and _FOLDERS_CACHE["expires_at"] > now:
        return list(_FOLDERS_CACHE["folders"])

    folders = _read_folders_uncached()
    _FOLDERS_CACHE["folders"] = folders
    _FOLDERS_CACHE["expires_at"] = now + _CACHE_TTL_SECONDS
    return list(folders)


def _ensure_folder_exists(folder_name: str) -> None:
    folders = _read_folders_cached()
    if folder_name in folders:
        return
    escaped = _escape(folder_name)
    script = f'tell application "Notes" to make new folder with properties {{name:"{escaped}"}}'
    _run_applescript(script)
    _read_folders_cached(force=True)


def list_folders_tool():
    async def list_folders():
        return await asyncio.to_thread(_read_folders_cached)

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
        await asyncio.to_thread(_ensure_folder_exists, folder_name)
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
