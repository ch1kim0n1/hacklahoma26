const statusBtn = document.getElementById("statusBtn");
const statusIcon = document.getElementById("statusIcon");
const statusDot = document.getElementById("statusDot");
const voiceBtn = document.getElementById("voiceBtn");

const ICONS = {
  idle: "../../assets/idle.png",
  listen: "../../assets/listening.png",
  action: "../../assets/action.png"
};

function setRuntimeVisuals(runtime) {
  const backendOnline = runtime?.backend === "online";
  const waiting = Boolean(runtime?.pendingConfirmation || runtime?.pendingClarification);
  const pipelineState = String(runtime?.pipelineState || "idle").toLowerCase();
  const stage = pipelineState === "listen" ? "listen" : (pipelineState === "idle" ? "idle" : "action");

  if (!backendOnline) {
    statusDot.className = "status-dot status-offline";
  } else if (waiting) {
    statusDot.className = "status-dot status-warn";
  } else {
    statusDot.className = "status-dot status-online";
  }

  statusBtn.classList.remove("stage-idle", "stage-listen", "stage-action");
  statusBtn.classList.add(`stage-${stage}`);
  if (statusIcon && statusIcon.getAttribute("src") !== ICONS[stage]) {
    statusIcon.setAttribute("src", ICONS[stage]);
  }
}

async function invokeVoiceAgent() {
  if (!voiceBtn || voiceBtn.disabled) {
    return;
  }
  voiceBtn.disabled = true;
  voiceBtn.classList.add("busy");
  try {
    await window.pixelink.captureVoiceInput();
  } catch (_) {
    // Ignore launcher-level errors. Runtime events handle user-facing status.
  } finally {
    voiceBtn.disabled = false;
    voiceBtn.classList.remove("busy");
  }
}

voiceBtn.addEventListener("click", async () => {
  await invokeVoiceAgent();
});

async function boot() {
  const snapshot = await window.pixelink.getState();
  setRuntimeVisuals(snapshot.runtime);
  window.pixelink.onRuntimeUpdate((runtime) => {
    setRuntimeVisuals(runtime);
  });
}

boot().catch(() => {
  statusDot.className = "status-dot status-offline";
});
