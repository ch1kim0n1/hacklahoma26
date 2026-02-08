# hacklahoma26

## PixelLink

**An intent-driven accessibility operating layer for computers and phones**

PixelLink enables people with disabilities to control computers and mobile devices using **intent**, not physical input.
It translates natural language and alternative inputs into OS-level actions—allowing users to operate modern technology without relying on keyboards, mice, or rigid command systems.

---

## What PixelLink Is

PixelLink is a **local-first AI accessibility platform** that:

* Understands what a user wants to do
* Safely plans the required actions
* Executes them across operating systems and devices

PixelLink is **not**:

* A voice assistant
* A screen reader
* A macro automation tool

PixelLink is an **intent-based operating layer**.

---

## Problem

Modern operating systems assume:

* Fine motor control
* Continuous physical interaction
* High cognitive load

Existing accessibility tools are:

* Fragmented
* Single-modality
* Hard-coded
* Difficult to extend

**PixelLink removes these assumptions.**

---

## Core Concept: Intent Over Interaction

Instead of asking *how* a user interacts, PixelLink focuses on *what* the user wants to accomplish.

Example:
“Reply to the last email and attach the document I edited yesterday”

PixelLink:

1. Understands intent
2. Plans the steps
3. Executes safely
4. Confirms completion

---

## Who This Is For

### Primary Users

* People with limited motor control
* Neurodivergent users
* Users with temporary disabilities or injuries

### Secondary Users

* Accessibility researchers
* Power users seeking hands-free workflows
* Developers building inclusive software

---

## High-Level Architecture

User Input (Text / Voice / Face / Phone)
→ Input Normalizer
→ NLU Engine (Intent + Context)
→ Action Planner (Task Decomposition + Safety)
→ Execution Engine (OS-level Control)
→ Feedback Layer (Visual / Audio / Phone)

---

## Core Features

### Intent-Based Control

* Natural language understanding
* Multi-step task inference
* Context-aware disambiguation

### OS-Level Execution

* Keyboard and mouse simulation
* Window and application control
* File system interaction

### Phone ↔ PC Bridge (POST MVP)

* Phone as alternative controller
* Secure local communication
* Touch and gesture fallback

### Multi-Modal Input

* Text (usually via SST since people with no hands cant type)
* Voice
* **Eye and blink control** (webcam-based gaze + blink)
* Facial gestures
* Head movement
* Mobile input (POST MVP)

### Eye and Blink Control

PixelLink can use a webcam for **gaze** and **blink** input (inspired by Project-VISION):

* **Gaze**: Where you look drives the system mouse cursor (“look to point”).
* **Single blink**: Confirm a pending action.
* **Double blink**: Cancel a pending action, or left-click at the current cursor when no action is pending.
* **Live preview window**: Shows camera feed with eye landmarks, EAR/blink status, and gaze telemetry.
* **Desktop mini preview panel**: In-app camera tile with live eye sensors so you can verify tracking at a glance.
* **Esc key support**: Press `Esc` in the desktop app to exit eye mode instantly.

Enable via the **Eye** toggle in the desktop app. Requires:

* A camera (built-in or USB).
* Optional Python deps: `opencv-python`, `mediapipe` (see `pylink/requirements.txt`). If missing, the Eye button is disabled and PixelLink runs normally for text/voice.
* Camera permission (e.g. macOS: System Preferences → Security & Privacy → Camera).

Calibration for more accurate gaze is planned for a future release.
Advanced tuning env vars:
* `PIXELINK_EYE_IRIS_GAIN_X` / `PIXELINK_EYE_IRIS_GAIN_Y` to control eye-movement sensitivity.
* `PIXELINK_EYE_HEAD_WEIGHT` to blend head movement back in (default `0.0` = eyeballs-first).
* `PIXELINK_EYE_INVERT_X` / `PIXELINK_EYE_INVERT_Y` if your camera orientation is reversed.

### Accessibility-First Design

* No mandatory modality
* Adjustable interaction speed
* Low cognitive load workflows

---

## Privacy & Security

PixelLink is **local-first** by design.

### Guarantees

* No cloud dependency by default
* Explicit user authorization for all actions
* No background surveillance
* No hidden data collection

---

## MVP Scope

### Required

* Text-based intent input
* OS keyboard and mouse control
* One complete end-to-end workflow
* One accessibility persona demo

### Optional

* Phone controller
* Facial gesture input
* Multi-step task chaining

---

## Tech Stack

### Core

* Python (NLU + execution)
* OS automation libraries
* Electron desktop shell (SwiftUI-inspired design language)
* Local desktop bridge process (JSON over stdin/stdout)
* Local HTTP phone bridge for confirmation controls

### Optional

* On-device LLM
* Cross-platform UI framework

## Platform Support Reality

PixelLink currently targets **macOS first** for live reliability.

* `stable`: macOS
* `experimental`: Windows, Linux (core flows may work, but automation/focus behavior varies by platform)

---

## Desktop App (Electron)

Run the new production-style desktop UI:

```bash
cd electron
npm install
npm run start
```

Safe test mode (no real keyboard/mouse automation):

```bash
npm run start:dry-run
```

See details in `electron/README.md`.

---

## Mission Implementation Plan

The full mission feature implementation map is documented in:

`MISSION_IMPLEMENTATION_PLAN.md`

---

## Example User Flow

**Scenario: Replying to an email hands-free**

1. User inputs:
   “Reply saying I’ll send the file tomorrow”

2. PixelLink:

   * Identifies the target email
   * Drafts the response
   * Requests confirmation

3. User confirms via phone tap

4. Email is sent

5. Visual confirmation is shown

---

## How PixelLink Is Different

* Intent-based instead of command-based
* OS-wide control instead of app-limited control
* Multi-modal input instead of single modality
* Accessibility-first instead of accessibility-added-later
* Extensible by design

---

## Roadmap

### Phase 1

* Stable core
* Accessibility testing
* MVP release

### Phase 2

* Plugin system
* Custom workflows
* Advanced context memory

### Phase 3

* Multi-device ecosystem
* Research partnerships
* Accessibility standardization

## Mission

PixelLink exists to remove physical barriers between people and technology—by letting intent, not ability, define access.

---

## Plugins (Google & Reminders)

### Google (Calendar, Gmail)

**If you push this repo, other people do *not* get access to your Google account.** OAuth is **per-user**:

- **Do not commit** `credentials.json` or `token.json` / `token_gmail.json` (they are in `.gitignore`).
- Each user clones the repo, adds their own OAuth client (or uses a shared client ID) and runs the app **once** to sign in in the browser. That creates a **personal** token on their machine.
- So: pushing the repo only shares the *code*. Each user must run the app and complete the Google sign-in on their own machine to use Calendar/Gmail.

### Apple Reminders (Mac only)

The `reminders-mcp` plugin is loaded only on **macOS** (`darwin`). It uses the native Reminders app via AppleScript. Add `"reminders-mcp": {}` to your plugin config to use it.
