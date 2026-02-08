# PixelLink MVP - Quick Start Guide

**Get up and running in 2 minutes**

---

## Prerequisites Check

```bash
# Check Python version (need 3.10+)
python3 --version

# Check if you're on macOS (recommended)
uname -s  # Should show "Darwin"
```

---

## Installation (3 commands)

```bash
# 1. Navigate to the project
cd /path/to/hacklahoma26/pylink

# 2. Install dependencies
pip3 install -r requirements.txt

# 3. Run the demo
python3 demo/email_reply_demo.py
```

---

## New Desktop UI (Electron)

```bash
cd /path/to/hacklahoma26/electron
npm install
npm run start
```

For a safe UI test without OS automation:

```bash
npm run start:dry-run
```

---

## macOS: Enable Accessibility Permissions

**⚠️ CRITICAL: Required for kill switch (ESC key) to work**

1. Open **System Preferences** → **Security & Privacy** → **Accessibility**
2. Click the lock icon (bottom left) to unlock
3. Click the **+** button
4. Add your Terminal app (or iTerm, VS Code, etc.)
5. Restart your terminal

---

## Demo Options

### Option 1: Automated Demo (Best for Presentations)
```bash
python3 demo/email_reply_demo.py
# Choose: 1
# Press ENTER to advance through steps
```

**Shows:**
- Full email reply workflow
- Voice-to-text simulation
- Safety confirmation
- Complete accessibility story

---

### Option 2: Interactive Testing
```bash
python3 main.py --cli
```

**Try these commands:**
```
open Notes
type Hello, this is a test message
open Mail
reply email saying I'll send the file tomorrow
confirm
exit
```

---

### Option 3: Manual Demo
```bash
python3 demo/email_reply_demo.py
# Choose: 2
# Type commands interactively
```

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'pyautogui'"
```bash
pip3 install pyautogui pynput
```

### "Permission denied" or "Cannot open app"
**Fix**: Enable Accessibility permissions (see above)

### "App not found"
Use exact app name:
- ✅ `open Notes` (correct)
- ❌ `open notes.app` (wrong)

### Kill switch (ESC) doesn't work
**Fix**: Accessibility permissions not enabled

---

## What to Show Judges

### 1. The Problem (30 seconds)
"People with limited mobility can't use keyboards and mice. Existing tools are fragmented and rigid."

### 2. The Solution (30 seconds)
"PixelLink uses intent-based control. Users say what they want, not how to do it."

### 3. Live Demo (3 minutes)
```bash
python3 demo/email_reply_demo.py
```
Run the automated demo. Highlight:
- Natural language understanding
- Safety confirmation before sending
- No keyboard/mouse needed
- Works with voice-to-text

### 4. Code Highlight (1 minute)
Show `core/nlu/parser.py`:
```python
# Natural language → structured intent
"reply email saying I'm on it"
  → Intent(name="reply_email", entities={"content": "I'm on it"})
```

### 5. Safety Features (30 seconds)
- ESC key = instant kill switch
- Blocked actions: delete_file, shutdown_system, format_drive
- Confirmation required before sending emails

---

## Common Demo Commands

### Basic Control
```
open Notes
open Safari
open Mail
focus Terminal
launch Calculator
```

### Text Input
```
type Hello world
type test@example.com
write This is a test message
```

### Email Workflow
```
open Mail
reply email saying I'll send it by tomorrow
confirm
```

### Safety
```
Press ESC          → Emergency stop
Type "cancel"      → Cancel pending action
Type "exit"        → Quit application
```

---

## Project Structure

```
hacklahoma26/
├── pylink/
│   ├── main.py                    # Interactive CLI
│   ├── demo/
│   │   ├── email_reply_demo.py    # Full automated demo
│   │   └── demo_workflow.py       # Simple single-command demo
│   ├── core/
│   │   ├── nlu/parser.py          # Intent recognition
│   │   ├── planner/               # Action planning
│   │   ├── executor/              # OS-level control
│   │   ├── safety/guard.py        # Kill switch + safety
│   │   └── context/session.py     # Context tracking
│   └── README.md                  # Full documentation
├── IMPROVEMENTS.md                 # Complete changelog
├── QUICKSTART.md                   # This file
└── LICENSE                         # MIT License
```

---

## Key Features to Mention

### 1. Accessibility-First
- Built for people with limited mobility
- No mandatory input modality
- Works with any voice-to-text tool

### 2. Intent-Based Control
- Natural language: "reply email saying X"
- Not rigid commands: "can you please open Notes" works
- Context-aware: "open last app" remembers

### 3. Safe by Design
- Kill switch (ESC key)
- Blocked dangerous actions
- Confirmation before irreversible actions

### 4. Local-First
- No cloud dependency
- No data collection
- All processing on device

---

## Technical Highlights for Judges

### Clean Architecture
```
Input → NLU → Planner → Safety Guard → Executor
```

### Cross-Platform Design
- macOS: Fully supported
- Windows/Linux: Experimental (OS abstraction layer ready)

### Error Handling
- Comprehensive try-except blocks
- Clear error messages
- Graceful degradation

### Extensibility
- Easy to add new intents
- Modular action system
- Plugin-ready architecture (future)

---

## Testing Checklist

Before demo:
- [ ] Dependencies installed (`pip3 install -r requirements.txt`)
- [ ] Accessibility permissions enabled (macOS)
- [ ] Mail.app has at least one email (for email demo)
- [ ] Notes.app installed (for typing demo)
- [ ] Tested demo once (`python3 demo/email_reply_demo.py`)
- [ ] Kill switch works (press ESC during execution)

---

## Emergency Recovery

If demo breaks during presentation:

### Plan A: Switch to Interactive Mode
```bash
python3 main.py --cli
# Type: open Notes
# Type: type This is a demo
```

### Plan B: Show Code + Logs
```bash
# Show intent parser
cat core/nlu/parser.py | grep "def parse_intent"

# Show recent logs
cat logs/pixelink-*.log | tail -20
```

### Plan C: Explain Architecture
Use whiteboard/slides to explain:
1. Intent recognition
2. Action planning
3. Safe execution
4. OS abstraction

---

## Contact & Resources

- **Documentation**: [pylink/README.md](pylink/README.md)
- **Improvements Log**: [IMPROVEMENTS.md](IMPROVEMENTS.md)
- **License**: MIT (see [LICENSE](LICENSE))

---

## MVP Scope Reminder

**What's Included:**
✅ Text-based intent input
✅ OS keyboard/mouse control
✅ One complete workflow (email reply)
✅ Safety features (kill switch, blocked actions)
✅ Natural language parsing

**What's NOT Included (Future Work):**
❌ Voice input (use external voice-to-text)
❌ Phone controller bridge
❌ Facial gesture input
❌ Custom workflows
❌ Long-term memory

---

## Success Criteria

The demo succeeds if judges see:
1. ✅ Natural language works ("reply email saying X")
2. ✅ No keyboard/mouse used
3. ✅ Safety confirmation shown
4. ✅ Task completes end-to-end
5. ✅ Clear accessibility value

---

## Final Checklist

Before submission:
- [ ] Code runs without errors
- [ ] Demo completes successfully
- [ ] README is complete
- [ ] LICENSE file present
- [ ] No hardcoded secrets or paths
- [ ] Git history is clean
- [ ] All scope creep removed

---

**You're ready to demo! 🚀**

*PixelLink exists to remove physical barriers between people and technology—by letting intent, not ability, define access.*
