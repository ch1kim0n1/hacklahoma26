import platform
import subprocess
from typing import Optional
from urllib.parse import urlparse


class OSController:
    # Common app name whitelist for validation (can be extended)
    COMMON_APPS = {
        "notes", "mail", "safari", "chrome", "google chrome", "firefox",
        "terminal", "iterm", "vscode", "code", "slack", "spotify",
        "calendar", "messages", "notepad", "word", "excel", "powerpoint",
        "outlook",
    }

    # Map common shorthand names to actual macOS application names
    APP_NAME_ALIASES = {
        "chrome": "Google Chrome",
        "vscode": "Visual Studio Code",
        "code": "Visual Studio Code",
        "iterm": "iTerm",
        "word": "Microsoft Word",
        "excel": "Microsoft Excel",
        "powerpoint": "Microsoft PowerPoint",
        "outlook": "Microsoft Outlook",
        "teams": "Microsoft Teams",
    }

    def _resolve_app_name(self, app_name: str) -> str:
        """Resolve common app name aliases to actual macOS app names."""
        if platform.system().lower() != "darwin":
            return app_name
        return self.APP_NAME_ALIASES.get(app_name.lower(), app_name)

    def _validate_app_name(self, app_name: str) -> None:
        """Validate app name to prevent shell injection"""
        if not app_name:
            raise ValueError("App name cannot be empty")

        # Check for shell metacharacters that could be dangerous
        dangerous_chars = [";", "|", "&", "$", "`", "(", ")", "<", ">", "\n", "\r"]
        for char in dangerous_chars:
            if char in app_name:
                raise ValueError(f"Invalid app name: contains dangerous character '{char}'")
    
    def is_app_running(self, app_name: str) -> bool:
        """Check if an application is currently running."""
        if not app_name:
            return False

        self._validate_app_name(app_name)
        app_name = self._resolve_app_name(app_name)
        system = platform.system().lower()
        
        try:
            if system == "darwin":
                # Use osascript to check if app is running
                result = subprocess.run(
                    ["osascript", "-e", f'tell application "System Events" to (name of processes) contains "{app_name}"'],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                return result.stdout.strip().lower() == "true"
            elif system == "windows":
                result = subprocess.run(
                    ["tasklist", "/FI", f"IMAGENAME eq {app_name}.exe"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                return app_name.lower() in result.stdout.lower()
            else:  # Linux
                result = subprocess.run(
                    ["pgrep", "-f", app_name],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                return bool(result.stdout.strip())
        except Exception:
            # If we can't determine, assume not running (will try to open)
            return False

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError(f"Unsupported URL scheme for '{url}'")
        if not parsed.netloc:
            raise ValueError(f"Invalid URL '{url}'")

    def open_app(self, app_name: str) -> None:
        if not app_name:
            raise ValueError("App name is required")

        self._validate_app_name(app_name)
        app_name = self._resolve_app_name(app_name)

        # Check if app is already running - if so, just focus it
        if self.is_app_running(app_name):
            try:
                self.focus_app(app_name)
                return  # App was already running, we focused it
            except Exception:
                # If focus fails, fall through to opening
                pass
        
        system = platform.system().lower()

        try:
            if system == "darwin":
                result = subprocess.run(
                    ["open", "-a", app_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True
                )
            elif system == "windows":
                result = subprocess.run(
                    ["cmd", "/c", "start", "", app_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True
                )
            else:  # Linux
                result = subprocess.run(
                    ["xdg-open", app_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True
                )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Timeout: Failed to open app '{app_name}' (took longer than 5 seconds)")
        except subprocess.CalledProcessError as e:
            error_output = e.stderr.strip() if e.stderr else str(e)
            raise RuntimeError(f"Failed to open app '{app_name}': {error_output}")
        except FileNotFoundError:
            raise RuntimeError(f"App '{app_name}' not found or not installed")
        except PermissionError:
            raise RuntimeError(f"Permission denied: Cannot open app '{app_name}'. Check accessibility permissions.")

    def focus_app(self, app_name: str) -> None:
        if not app_name:
            raise ValueError("App name is required")

        self._validate_app_name(app_name)
        app_name = self._resolve_app_name(app_name)
        system = platform.system().lower()

        if system == "darwin":
            try:
                # First open the app
                subprocess.run(
                    ["open", "-a", app_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True
                )
                # Then activate/focus it
                subprocess.run(
                    ["osascript", "-e", f'tell application "{app_name}" to activate'],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True
                )
            except subprocess.CalledProcessError as e:
                error_output = e.stderr.strip() if e.stderr else str(e)
                raise RuntimeError(f"Failed to focus app '{app_name}': {error_output}")
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"Timeout: Failed to focus app '{app_name}'")
        else:
            # For Windows/Linux, opening is the same as focusing
            self.open_app(app_name)

    def close_app(self, app_name: str) -> None:
        if not app_name:
            raise ValueError("App name is required")
        self._validate_app_name(app_name)
        app_name = self._resolve_app_name(app_name)
        system = platform.system().lower()
        try:
            if system == "darwin":
                subprocess.run(
                    ["osascript", "-e", f'tell application "{app_name}" to quit'],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True,
                )
            elif system == "windows":
                subprocess.run(
                    ["taskkill", "/IM", f"{app_name}.exe", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True,
                )
            else:
                subprocess.run(
                    ["pkill", "-f", app_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=True,
                )
        except subprocess.CalledProcessError as e:
            error_output = e.stderr.strip() if e.stderr else str(e)
            raise RuntimeError(f"Failed to close app '{app_name}': {error_output}")

    def open_url(self, url: str) -> None:
        if not url:
            raise ValueError("URL is required")
        self._validate_url(url)
        system = platform.system().lower()
        try:
            if system == "darwin":
                subprocess.run(["open", url], capture_output=True, text=True, timeout=5, check=True)
            elif system == "windows":
                subprocess.run(["cmd", "/c", "start", "", url], capture_output=True, text=True, timeout=5, check=True)
            else:
                subprocess.run(["xdg-open", url], capture_output=True, text=True, timeout=5, check=True)
        except subprocess.CalledProcessError as e:
            error_output = e.stderr.strip() if e.stderr else str(e)
            raise RuntimeError(f"Failed to open URL '{url}': {error_output}")

    def open_file(self, file_path: str) -> None:
        if not file_path:
            raise ValueError("File path is required")
        system = platform.system().lower()
        try:
            if system == "darwin":
                subprocess.run(["open", file_path], capture_output=True, text=True, timeout=5, check=True)
            elif system == "windows":
                subprocess.run(["cmd", "/c", "start", "", file_path], capture_output=True, text=True, timeout=5, check=True)
            else:
                subprocess.run(["xdg-open", file_path], capture_output=True, text=True, timeout=5, check=True)
        except subprocess.CalledProcessError as e:
            error_output = e.stderr.strip() if e.stderr else str(e)
            raise RuntimeError(f"Failed to open file '{file_path}': {error_output}")

    def send_text_native(self, app_name: str, target: str, content: str) -> None:
        system = platform.system().lower()
        if system != "darwin":
            raise RuntimeError("Native text sending is currently only supported on macOS")
        _ = app_name

        safe_target = _escape_applescript_text(target)
        safe_content = _escape_applescript_text(content)

        script = f'''
set targetQuery to "{safe_target}"
set messageText to "{safe_content}"
set matchedBuddy to missing value
set resolvedHandle to ""

on normalize_phone(rawValue)
    set cleaned to do shell script "echo " & quoted form of rawValue & " | tr -cd '0-9+'"
    return cleaned
end normalize_phone

on find_contact_handle(nameQuery)
    tell application "Contacts"
        set queryTokens to words of nameQuery
        repeat with p in people
            set personName to ""
            try
                set personName to (name of p as text)
            end try

            set allTokensMatch to true
            repeat with tk in queryTokens
                set tokenText to contents of tk
                if tokenText is not "" then
                    ignoring case
                        if personName does not contain tokenText then
                            set allTokensMatch to false
                            exit repeat
                        end if
                    end ignoring
                end if
            end repeat

            if allTokensMatch then
                try
                    set phoneValue to value of first phone of p as text
                    if phoneValue is not "" then
                        return my normalize_phone(phoneValue)
                    end if
                end try
                try
                    set emailValue to value of first email of p as text
                    if emailValue is not "" then
                        return emailValue
                    end if
                end try
            end if
        end repeat
    end tell
    return ""
end find_contact_handle

tell application "Messages"
    activate
    repeat with svc in services
        try
            repeat with b in buddies of svc
                set buddyName to ""
                set buddyHandle to ""
                try
                    set buddyName to (name of b as text)
                end try
                try
                    set buddyHandle to (handle of b as text)
                end try
                ignoring case
                    if buddyName contains targetQuery or buddyHandle contains targetQuery then
                        set matchedBuddy to b
                        exit repeat
                    end if
                end ignoring
            end repeat
        end try
        if matchedBuddy is not missing value then exit repeat
    end repeat

    if matchedBuddy is missing value then
        set resolvedHandle to my find_contact_handle(targetQuery)
        if resolvedHandle is not "" then
            repeat with svc in services
                try
                    set maybeBuddy to buddy resolvedHandle of svc
                    if maybeBuddy is not missing value then
                        set matchedBuddy to maybeBuddy
                        exit repeat
                    end if
                end try
            end repeat
        end if
    end if

    if matchedBuddy is missing value then
        error "No matching Messages contact found for '" & targetQuery & "'. Use a more specific contact name."
    end if

    send messageText to matchedBuddy
end tell
'''
        try:
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=8,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            error_output = e.stderr.strip() if e.stderr else str(e)
            raise RuntimeError(f"Failed to send text in '{app_name}': {error_output}")

    def run_shell(self, command: list[str]) -> Optional[subprocess.Popen]:
        """Execute shell command with validation. Use with extreme caution."""
        if not command:
            return None

        # Basic validation - reject commands with suspicious patterns
        cmd_str = " ".join(command)
        if any(pattern in cmd_str for pattern in ["rm -rf", "format", "delete", "del /f"]):
            raise ValueError(f"Blocked potentially dangerous command: {cmd_str}")

        try:
            return subprocess.Popen(command, capture_output=True, text=True)
        except Exception as e:
            raise RuntimeError(f"Failed to execute shell command: {str(e)}")


def _escape_applescript_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ").replace("\r", " ")
