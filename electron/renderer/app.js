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
  hideBtn: document.getElementById("hideBtn"),
  reducedLoadToggle: document.getElementById("reducedLoadToggle"),
  minimalUiToggle: document.getElementById("minimalUiToggle"),
  visualOnlyToggle: document.getElementById("visualOnlyToggle"),
  voiceModelStatus: document.getElementById("voiceModelStatus"),
  voiceModelMessage: document.getElementById("voiceModelMessage"),
  voiceModelPercent: document.getElementById("voiceModelPercent"),
  voiceModelProgress: document.getElementById("voiceModelProgress")
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
  elements.commandForm.addEventListener("submit", (event) => {
    event.preventDefault();
    submitCommand(elements.commandInput.value);
  });

  elements.voiceBtn.addEventListener("click", async () => {
    await submitVoiceCommand();
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
