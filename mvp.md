# Maes — MVP Implementation Guide (`mvp.md`)

This document defines the **Minimum Viable Product (MVP)** for Maes and provides **concrete implementation guidance** for each subsystem.

The goal of the MVP is to demonstrate:

* Intent-based control
* Real OS-level interaction
* Accessibility value through one complete workflow

This is **not** a prototype spec. This is an **executable system definition**.

---

## 1. MVP Scope Definition

### What the MVP MUST Prove

* A user can express intent in natural language
* Maes can translate intent into OS actions
* The system operates safely and locally
* One accessibility persona can complete a real task end-to-end

### What the MVP Will NOT Cover

* Full voice pipeline
* Cloud services
* Long-term memory
* Multiple personas
* Plugin ecosystem

---

## 2. Target Environment

### Operating System

Choose **one** OS for MVP:

* Windows (recommended for automation support)
* macOS
* Linux

All logic must be OS-abstracted where possible.

### Runtime

* Python 3.10+
* Local execution only

---

## 3. Repository Structure (Recommended)

```
pixelink/
│
├── core/
│   ├── input/
│   │   └── text_input.py
│   ├── nlu/
│   │   ├── intents.py
│   │   └── parser.py
│   ├── planner/
│   │   └── action_planner.py
│   ├── executor/
│   │   ├── keyboard.py
│   │   ├── mouse.py
│   │   └── os_control.py
│   ├── safety/
│   │   └── guard.py
│   └── context/
│       └── session.py
│
├── demo/
│   └── demo_workflow.py
│
├── logs/
│
├── main.py
└── mvp.md
```

---

## 4. Input Layer (Implementation)

### Goal

Convert user input into a clean text string for the NLU layer.

### MVP Implementation

* Use CLI or minimal UI
* Accept free-form text input
* Strip special characters
* Reject empty or malformed input

### Output Contract

```python
{
  "raw_text": "reply to last email saying I'll send the file tomorrow",
  "timestamp": "...",
  "source": "text"
}
```

### Completion Criteria

* User can input text reliably
* Input reaches NLU without modification loss

---

## 5. Intent System (NLU)

### Goal

Translate text into structured intent.

### Supported MVP Intents

Limit to **5–8 intents**:

* open_app
* focus_app
* type_text
* click
* reply_email
* confirm
* cancel

### Implementation Strategy

* Start rule-based (regex or keyword mapping)
* No ML dependency required for MVP
* Confidence score is optional but recommended

### Output Schema

```json
{
  "intent": "reply_email",
  "entities": {
    "target": "last_email",
    "content": "I'll send the file tomorrow"
  },
  "confidence": 0.9
}
```

### Completion Criteria

* Every input maps to exactly one intent or fails gracefully
* Unknown intents return a clear error

---

## 6. Context Management

### Goal

Enable basic references like “last” or “previous”.

### Stored Context

* Last executed intent
* Last focused application
* Last active file or window (optional)

### Implementation

* In-memory session object
* Reset on app restart

### Completion Criteria

* “last” resolves correctly in demo workflow
* No persistence required

---

## 7. Action Planner

### Goal

Convert intent into ordered OS-level actions.

### Responsibilities

* Validate intent
* Decompose into steps
* Check safety constraints
* Request confirmation when needed

### Example

Intent:

```
reply_email
```

Plan:

1. Focus email client
2. Open last email
3. Insert reply text
4. Await confirmation
5. Send email

### Completion Criteria

* Planner outputs a step list
* Steps are deterministic and logged

---

## 8. Safety Layer

### Goal

Prevent destructive or unsafe actions.

### MVP Rules

* Block file deletion
* Block system shutdown
* Block admin-level commands
* Require confirmation before send actions

### Implementation

* Central guard module
* Planner calls guard before execution

### Kill Switch

* Keyboard shortcut or CLI command
* Immediately halts execution

### Completion Criteria

* Unsafe actions are blocked
* Kill switch works during execution

---

## 9. Execution Engine (OS Control)

### Goal

Execute actions on the operating system.

### Required Capabilities

* Keyboard typing
* Mouse move and click
* Application focus switching
* Window activation

### Implementation Notes

* Abstract OS calls behind interfaces
* Each action returns success or failure
* Add small delays to ensure stability

### Completion Criteria

* Actions visibly occur on screen
* Failures are detected and reported

---

## 10. Feedback System

### Goal

Keep the user informed at all times.

### MVP Feedback

* Print current action
* Print success or error
* Ask for confirmation explicitly

### Example

```
Action 3/5: Typing reply text...
Awaiting confirmation to send email.
```

### Completion Criteria

* User always knows system state
* No silent failures

---

## 11. Demo Workflow (Critical)

### Required Demo

**One full end-to-end task**, for example:

* Replying to an email without keyboard or mouse

### Demo Script Must Show

1. User intent input
2. Parsed intent output
3. Planned steps
4. Live execution
5. Completion confirmation

### Completion Criteria

* Demo completes without manual intervention
* Repeatable and deterministic

---

## 12. Accessibility Persona

### Definition

Create one persona:

* Specific disability
* Specific limitation
* Clear benefit from Maes

### Example

> User with limited hand mobility replying to emails hands-free.

### Completion Criteria

* Persona is described in README or demo
* Workflow maps directly to persona needs

---

## 13. Logging

### Goal

Provide transparency and debuggability.

### MVP Logs

* Timestamped actions
* Intent parsed
* Execution results

### Storage

* Local log files only

---

## 14. MVP Completion Checklist

Maes MVP is complete when:

* One OS is fully supported
* One persona workflow works end-to-end
* Safety guard prevents dangerous actions
* Demo can run live without hacks
* Codebase is understandable by another developer

---

## 15. What Judges Should See

* Accessibility-first design
* Real OS control
* Intent-based reasoning
* Safety awareness
* Clear impact
