Below is a **clean, MVP-aligned feature list** for **Maes**.
Each feature is **explicit**, **implementable**, and **demo-safe**.

---

## Maes — Feature List

### Core Accessibility

* Intent-based control instead of command-based input
* Hands-free computer operation
* Accessibility-first interaction model
* No mandatory input modality

---

### Input Features

* Text-based intent input
* Optional voice input (if available)
* Phone-based input as fallback controller
* Input normalization across modalities

---

### Intent Understanding (NLU)

* Intent classification (open app, type text, click, navigate)
* Entity extraction (app names, text content, targets)
* Simple context memory (last action, last app)
* Support for “last / previous” references

---

### OS-Level Control

* Keyboard input simulation
* Mouse movement and clicking
* Application focus switching
* Window navigation
* Text typing into active applications

---

### Task Execution

* Multi-step task decomposition
* Sequential action execution
* Execution confirmation before critical steps
* Cancel or abort execution mid-task

---

### Safety & Control

* Permission-based action whitelist
* Blocking of destructive system actions
* Emergency kill switch
* Local execution only (no cloud dependency)

---

### Feedback & Visibility

* Real-time execution status
* Success and failure notifications
* Clear user confirmation prompts
* Local action logging

---

### Phone ↔ PC Bridge (MVP+)

* Secure local connection
* Phone used as confirmation device
* Simple tap-based confirm / cancel
* Status display on phone

---

### Accessibility Customization

* Adjustable interaction speed
* Reduced cognitive load mode
* Minimal UI option
* Visual-only feedback option

---

### Demo & MVP Support

* Single accessibility persona workflow
* One full real-world task demo
* Deterministic behavior for live demos
* Clear demo start / stop flow

---

### Developer / Open Source

* Modular architecture
* Extendable intent-action mapping
* Clear separation of NLU and execution
* Documented safety constraints
