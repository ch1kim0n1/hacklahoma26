const PREFERENCES_KEY = "maes.ui.preferences.v1";
const BLIND_ONBOARD_KEY = "maes.ui.blindmode.onboarded.v1";

const state = {
  runtime: null,
  logs: [],
  voiceListening: false,
  continuousVoiceEnabled: true,
  continuousVoiceLoopRunning: false,
  continuousVoiceAnnounced: false,
  voiceModel: null,
  lastModelErrorSignature: "",
  preferences: {
    blindModeEnabled: false,
    narrationLevel: "concise",
    screenReaderHintsEnabled: true,
    reducedLoad: false,
    minimalUi: false,
    visualOnly: false
  },
  lastAnnouncedStatus: "",
  hasInitialPreferenceSync: false,
  lastRuntimeAnnouncement: ""
};

const elements = {
  consoleRoot: document.querySelector(".console"),
  statusDot: document.getElementById("statusDot"),
  statusText: document.getElementById("statusText"),
  logArea: document.getElementById("logArea"),
  commandForm: document.getElementById("commandForm"),
  commandInput: document.getElementById("commandInput"),
  sendBtn: document.getElementById("sendBtn"),
  voiceBtn: document.getElementById("voiceBtn"),
  blindModeToggle: document.getElementById("blindModeToggle"),
  reducedLoadToggle: document.getElementById("reducedLoadToggle"),
  minimalUiToggle: document.getElementById("minimalUiToggle"),
  visualOnlyToggle: document.getElementById("visualOnlyToggle"),
  voiceModelStatus: document.getElementById("voiceModelStatus"),
  voiceModelMessage: document.getElementById("voiceModelMessage"),
  voiceModelPercent: document.getElementById("voiceModelPercent"),
  voiceModelProgress: document.getElementById("voiceModelProgress"),
  eyeControlBtn: document.getElementById("eyeControlBtn"),
  hideBtn: document.getElementById("hideBtn"),
  eyePreviewPanel: document.getElementById("eyePreviewPanel"),
  eyePreviewVideo: document.getElementById("eyePreviewVideo"),
  eyePreviewStats: document.getElementById("eyePreviewStats"),
  eyePreviewState: document.getElementById("eyePreviewState"),
  livePolite: document.getElementById("livePolite"),
  liveAssertive: document.getElementById("liveAssertive")
};

function loadPreferences() {
  try {
    const raw = localStorage.getItem(PREFERENCES_KEY);
    if (!raw) {
      return;
    }
    const parsed = JSON.parse(raw);
    state.preferences = {
      ...state.preferences,
      ...parsed
    };
  } catch (_) {
    // Ignore corrupted local preferences.
  }
}

function savePreferences() {
  localStorage.setItem(PREFERENCES_KEY, JSON.stringify(state.preferences));
}

function announce(message, priority = "polite") {
  const text = String(message || "").trim();
  if (!text) {
    return;
  }
  const isAssertive = String(priority).toLowerCase() === "assertive";
  const target = isAssertive ? elements.liveAssertive : elements.livePolite;
  if (!target) {
    return;
  }
  target.textContent = "";
  window.setTimeout(() => {
    target.textContent = text;
  }, 20);
}

