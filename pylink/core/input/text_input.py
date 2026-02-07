import time


def read_text_input(prompt: str = "PixelLink> ") -> dict:
    raw_text = input(prompt).strip()
    normalized = " ".join(raw_text.split())
    return {
        "raw_text": normalized,
        "timestamp": time.time(),
        "source": "text",
    }
