# PixelLink Electron App

## Run

```bash
cd /Users/pomoika/Documents/hack/hacklahoma26/electron
npm install
npm run start
```

Dry-run mode (safe for testing UI without OS automation):

```bash
npm run start:dry-run
```

## What It Includes
- PixelLink floating launcher button (bottom-right).
- Minimal console window with color-coded status + logs.
- Compact command input for sending intents.
- Live runtime stream from the local Python backend.

## Architecture
- `main.js`: Electron main process, Python bridge process, launcher/main windows.
- `preload.js`: Safe IPC API for renderer.
- `renderer/index.html`: Minimal PixelLink console.
- `renderer/launcher.html`: Floating launcher button window.
- Python bridge target: `/Users/pomoika/Documents/hack/hacklahoma26/pylink/desktop_bridge.py`.

## Usage
1. Start the app with `npm run start`.
2. Click the floating `P` launcher button to open the PixelLink console.
3. Enter commands in the console; logs and status update in real time.

## Blind Mode

Blind Mode is a desktop-first non-visual interaction mode with voice guidance and screen-reader announcements.

### Enable
1. Open the PixelLink console.
2. Turn on the **Blind Mode** toggle in preferences.
3. Blind Mode stays enabled across app restarts.

### Non-visual controls
- Voice commands:
  - `enable blind mode`
  - `disable blind mode`
  - `read status`
  - `repeat last response`
  - `blind help`
- Keyboard shortcuts:
  - `V` start voice capture
  - `S` read status
  - `R` repeat last response

### Safety behavior
- Sensitive actions require explicit `confirm` or `cancel`.
- When Blind Mode is enabled, PixelLink forces voice output on.
- If TTS/STT is unavailable, PixelLink emits assertive guidance announcements.

### Troubleshooting
- If voice input fails, verify microphone permission for Electron/Terminal.
- If voice output is silent, check your TTS provider/API settings.
- If screen-reader announcements are not read, verify VoiceOver/NVDA is enabled.