function shouldCaptureShortcutTarget() {
  const active = document.activeElement;
  if (!active) {
    return true;
  }
  if (active === elements.commandInput) {
    return false;
  }
  const tag = String(active.tagName || "").toUpperCase();
  if (tag === "INPUT" || tag === "TEXTAREA") {
    return false;
  }
  return !active.isContentEditable;
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function maybeShowBlindModeOnboarding() {
  if (!state.preferences.blindModeEnabled) {
    return;
  }
  if (localStorage.getItem(BLIND_ONBOARD_KEY) === "1") {
    return;
  }
  const message = "Blind mode is on. Press V for voice, S for status, and R to repeat the last response.";
  localStorage.setItem(BLIND_ONBOARD_KEY, "1");
  appendLog("info", "Blind Mode", message);
  announce(message, "assertive");
}

function applyPreferencesUi() {
  if (state.preferences.blindModeEnabled && state.preferences.visualOnly) {
    state.preferences.visualOnly = false;
  }
  elements.blindModeToggle.checked = Boolean(state.preferences.blindModeEnabled);
  elements.reducedLoadToggle.checked = Boolean(state.preferences.reducedLoad);
  elements.minimalUiToggle.checked = Boolean(state.preferences.minimalUi);
  elements.visualOnlyToggle.checked = Boolean(state.preferences.visualOnly);
  elements.visualOnlyToggle.disabled = Boolean(state.preferences.blindModeEnabled);
  elements.consoleRoot.classList.toggle("reduced-load", Boolean(state.preferences.reducedLoad));
  elements.consoleRoot.classList.toggle("minimal-ui", Boolean(state.preferences.minimalUi));
  renderLogs();
}

function isLogVisible(entry) {
  if (!state.preferences.reducedLoad) {
    return true;
  }
  if (entry.title === "Bridge Log") {
    return false;
  }
  if (entry.level === "info" && !["Command", "Voice", "Heard", "Maes", "Model"].includes(entry.title)) {
    return false;
  }
  return true;
}

function appendLog(level, title, message) {
  const time = new Date().toLocaleTimeString();
  state.logs.unshift({ level, title, message, time });
  state.logs = state.logs.slice(0, 140);
  renderLogs();
}

function renderLogs() {
  elements.logArea.innerHTML = "";
  state.logs.filter(isLogVisible).forEach((entry) => {
    const node = document.createElement("article");
    node.className = `log-entry log-${entry.level}`;
    const heading = state.preferences.reducedLoad ? entry.title : `${entry.time} • ${entry.title}`;
    node.innerHTML = `<strong>${heading}</strong>${entry.message || ""}`;
    elements.logArea.appendChild(node);
  });
}

function setStatus(runtime) {
  const backendOnline = runtime?.backend === "online";
  const waitingConfirm = Boolean(runtime?.pendingConfirmation);
  const waitingClarification = Boolean(runtime?.pendingClarification);
  const pipelineState = runtime?.pipelineState || "idle";
  let statusMessage = "Offline";

  if (!backendOnline) {
    elements.statusDot.className = "status-dot status-offline";
    elements.statusText.textContent = "Offline";
  } else {
    // Show pipeline state when not idle
    const pipelineLabels = {
      listen: "Listening...",
      processing: "Processing...",
      action: "Executing...",
      output: "Speaking...",
    };

    if (pipelineState !== "idle" && pipelineLabels[pipelineState]) {
      elements.statusDot.className = "status-dot status-busy";
      statusMessage = pipelineLabels[pipelineState];
      elements.statusText.textContent = statusMessage;
    } else if (waitingClarification) {
      elements.statusDot.className = "status-dot status-warn";
      statusMessage = state.preferences.reducedLoad ? "Need Input" : "Needs Clarification";
      elements.statusText.textContent = statusMessage;
    } else if (waitingConfirm) {
      elements.statusDot.className = "status-dot status-warn";
      statusMessage = state.preferences.reducedLoad ? "Need Confirm" : "Awaiting Confirmation";
      elements.statusText.textContent = statusMessage;
    } else {
      elements.statusDot.className = "status-dot status-online";
      statusMessage = "Online";
      elements.statusText.textContent = statusMessage;
    }
  }

  const shouldAnnounce = state.preferences.blindModeEnabled || state.preferences.screenReaderHintsEnabled;
  if (shouldAnnounce && statusMessage !== state.lastAnnouncedStatus) {
    state.lastAnnouncedStatus = statusMessage;
    announce(`Status: ${statusMessage}`, "polite");
  }
}

function updateVoiceModelStatus(model) {
  if (!model || typeof model !== "object") {
    elements.voiceModelStatus.classList.add("hidden");
    return;
  }
  state.voiceModel = model;
  const stage = String(model.stage || "").toLowerCase();
  const stateName = String(model.state || "").toLowerCase();
  const progress = Number.isFinite(Number(model.progress)) ? Math.max(0, Math.min(100, Number(model.progress))) : 0;

  const visible = stage === "downloading" || stage === "loading_model" || stage === "checking_cache" || stage === "failed";
  elements.voiceModelStatus.classList.toggle("hidden", !visible);
  elements.voiceModelMessage.textContent = model.message || "Preparing voice model...";
  elements.voiceModelPercent.textContent = `${progress}%`;
  elements.voiceModelProgress.style.width = `${progress}%`;

  if (stage === "failed" || stateName === "error") {
    const signature = `${model.stage || ""}:${model.error || model.message || ""}`;
    if (signature !== state.lastModelErrorSignature) {
      state.lastModelErrorSignature = signature;
      appendLog("error", "Model", model.error || model.message || "Voice model setup failed.");
    }
  }
}

function applyAccessibilityFromRuntime(runtime) {
  const accessibility = runtime?.accessibility;
  if (!accessibility || typeof accessibility !== "object") {
    return;
  }
  const runtimeBlind = Boolean(accessibility.blindModeEnabled ?? accessibility.blind_mode_enabled);
  const runtimeNarration = String((accessibility.narrationLevel ?? accessibility.narration_level ?? "concise")) === "verbose"
    ? "verbose"
    : "concise";
  const runtimeHints = Boolean(
    accessibility.screenReaderHintsEnabled
    ?? accessibility.screen_reader_hints_enabled
    ?? state.preferences.screenReaderHintsEnabled
  );

  if (state.hasInitialPreferenceSync) {
    let changed = false;
    if (state.preferences.blindModeEnabled !== runtimeBlind) {
      state.preferences.blindModeEnabled = runtimeBlind;
      changed = true;
    }
    if (state.preferences.narrationLevel !== runtimeNarration) {
      state.preferences.narrationLevel = runtimeNarration;
      changed = true;
    }
    if (state.preferences.screenReaderHintsEnabled !== runtimeHints) {
      state.preferences.screenReaderHintsEnabled = runtimeHints;
      changed = true;
    }
    if (changed) {
      savePreferences();
      applyPreferencesUi();
      if (runtimeBlind) {
        maybeShowBlindModeOnboarding();
      }
    }
  }

  const message = String((accessibility.lastAnnouncement ?? accessibility.last_announcement ?? "")).trim();
  if (message && message !== state.lastRuntimeAnnouncement) {
    state.lastRuntimeAnnouncement = message;
    announce(message, "polite");
  }
}

function updateRuntime(runtime) {
  state.runtime = runtime;
  applyAccessibilityFromRuntime(runtime);
  setStatus(runtime);
  updateVoiceModelStatus(runtime?.voice?.model);
  updateVoiceButtonState();
  updateEyeControlButton();
  updateEyePreview(runtime);
}

async function startEyePreviewCamera() {
  if (state.eyePreviewStream || !elements.eyePreviewVideo) {
    return;
  }
  if (!navigator.mediaDevices || typeof navigator.mediaDevices.getUserMedia !== "function") {
    if (!state.eyePreviewUnsupported) {
      appendLog("warning", "Eye Preview", "Camera preview API unavailable in this runtime.");
      state.eyePreviewUnsupported = true;
    }
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: "user",
        width: { ideal: 320 },
        height: { ideal: 240 }
      },
      audio: false
    });
    state.eyePreviewStream = stream;
    elements.eyePreviewVideo.srcObject = stream;
  } catch (error) {
    if (!state.eyePreviewUnsupported) {
      appendLog("warning", "Eye Preview", `Camera preview unavailable: ${String(error.message || error)}`);
      state.eyePreviewUnsupported = true;
    }
  }
}

