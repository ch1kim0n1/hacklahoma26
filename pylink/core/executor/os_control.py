import platform
import subprocess
import re
from typing import Optional


class OSController:
    # Common app name whitelist for validation (can be extended)
    COMMON_APPS = {
        "notes", "mail", "safari", "chrome", "firefox", "terminal", "iterm",
        "vscode", "code", "slack", "spotify", "calendar", "messages",
        "notepad", "word", "excel", "powerpoint", "outlook"
    }

    def _validate_app_name(self, app_name: str) -> None:
        """Validate app name to prevent shell injection"""
        if not app_name:
            raise ValueError("App name cannot be empty")

        # Check for shell metacharacters that could be dangerous
        dangerous_chars = [";", "|", "&", "$", "`", "(", ")", "<", ">", "\n", "\r"]
        for char in dangerous_chars:
            if char in app_name:
                raise ValueError(f"Invalid app name: contains dangerous character '{char}'")

    def open_app(self, app_name: str) -> None:
        if not app_name:
            raise ValueError("App name is required")

        self._validate_app_name(app_name)
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
