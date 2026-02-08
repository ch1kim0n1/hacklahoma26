const state = {
  runtime: null,
  logs: [],
  voiceListening: false
};

const elements = {
  statusDot: document.getElementById("statusDot"),
  statusText: document.getElementById("statusText"),
  logArea: document.getElementById("logArea"),
  commandForm: document.getElementById("commandForm"),
  commandInput: document.getElementById("commandInput"),
  voiceBtn: document.getElementById("voiceBtn"),
  hideBtn: document.getElementById("hideBtn")
};

function appendLog(level, title, message) {
  const time = new Date().toLocaleTimeString();
  state.logs.unshift({ level, title, message, time });
  state.logs = state.logs.slice(0, 120);
  renderLogs();
}

function renderLogs() {
  elements.logArea.innerHTML = "";
  state.logs.forEach((entry) => {
    const node = document.createElement("article");
    node.className = `log-entry log-${entry.level}`;
    node.innerHTML = `<strong>${entry.time} • ${entry.title}</strong>${entry.message || ""}`;
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
    elements.statusText.textContent = "Needs Clarification";
    return;
  }

  if (waitingConfirm) {
    elements.statusDot.className = "status-dot status-warn";
    elements.statusText.textContent = "Awaiting Confirmation";
    return;
  }

  elements.statusDot.className = "status-dot status-online";
  elements.statusText.textContent = "Online";
}

function updateRuntime(runtime) {
  state.runtime = runtime;
  setStatus(runtime);
  updateVoiceButtonState();
}

function updateVoiceButtonState() {
  if (!elements.voiceBtn) {
    return;
  }
  const backendOnline = state.runtime?.backend === "online";
  const voiceInputEnabled = Boolean(state.runtime?.voice?.inputEnabled);
  const active = state.voiceListening || state.runtime?.voiceCaptureActive;
  const phase = state.runtime?.voicePhase || "idle";
  const enabled = backendOnline && voiceInputEnabled && !active;

  elements.voiceBtn.disabled = !enabled;
  elements.voiceBtn.classList.toggle("listening", active);

  if (active) {
    if (phase === "processing") {
      elements.voiceBtn.textContent = "Processing...";
    } else if (phase === "speaking") {
      elements.voiceBtn.textContent = "Speaking...";
    } else {
      elements.voiceBtn.textContent = "Listening...";
    }
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

function formatStructuredError(result) {
  if (!result || !result.error || typeof result.error !== "object") {
    return result?.message || "";
  }
  const code = result.error.code || "UNKNOWN";
  const details = result.error.details || result.message || "No details";
  return `[${code}] ${details}`;
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

async function submitVoiceCommand() {
  if (state.voiceListening) {
    return;
  }

  state.voiceListening = true;
  updateVoiceButtonState();
  appendLog("info", "Voice", "Listening for command...");

  try {
    const result = await window.pixelink.captureVoiceInput("", { continuous: true });
    logResult(result);
    state.voiceListening = false;
    updateVoiceButtonState();
  } catch (error) {
    appendLog("error", "Voice Error", String(error.message || error));
    state.voiceListening = false;
    updateVoiceButtonState();
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
}

async function boot() {
  bindEvents();

  const snapshot = await window.pixelink.getState();
  updateRuntime(snapshot.runtime);
  appendLog("info", "PixelLink", "Console ready.");

  if (!snapshot.runtime?.voice?.outputEnabled) {
    appendLog("warning", "Voice Output", "Voice output is not available. Check voice config/API key.");
  }

  window.pixelink.onRuntimeUpdate((runtime) => {
    updateRuntime(runtime);
  });

  window.pixelink.onBridgeError((payload) => {
    if (payload && payload.error && typeof payload.error === "object") {
      appendLog("error", "Bridge Error", `[${payload.error.code || "BRIDGE"}] ${payload.error.details || "Unknown error"}`);
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