function stopEyePreviewCamera() {
  if (!state.eyePreviewStream) {
    return;
  }
  state.eyePreviewStream.getTracks().forEach((track) => track.stop());
  state.eyePreviewStream = null;
  if (elements.eyePreviewVideo) {
    elements.eyePreviewVideo.srcObject = null;
  }
}

function updateEyePreview(runtime) {
  if (!elements.eyePreviewPanel || !elements.eyePreviewStats || !elements.eyePreviewState) {
    return;
  }
  const eye = runtime?.eyeControl || {};
  const eyeActive = Boolean(eye.active);
  if (!eyeActive) {
    elements.eyePreviewPanel.classList.add("hidden");
    elements.eyePreviewState.textContent = "idle";
    elements.eyePreviewStats.textContent = "Waiting for eye control...";
    stopEyePreviewCamera();
    return;
  }

  elements.eyePreviewPanel.classList.remove("hidden");
  elements.eyePreviewState.textContent = eye.blinkState || "tracking";
  void startEyePreviewCamera();

  const gaze = Array.isArray(eye.lastGaze) ? eye.lastGaze.join(", ") : "n/a";
  const gazeNorm = Array.isArray(eye.gazeNorm)
    ? `${Number(eye.gazeNorm[0]).toFixed(2)}, ${Number(eye.gazeNorm[1]).toFixed(2)}`
    : "n/a";
  const ear = typeof eye.lastEar === "number" ? eye.lastEar.toFixed(3) : "n/a";
  const previewStatus = eye.previewActive ? "native ok" : "native off";
  elements.eyePreviewStats.textContent =
    `Blink: ${eye.lastBlink || "-"}\n` +
    `EAR: ${ear}\n` +
    `Gaze: ${gaze}\n` +
    `Norm: ${gazeNorm}\n` +
    `Iris: ${eye.irisTracking ? "on" : "off"}\n` +
    `Mode: ${eye.controlMode || "face"}\n` +
    `Backend: ${eye.backend || "-"} (${previewStatus})`;
}

