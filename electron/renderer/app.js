const PREFERENCES_KEY = "pixelink.ui.preferences.v1";

const state = {
  runtime: null,
  logs: [],
  voiceListening: false,
  voiceModel: null,
  lastModelErrorSignature: "",
  preferences: {
    reducedLoad: false,
    minimalUi: false,
    visualOnly: false
  }
};

const elements = {
  consoleRoot: document.querySelector(".console"),
  statusDot: document.getElementById("statusDot"),
  statusText: document.getElementById("statusText"),
  logArea: document.getElementById("logArea"),
  commandForm: document.getElementById("commandForm"),
  commandInput: document.getElementById("commandInput"),
  voiceBtn: document.getElementById("voiceBtn"),
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
  runtimeHints: document.getElementById("runtimeHints"),
  runtimeModeBadges: document.getElementById("runtimeModeBadges"),
  runtimeHintText: document.getElementById("runtimeHintText")
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

function applyPreferencesUi() {
  elements.reducedLoadToggle.checked = Boolean(state.preferences.reducedLoad);
  elements.minimalUiToggle.checked = Boolean(state.preferences.minimalUi);
  elements.visualOnlyToggle.checked = Boolean(state.preferences.visualOnly);
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
  if (entry.level === "info" && !["Command", "Voice", "Heard", "PixelLink", "Model"].includes(entry.title)) {
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

  if (!backendOnline) {
    elements.statusDot.className = "status-dot status-offline";
    elements.statusText.textContent = "Offline";
    return;
  }

  if (waitingClarification) {
    elements.statusDot.className = "status-dot status-warn";
    elements.statusText.textContent = state.preferences.reducedLoad ? "Need Input" : "Needs Clarification";
    return;
  }

  if (waitingConfirm) {
    elements.statusDot.className = "status-dot status-warn";
    elements.statusText.textContent = state.preferences.reducedLoad ? "Need Confirm" : "Awaiting Confirmation";
    return;
  }

  elements.statusDot.className = "status-dot status-online";
  elements.statusText.textContent = "Online";
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

function updateRuntime(runtime) {
  state.runtime = runtime;
  setStatus(runtime);
  updateVoiceModelStatus(runtime?.voice?.model);
  updateVoiceButtonState();
  updateEyeControlButton();
  updateEyePreview(runtime);
  renderRuntimeHints(runtime);
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
  const eyeError = eye.lastError ? `\nError: ${eye.lastError}` : "";
  elements.eyePreviewStats.textContent =
    `Blink: ${eye.lastBlink || "-"}\n` +
    `EAR: ${ear}\n` +
    `Gaze: ${gaze}\n` +
    `Norm: ${gazeNorm}\n` +
    `Iris: ${eye.irisTracking ? "on" : "off"}\n` +
    `Mode: ${eye.controlMode || "face"}\n` +
    `Backend: ${eye.backend || "-"} (${previewStatus})` +
    eyeError;
}

function updateVoiceButtonState() {
  const backendOnline = state.runtime?.backend === "online";
  const voiceInputEnabled = Boolean(state.runtime?.voice?.inputEnabled);
  const modelLoading = ["loading", "idle"].includes(String(state.runtime?.voice?.model?.state || "").toLowerCase())
    && String(state.runtime?.voice?.model?.stage || "").toLowerCase() !== "ready";
  const enabled = backendOnline && voiceInputEnabled && !state.voiceListening && !modelLoading;

  elements.voiceBtn.disabled = !enabled;
  elements.voiceBtn.classList.toggle("listening", state.voiceListening);

  if (state.voiceListening) {
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
    const reason = state.runtime?.eyeControl?.availabilityReason || state.runtime?.eyeControl?.lastError || "camera or dependencies missing";
    elements.eyeControlBtn.title = `Eye control unavailable: ${reason}`;
  } else if (eyeActive) {
    elements.eyeControlBtn.textContent = "Eye On";
    elements.eyeControlBtn.title = "Eye and blink control active. Click to turn off.";
  } else {
    elements.eyeControlBtn.textContent = "Eye";
    elements.eyeControlBtn.title = "Click to enable eye and blink control (gaze moves cursor, double blink = click)";
  }
}

function renderRuntimeHints(runtime) {
  if (!elements.runtimeHints || !elements.runtimeModeBadges || !elements.runtimeHintText) {
    return;
  }
  const badges = [];
  const hints = [];
  const eye = runtime?.eyeControl || {};
  const voice = runtime?.voice || {};
  const platformInfo = runtime?.platform || {};
  const pendingAction = runtime?.pendingAction || runtime?.pending_action || null;
  const pendingConfirmation = Boolean(runtime?.pendingConfirmation || runtime?.pending_confirmation);
  const pendingClarification = Boolean(runtime?.pendingClarification || runtime?.pending_clarification);

  if (runtime?.backend !== "online") {
    elements.runtimeHints.classList.add("hidden");
    return;
  }

  if (platformInfo.support_tier && platformInfo.support_tier !== "stable") {
    badges.push({ label: "Platform: experimental", variant: "warn" });
    if (platformInfo.message) {
      hints.push(platformInfo.message);
    }
  } else {
    badges.push({ label: "Platform: stable", variant: "active" });
  }

  if (voice.inputEnabled) {
    badges.push({ label: "Voice Input", variant: "active" });
  }
  if (voice.outputEnabled) {
    badges.push({ label: "Voice Output", variant: "active" });
  }
  if (eye.active) {
    badges.push({ label: "Eye Control", variant: "active" });
  }
  if (pendingClarification) {
    badges.push({ label: "Need Clarification", variant: "warn" });
  } else if (pendingConfirmation) {
    badges.push({ label: "Need Confirmation", variant: "warn" });
  }

  if (pendingAction?.action === "autofill_login") {
    const service = pendingAction?.params?.service || "selected service";
    hints.push(`Credential autofill pending for ${service}. Credentials stay local and are never displayed.`);
  } else if (pendingConfirmation && eye.active) {
    hints.push("Eye shortcut: single blink confirms; double blink cancels.");
  }

  if (!eye.available && eye.availabilityReason) {
    hints.push(`Eye control unavailable: ${eye.availabilityReason}`);
  }
  if (voice.errors && Object.keys(voice.errors).length > 0) {
    hints.push("Voice availability is degraded. Check voice diagnostics in the log feed.");
  }

  const filteredHints = Array.from(new Set(hints.filter(Boolean)));
  const shouldShow = badges.length > 0 || filteredHints.length > 0;
  elements.runtimeHints.classList.toggle("hidden", !shouldShow);
  if (!shouldShow) {
    return;
  }

  elements.runtimeModeBadges.innerHTML = badges
    .map((item) => `<span class=\"runtime-badge ${item.variant || ""}\">${item.label}</span>`)
    .join("");
  elements.runtimeHintText.textContent = filteredHints.slice(0, 2).join(" ");
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

async function submitVoiceCommand() {
  if (state.voiceListening) {
    return;
  }

  state.voiceListening = true;
  updateVoiceButtonState();
  appendLog("info", "Voice", "Listening for command...");

  try {
    const result = await window.pixelink.captureVoiceInput();
    logResult(result);
  } catch (error) {
    appendLog("error", "Voice Error", String(error.message || error));
  } finally {
    state.voiceListening = false;
    updateVoiceButtonState();
  }
}

async function syncVoicePreferences() {
  if (!state.runtime || state.runtime.backend !== "online") {
    return;
  }
  try {
    const response = await window.pixelink.updatePreferences({
      voiceOutputEnabled: !state.preferences.visualOnly
    });
    if (response?.voice) {
      updateRuntime({
        ...state.runtime,
        voice: response.voice
      });
    }
  } catch (error) {
    appendLog("error", "Settings", `Failed to apply visual-only feedback: ${String(error.message || error)}`);
  }
}

function bindEvents() {
  document.addEventListener("keydown", async (event) => {
    if (event.key !== "Escape") {
      return;
    }
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
  });

  elements.commandForm.addEventListener("submit", (event) => {
    event.preventDefault();
    submitCommand(elements.commandInput.value);
  });

  elements.voiceBtn.addEventListener("click", async () => {
    await submitVoiceCommand();
  });

  elements.eyeControlBtn.addEventListener("click", async () => {
    const eyeActive = Boolean(state.runtime?.eyeControl?.active);
    try {
      if (eyeActive) {
        const result = await window.pixelink.stopEyeControl();
        if (result?.status === "error") {
          logResult(result);
          return;
        }
        appendLog("info", "Eye Control", "Eye control turned off.");
      } else {
        state.eyePreviewUnsupported = false;
        const result = await window.pixelink.startEyeControl();
        if (result?.status === "error") {
          logResult(result);
          return;
        }
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

  elements.minimalUiToggle.addEventListener("change", () => {
    state.preferences.minimalUi = elements.minimalUiToggle.checked;
    savePreferences();
    applyPreferencesUi();
  });

  elements.visualOnlyToggle.addEventListener("change", async () => {
    state.preferences.visualOnly = elements.visualOnlyToggle.checked;
    savePreferences();
    applyPreferencesUi();
    await syncVoicePreferences();
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
  appendLog("info", "PixelLink", "Console ready.");

  if (state.preferences.visualOnly) {
    await syncVoicePreferences();
  }

  if (!snapshot.runtime?.voice?.outputEnabled && !state.preferences.visualOnly) {
    appendLog("warning", "Voice Output", "Voice output is not available. Check voice config/API key.");
  }
  if (snapshot.runtime?.voice?.requestedInput && !snapshot.runtime?.voice?.inputEnabled) {
    const sttError = snapshot.runtime?.voice?.errors?.stt || "Speech input is unavailable in this environment.";
    appendLog("warning", "Voice Input", sttError);
  }
  if (snapshot.runtime?.platform?.support_tier && snapshot.runtime.platform.support_tier !== "stable") {
    appendLog("warning", "Platform", snapshot.runtime?.platform?.message || "Running on an experimental platform.");
  }
  const backendOnline = snapshot.runtime?.backend === "online";
  if (backendOnline && !snapshot.runtime?.eyeControl?.available) {
    const reason = snapshot.runtime?.eyeControl?.availabilityReason || "install opencv-python and mediapipe, and allow camera access";
    appendLog("info", "Eye Control", `Eye control is unavailable (${reason}).`);
  }

  window.pixelink.onRuntimeUpdate((runtime) => {
    updateRuntime(runtime);
  });

  if (typeof window.pixelink.onVoiceModelStatus === "function") {
    window.pixelink.onVoiceModelStatus((model) => {
      updateVoiceModelStatus(model);
      updateVoiceButtonState();
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
}

boot().catch((error) => {
  appendLog("error", "Fatal", String(error.message || error));
});

window.addEventListener("beforeunload", () => {
  stopEyePreviewCamera();
});
