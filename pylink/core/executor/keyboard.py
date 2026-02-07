import pyautogui

pyautogui.FAILSAFE = True


class KeyboardController:
    def type_text(self, content: str, interval: float = 0.02) -> None:
        if content:
            # Use write() instead of typewrite() to support special characters and unicode
            pyautogui.write(content, interval=interval)

    def press(self, key: str) -> None:
        pyautogui.press(key)

    def hotkey(self, keys: list[str]) -> None:
        if keys:
            pyautogui.hotkey(*keys)