function isPipelineBusy() {
  const ps = state.runtime?.pipelineState || "idle";
  return ps === "action" || ps === "output" || ps === "processing";
}

function isVoiceModelLoading() {
  const modelState = String(state.runtime?.voice?.model?.state || "").toLowerCase();
  const modelStage = String(state.runtime?.voice?.model?.stage || "").toLowerCase();
  return ["loading", "idle"].includes(modelState) && modelStage !== "ready";
}

function isExpectedContinuousVoiceResult(result) {
  const code = String(result?.error?.code || "").toUpperCase();
  if (!code) {
    return false;
  }
  return ["VOICE_INPUT_EMPTY", "VOICE_INPUT_FAILED", "INPUT_BLOCKED"].includes(code);
}

function canCaptureContinuousVoice() {
  if (!state.continuousVoiceEnabled || state.voiceListening) {
    return false;
  }
  const backendOnline = state.runtime?.backend === "online";
  const voiceInputEnabled = Boolean(state.runtime?.voice?.inputEnabled);
  if (!backendOnline || !voiceInputEnabled) {
    return false;
  }
  if (isPipelineBusy() || isVoiceModelLoading()) {
    return false;
  }
  return true;
}

async function runContinuousVoiceLoop() {
  if (state.continuousVoiceLoopRunning) {
    return;
  }
  state.continuousVoiceLoopRunning = true;
  if (!state.continuousVoiceAnnounced) {
    state.continuousVoiceAnnounced = true;
    appendLog("info", "Voice", "24/7 listening enabled. Voice is now primary input.");
    announce("24/7 listening enabled. Voice is primary input.", "polite");
  }

  while (state.continuousVoiceEnabled) {
    if (!canCaptureContinuousVoice()) {
      await delay(750);
      continue;
    }
    const result = await submitVoiceCommand({ continuous: true, quietStart: true });
    if (result && !isExpectedContinuousVoiceResult(result)) {
      await delay(140);
    } else {
      await delay(250);
    }
  }
  state.continuousVoiceLoopRunning = false;
}

function ensureContinuousVoiceLoop() {
  if (state.continuousVoiceEnabled && !state.continuousVoiceLoopRunning) {
    void runContinuousVoiceLoop();
  }
}

