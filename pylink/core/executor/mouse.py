import pyautogui

pyautogui.FAILSAFE = True


class MouseController:
    def move_to(self, x: int, y: int, duration: float = 0.2) -> None:
        pyautogui.moveTo(x, y, duration=duration)

    def click(self, x: int | None = None, y: int | None = None, button: str = "left") -> None:
        if x is None or y is None:
            pyautogui.click(button=button)
        else:
            pyautogui.click(x, y, button=button)
