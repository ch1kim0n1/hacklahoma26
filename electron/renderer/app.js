const state = {
  runtime: null,
  logs: []
};

const elements = {
  statusDot: document.getElementById("statusDot"),
  statusText: document.getElementById("statusText"),
  logArea: document.getElementById("logArea"),
  commandForm: document.getElementById("commandForm"),
  commandInput: document.getElementById("commandInput"),
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
    const level = classifyLevel(result);
    appendLog(level, result.status || "Result", result.message || "");

    if (result.pending_clarification && result.clarification_prompt) {
      appendLog("warning", "Follow-up", result.clarification_prompt);
    }
  } catch (error) {
    appendLog("error", "Error", String(error.message || error));
  }
}

function bindEvents() {
  elements.commandForm.addEventListener("submit", (event) => {
    event.preventDefault();
    submitCommand(elements.commandInput.value);
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

  window.pixelink.onRuntimeUpdate((runtime) => {
    updateRuntime(runtime);
  });

  window.pixelink.onBridgeError((payload) => {
    appendLog("error", "Bridge Error", payload.error || "Unknown error");
  });

  window.pixelink.onBridgeLog((payload) => {
    appendLog("info", "Bridge Log", payload.line || "");
  });
}

boot().catch((error) => {
  appendLog("error", "Fatal", String(error.message || error));
});