function updateVoiceButtonState() {
  const backendOnline = state.runtime?.backend === "online";
  const voiceInputEnabled = Boolean(state.runtime?.voice?.inputEnabled);
  const modelLoading = isVoiceModelLoading();
  const busy = isPipelineBusy();
  const enabled = backendOnline && voiceInputEnabled && !state.voiceListening && !modelLoading && !busy;

  elements.voiceBtn.disabled = !enabled;
  elements.voiceBtn.classList.toggle("listening", state.voiceListening);

  // Also disable command input when pipeline is busy
  if (elements.commandInput) {
    elements.commandInput.disabled = busy;
    elements.commandInput.placeholder = busy
      ? "Please wait..."
      : "Voice-first mode active. You can still type if needed.";
  }

  if (busy) {
    const ps = state.runtime?.pipelineState || "";
    const labels = { processing: "Processing...", action: "Executing...", output: "Speaking..." };
    elements.voiceBtn.textContent = labels[ps] || "Busy...";
  } else if (state.voiceListening) {
    elements.voiceBtn.textContent = "Listening...";
  } else if (modelLoading && voiceInputEnabled) {
    elements.voiceBtn.textContent = "Model Loading";
  } else if (!voiceInputEnabled) {
    elements.voiceBtn.textContent = "Voice Off";
  } else {
    elements.voiceBtn.textContent = "Voice";
  }
}

function updateEyeControlButton() {
  if (!elements.eyeControlBtn) {
    return;
  }
  const backendOnline = state.runtime?.backend === "online";
  const eyeAvailable = Boolean(state.runtime?.eyeControl?.available);
  const eyeActive = Boolean(state.runtime?.eyeControl?.active);

  elements.eyeControlBtn.disabled = !backendOnline || !eyeAvailable;
  elements.eyeControlBtn.classList.toggle("eye-active", eyeActive);

  if (!eyeAvailable) {
    elements.eyeControlBtn.textContent = "Eye Off";
    elements.eyeControlBtn.title = "Eye control unavailable (camera or dependencies missing)";
  } else if (eyeActive) {
    elements.eyeControlBtn.textContent = "Eye On";
    elements.eyeControlBtn.title = "Eye and blink control active. Click to turn off.";
  } else {
    elements.eyeControlBtn.textContent = "Eye";
    elements.eyeControlBtn.title = "Click to enable eye and blink control (gaze moves cursor, double blink = click)";
  }
}

function classifyLevel(result) {
  if (!result) {
    return "info";
  }
  if (["error", "blocked"].includes(result.status)) {
    return "error";
  }
  if (["awaiting_confirmation", "awaiting_clarification", "unknown"].includes(result.status)) {
    return "warning";
  }
  if (result.status === "completed") {
    return "success";
  }
  return "info";
}

function formatStructuredError(result) {
  if (!result || !result.error || typeof result.error !== "object") {
    return result?.message || "";
  }
  const userMessage = result.error.user_message || result.user_message || "";
  const hints = Array.isArray(result.error.hints) ? result.error.hints : (Array.isArray(result.hints) ? result.hints : []);
  if (state.preferences.reducedLoad) {
    return [userMessage || result.message || "Something went wrong.", hints[0] || ""].filter(Boolean).join(" ");
  }
  const code = result.error.code || "UNKNOWN";
  const details = result.error.details || result.message || "No details";
  const hintText = hints.length ? ` Tips: ${hints.join(" ")}` : "";
  return `${userMessage ? `${userMessage} ` : ""}[${code}] ${details}${hintText}`;
}

function logResult(result) {
  const level = classifyLevel(result);
  const title = result?.status || "Result";
  const message = result?.status === "error" ? formatStructuredError(result) : (result?.message || "");
  appendLog(level, title, message);
  if (state.preferences.blindModeEnabled || state.preferences.screenReaderHintsEnabled) {
    announce(message || title, "polite");
  }

  const intentName = result?.intent?.name;
  if (intentName === "set_blind_mode") {
    const enabled = Boolean(result?.intent?.entities?.enabled);
    state.preferences.blindModeEnabled = enabled;
    if (enabled) {
      state.preferences.visualOnly = false;
      maybeShowBlindModeOnboarding();
    }
    savePreferences();
    applyPreferencesUi();
  }

  if (result?.transcript) {
    appendLog("info", "Heard", result.transcript);
  }

  if (result?.pending_clarification && result?.clarification_prompt) {
    appendLog("warning", "Follow-up", result.clarification_prompt);
  }
}

