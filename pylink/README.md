# PixelLink MVP

**An intent-driven accessibility operating layer for hands-free computer control**

PixelLink enables people with disabilities to control computers using natural language intent, not physical input.

---

## Accessibility Persona

**Alex** has limited hand mobility due to a repetitive stress injury. Alex needs to reply to emails and take notes without relying on a keyboard or mouse. PixelLink allows Alex to control the computer using voice-to-text input and natural language commands.

---

## Prerequisites

### Required
- **Python 3.10 or higher**
- **Operating System**: macOS (recommended), Windows, or Linux
  - ✅ **macOS**: Fully supported and tested
  - ⚠️ **Windows/Linux**: Experimental support (not fully tested)

### macOS Specific Requirements
**Critical**: You must enable Accessibility permissions for Terminal (or your Python environment):

1. Open **System Preferences** → **Security & Privacy** → **Accessibility**
2. Click the lock icon to make changes
3. Add **Terminal** (or **iTerm**, **VS Code**, etc.) to the list
4. Restart your terminal

**Without this, the kill switch (ESC key) will not work.**

---

## Installation

### 1. Clone or Navigate to the Repository
```bash
cd /path/to/hacklahoma26/pylink
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

Dependencies:
- `pyautogui>=0.9.54` - Keyboard and mouse automation
- `pynput>=1.7.7` - Kill switch (ESC key detection)

### 3. Verify Installation
```bash
python main.py
```

You should see:
```
PixelLink MVP - Running on Darwin
✓ macOS detected (recommended)
⚠ Note: Ensure accessibility permissions are enabled for Terminal/Python

PixelLink started. Type 'exit' to quit. Press ESC for kill switch.
PixelLink>
```

---

## Usage

### Interactive Mode (Manual Testing)

Run the main CLI application:
```bash
python main.py
```

**Example Commands:**
```
open Notes
type Hello, this is a test
open Mail
reply email saying I'll send the file tomorrow
confirm
```

**Built-in Commands:**
- Type `exit` or `quit` to stop
- Press **ESC** at any time to trigger the emergency kill switch

---

### Demo Mode (Automated Workflow)

Run the single-step demo:
```bash
python demo/demo_workflow.py
```

**What it does:**
- Prompts for a single command
- Parses intent
- Shows planned steps
- Executes the action

**Try:**
```
open Notes
```

---

## Supported Intents

| Intent | Example Commands | Description |
|--------|-----------------|-------------|
| **open_app** | `open Notes`, `launch Safari`, `start Mail` | Opens an application |
| **focus_app** | `focus Mail`, `switch to Chrome` | Focuses/activates an application |
| **type_text** | `type Hello world`, `write test@example.com` | Types text into the active application |
| **click** | `click` | Clicks at the current mouse position |
| **reply_email** | `reply email saying I'm on it` | Opens reply in Mail, types content, awaits confirmation |
| **confirm** | `confirm`, `yes`, `ok` | Confirms pending action (e.g., sending email) |
| **cancel** | `cancel`, `no`, `stop` | Cancels pending action |

---

## MVP Workflow (Hands-Free Note Creation)

**Goal**: Demonstrate hands-free control for Alex

1. **User says (via voice-to-text)**: "open Notes"
   - PixelLink opens and focuses the Notes app

2. **User says**: "type This is my note for today"
   - PixelLink types the content into the active note

3. **Done!** Alex has created a note without using hands.

---

## Safety Features

### Kill Switch
- Press **ESC** at any time to immediately halt execution
- Prevents runaway automation

### Blocked Actions
The following actions are **permanently blocked**:
- `delete_file`
- `shutdown_system`
- `format_drive`

### Confirmation Required
Certain actions require explicit user confirmation:
- `send_email`
- `reply_email` (before sending)

When confirmation is needed:
```
Awaiting confirmation to proceed. Type 'confirm' or 'cancel'.
```

---

## Troubleshooting

### "Permission denied" or "Cannot open app"
**macOS**: Enable Accessibility permissions (see Prerequisites above)

### "App not found"
**Solution**: Use the exact app name as it appears in `/Applications`:
- ✅ `open Notes` (correct)
- ❌ `open notes.app` (incorrect)
- ✅ `open Safari` (correct)

### "I typed a command but nothing happened"
**Check**:
1. Did you see "Parsed intent: Intent(...)"?
2. Did you see "Planned steps"?
3. Did execution start?

If no output, the intent wasn't recognized. Try:
```
open <app>
type <text>
reply email saying <message>
```

### Kill switch (ESC) doesn't work
**macOS**: Accessibility permissions not enabled. See Prerequisites.

### Special characters not typing correctly
**Fixed in current version**. If issues persist, ensure you're using Python 3.10+.

---

## Logs

All actions are logged to:
```
logs/pixelink-YYYYMMDD.log
```

**View today's log:**
```bash
cat logs/pixelink-$(date +%Y%m%d).log
```

**Log format:**
```
2026-02-07 14:32:15 | INFO | Intent: open_app | Steps: ['open_app']
2026-02-07 14:32:16 | INFO | Executing step 1/1: open_app
```

---

## Project Structure

```
pylink/
├── core/
│   ├── input/          # Text input handling
│   ├── nlu/            # Intent parsing
│   ├── planner/        # Action planning
│   ├── executor/       # OS-level execution (keyboard, mouse, apps)
│   ├── safety/         # Kill switch and safety guard
│   └── context/        # Session context (last app, history)
├── demo/               # Demo workflows
├── logs/               # Execution logs
├── main.py             # Interactive CLI
└── requirements.txt    # Dependencies
```

---

## Known Limitations (MVP)

### Not Implemented
- Voice input (use external voice-to-text like macOS Dictation)
- Phone controller
- Facial gesture input
- Custom workflows
- Long-term memory
- Plugin system

### Platform Limitations
- **macOS**: Fully supported
- **Windows**: Experimental (hotkeys may differ)
- **Linux**: Experimental (app launching may vary)

### Email Reply Workflow
- Only tested with macOS Mail.app
- Keyboard shortcuts are platform-specific
- Requires email client to be already open with an email selected

---

## Development

### Adding New Intents

1. Update `core/nlu/parser.py` with new intent pattern
2. Update `core/planner/action_planner.py` to plan steps for the intent
3. If needed, add new actions to `core/executor/engine.py`

### Testing
Currently no automated tests. Manual testing workflow:
```bash
python main.py
# Test each intent manually
```

---

## License

See [LICENSE](../LICENSE) file in the repository root.

---

## Contributing

This is an MVP for a hackathon project. Contributions welcome after initial release.

**Contact**: See root README for project details.

---

## Acknowledgments

Built for accessibility-first design. Inspired by the need to make technology accessible to everyone, regardless of physical ability.

---

**PixelLink exists to remove physical barriers between people and technology—by letting intent, not ability, define access.**
