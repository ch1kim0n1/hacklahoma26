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