async function submitCommand(command) {
  const trimmed = command.trim();
  if (!trimmed) {
    return;
  }

  appendLog("info", "Command", trimmed);
  elements.commandInput.value = "";

  try {
    const result = await window.pixelink.sendInput(trimmed, "text");
    logResult(result);
  } catch (error) {
    appendLog("error", "Error", String(error.message || error));
  }
}

async function submitVoiceCommand(options = {}) {
  const continuous = Boolean(options.continuous);
  const quietStart = Boolean(options.quietStart);
  if (state.voiceListening) {
    return null;
  }

  state.voiceListening = true;
  updateVoiceButtonState();
  if (!quietStart) {
    appendLog("info", "Voice", "Listening for command...");
  }

  try {
    const result = await window.pixelink.captureVoiceInput();
    if (!(continuous && isExpectedContinuousVoiceResult(result))) {
      logResult(result);
    }
    return result;
  } catch (error) {
    if (!continuous) {
      appendLog("error", "Voice Error", String(error.message || error));
    }
    return null;
  } finally {
    state.voiceListening = false;
    updateVoiceButtonState();
  }
}

async function syncAccessibilityPreferences() {
  if (!state.runtime || state.runtime.backend !== "online") {
    return;
  }
  try {
    const shouldForceVoice = Boolean(state.preferences.blindModeEnabled);
    const voiceOutputEnabled = shouldForceVoice ? true : !state.preferences.visualOnly;
    const voiceInputEnabled = shouldForceVoice ? true : undefined;
    const response = await window.pixelink.updatePreferences({
      voiceOutputEnabled,
      voiceInputEnabled,
      blindModeEnabled: Boolean(state.preferences.blindModeEnabled),
      narrationLevel: state.preferences.narrationLevel,
      screenReaderHintsEnabled: Boolean(state.preferences.screenReaderHintsEnabled)
    });
    if (response?.voice) {
      updateRuntime({
        ...state.runtime,
        voice: response.voice,
        accessibility: response.accessibility || state.runtime?.accessibility
      });
    }
  } catch (error) {
    appendLog("error", "Settings", `Failed to apply accessibility preferences: ${String(error.message || error)}`);
  }
}

function bindEvents() {
  document.addEventListener("keydown", async (event) => {
    if (event.key === "Escape") {
      const eyeActive = Boolean(state.runtime?.eyeControl?.active);
      if (!eyeActive) {
        return;
      }
      event.preventDefault();
      try {
        await window.pixelink.stopEyeControl();
        appendLog("info", "Eye Control", "Eye control turned off (Esc).");
      } catch (error) {
        appendLog("error", "Eye Control", `Esc stop failed: ${String(error.message || error)}`);
      }
      return;
    }

    if (event.metaKey || event.ctrlKey || event.altKey || !shouldCaptureShortcutTarget()) {
      return;
    }

    const key = String(event.key || "").toLowerCase();
    if (key === "v") {
      event.preventDefault();
      await submitVoiceCommand({ continuous: false, quietStart: false });
      return;
    }
    if (key === "r") {
      event.preventDefault();
      await submitCommand("repeat last response");
      return;
    }
    if (key === "s") {
      event.preventDefault();
      await submitCommand("read status");
    }
  });

  elements.commandForm.addEventListener("submit", (event) => {
    event.preventDefault();
    submitCommand(elements.commandInput.value);
  });

  elements.voiceBtn.addEventListener("click", async () => {
    await submitVoiceCommand({ continuous: false, quietStart: false });
  });

  elements.eyeControlBtn.addEventListener("click", async () => {
    const eyeActive = Boolean(state.runtime?.eyeControl?.active);
    try {
      if (eyeActive) {
        await window.pixelink.stopEyeControl();
        appendLog("info", "Eye Control", "Eye control turned off.");
      } else {
        state.eyePreviewUnsupported = false;
        await window.pixelink.startEyeControl();
        appendLog("info", "Eye Control", "Eye control turned on. Advanced gaze tracking enabled; double blink = click.");
      }
    } catch (error) {
      appendLog("error", "Eye Control", String(error.message || error));
    }
  });

  elements.hideBtn.addEventListener("click", async () => {
    await window.pixelink.hideMain();
  });

  elements.reducedLoadToggle.addEventListener("change", () => {
    state.preferences.reducedLoad = elements.reducedLoadToggle.checked;
    savePreferences();
    applyPreferencesUi();
  });

  elements.blindModeToggle.addEventListener("change", async () => {
    state.preferences.blindModeEnabled = elements.blindModeToggle.checked;
    if (state.preferences.blindModeEnabled) {
      state.preferences.visualOnly = false;
    }
    savePreferences();
    applyPreferencesUi();
    await syncAccessibilityPreferences();
    appendLog("info", "Settings", state.preferences.blindModeEnabled
      ? "Blind mode enabled. Voice output and input are forced on."
      : "Blind mode disabled.");
    if (state.preferences.blindModeEnabled) {
      maybeShowBlindModeOnboarding();
    }
  });

  elements.minimalUiToggle.addEventListener("change", () => {
    state.preferences.minimalUi = elements.minimalUiToggle.checked;
    savePreferences();
    applyPreferencesUi();
  });

  elements.visualOnlyToggle.addEventListener("change", async () => {
    if (state.preferences.blindModeEnabled) {
      elements.visualOnlyToggle.checked = false;
      return;
    }
    state.preferences.visualOnly = elements.visualOnlyToggle.checked;
    savePreferences();
    applyPreferencesUi();
    await syncAccessibilityPreferences();
    appendLog("info", "Settings", state.preferences.visualOnly
      ? "Visual-only feedback enabled. Voice output is muted."
      : "Voice output re-enabled.");
  });
}

async function boot() {
  loadPreferences();
  applyPreferencesUi();
  bindEvents();

  const snapshot = await window.pixelink.getState();
  updateRuntime(snapshot.runtime);
  appendLog("info", "Maes", "Console ready.");

  await syncAccessibilityPreferences();
  state.hasInitialPreferenceSync = true;
  if (state.preferences.blindModeEnabled) {
    maybeShowBlindModeOnboarding();
  }

  if (!snapshot.runtime?.voice?.outputEnabled && !state.preferences.visualOnly) {
    appendLog("warning", "Voice Output", "Voice output is not available. Check voice config/API key.");
  }
  const backendOnline = snapshot.runtime?.backend === "online";
  if (backendOnline && !snapshot.runtime?.eyeControl?.available) {
    appendLog("info", "Eye Control", "Eye control is unavailable (install opencv-python and mediapipe, and allow camera access).");
  }

  window.pixelink.onRuntimeUpdate((runtime) => {
    updateRuntime(runtime);
    ensureContinuousVoiceLoop();
  });

  if (typeof window.pixelink.onVoiceModelStatus === "function") {
    window.pixelink.onVoiceModelStatus((model) => {
      updateVoiceModelStatus(model);
      updateVoiceButtonState();
    });
  }

  if (typeof window.pixelink.onAnnouncement === "function") {
    window.pixelink.onAnnouncement((payload) => {
      const message = String(payload?.message || "").trim();
      if (!message) {
        return;
      }
      const priority = String(payload?.priority || "polite");
      announce(message, priority);
      appendLog("info", "Announcement", message);
    });
  }

  window.pixelink.onBridgeError((payload) => {
    if (payload && payload.error && typeof payload.error === "object") {
      const hintText = Array.isArray(payload.error.hints) && payload.error.hints.length
        ? ` Tips: ${payload.error.hints.join(" ")}`
        : "";
      const summary = payload.error.user_message || payload.user_message || payload.error.details || "Unknown error";
      appendLog("error", "Bridge Error", `${summary}${hintText}`);
      return;
    }
    appendLog("error", "Bridge Error", payload.error || "Unknown error");
  });

  window.pixelink.onBridgeLog((payload) => {
    appendLog("info", "Bridge Log", payload.line || "");
  });

  ensureContinuousVoiceLoop();
}

boot().catch((error) => {
  appendLog("error", "Fatal", String(error.message || error));
});

window.addEventListener("beforeunload", () => {
  stopEyePreviewCamera();
});
