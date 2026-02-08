const { app, BrowserWindow, ipcMain, screen } = require("electron");
const { spawn } = require("child_process");
const path = require("path");

const REPO_ROOT = path.resolve(__dirname, "..");
const BRIDGE_PATH = path.join(REPO_ROOT, "pylink", "desktop_bridge.py");
const VENV_PYTHON = process.platform === "win32"
  ? path.join(REPO_ROOT, ".venv", "Scripts", "python.exe")
  : path.join(REPO_ROOT, ".venv", "bin", "python");

let mainWindow = null;
let launcherWindow = null;
let bridgeProcess = null;
let bridgeBuffer = "";
let bridgeReady = false;
let bridgePending = new Map();
let bridgeRequestSeq = 0;
let isQuitting = false;

const runtimeState = {
  backend: "offline",
  dryRun: false,
  speed: 1.0,
  pendingConfirmation: false,
  pendingClarification: false,
  clarificationPrompt: "",
  lastResult: null,
  voiceCaptureActive: false,
  voicePhase: "idle",
  voice: {
    requestedInput: true,
    requestedOutput: true,
    inputEnabled: false,
    outputEnabled: false,
    errors: {}
  },
  permissionProfile: {
    open_app: true,
    focus_app: true,
    close_app: true,
    open_url: true,
    open_file: true,
    send_text_native: true,
    type_text: true,
    click: true,
    right_click: true,
    double_click: true,
    scroll: true,
    press_key: true,
    hotkey: true,
    send_email: true,
    send_message: true,
    wait: true,
    reminders_create_reminder: true,
    reminders_list_lists: true,
    reminders_list_reminders: true,
    notes_create_note: true,
    notes_list_folders: true,
    notes_list_notes: true,
    gmail_list_messages: true,
    gmail_get_message: true,
    gmail_send_message: true,
    calendar_list_events: true,
    calendar_create_event: true,
    calendar_delete_event: true,
    gmail_read_first: true,
    autofill_login: true
  }
};

function broadcast(channel, payload) {
  BrowserWindow.getAllWindows().forEach((windowRef) => {
    if (!windowRef.isDestroyed()) {
      windowRef.webContents.send(channel, payload);
    }
  });
}

function normalizeVoiceState(payload) {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  return {
    requestedInput: payload.requestedInput ?? payload.requested_input ?? runtimeState.voice.requestedInput,
    requestedOutput: payload.requestedOutput ?? payload.requested_output ?? runtimeState.voice.requestedOutput,
    inputEnabled: payload.inputEnabled ?? payload.input_enabled ?? runtimeState.voice.inputEnabled,
    outputEnabled: payload.outputEnabled ?? payload.output_enabled ?? runtimeState.voice.outputEnabled,
    errors: payload.errors && typeof payload.errors === "object" ? payload.errors : runtimeState.voice.errors
  };
}

function applyRuntimeResult(result) {
  runtimeState.lastResult = result;
  if (result.voice_phase) {
    runtimeState.voicePhase = result.voice_phase;
  }
  if (typeof result.pending_confirmation === "boolean") {
    runtimeState.pendingConfirmation = result.pending_confirmation;
  }
  if (typeof result.pending_clarification === "boolean") {
    runtimeState.pendingClarification = result.pending_clarification;
  }
  runtimeState.clarificationPrompt = result.clarification_prompt || "";
  const normalizedVoice = normalizeVoiceState(result.voice);
  if (normalizedVoice) {
    runtimeState.voice = {
      ...runtimeState.voice,
      ...normalizedVoice
    };
  }
  broadcast("runtime:update", runtimeState);
}

function applyBridgeReadyPayload(payload) {
  runtimeState.backend = "online";
  runtimeState.dryRun = Boolean(payload.dry_run);
  runtimeState.speed = Number(payload.speed || 1.0);
  const normalizedVoice = normalizeVoiceState(payload.voice);
  if (normalizedVoice) {
    runtimeState.voice = {
      ...runtimeState.voice,
      ...normalizedVoice
    };
  }
  broadcast("runtime:update", runtimeState);
}

function onBridgeLine(rawLine) {
  const line = rawLine.trim();
  if (!line) {
    return;
  }

  let payload = null;
  try {
    payload = JSON.parse(line);
  } catch (_) {
    broadcast("runtime:bridge-log", { line });
    return;
  }

  if (payload.status === "ready" && !bridgeReady) {
    bridgeReady = true;
    applyBridgeReadyPayload(payload);
  }

  if (payload.status === "voice_phase" && payload.phase) {
    runtimeState.voicePhase = payload.phase;
    broadcast("runtime:update", runtimeState);
    return;
  }

  const requestId = String(payload.request_id || "");
  if (requestId && bridgePending.has(requestId)) {
    const pending = bridgePending.get(requestId);
    bridgePending.delete(requestId);
    clearTimeout(pending.timeout);
    pending.resolve(payload);
    return;
  }

  if (payload.status === "error" && payload.error) {
    broadcast("runtime:bridge-error", payload);
  }

  applyRuntimeResult(payload);
}

function failPendingRequests(error) {
  bridgePending.forEach((pending, requestId) => {
    clearTimeout(pending.timeout);
    pending.reject(error);
    bridgePending.delete(requestId);
  });
}

function getPythonCommandCandidates() {
  const candidates = [];
  // Prefer repo-local virtualenv if present (ensures optional MCP deps are available).
  try {
    if (require("fs").existsSync(VENV_PYTHON)) {
      candidates.push(VENV_PYTHON);
    }
  } catch (_) {
    // ignore
  }
  return candidates.concat(process.platform === "win32" ? ["python", "py"] : ["python3", "python"]);
}

function spawnBridge(command) {
  return new Promise((resolve, reject) => {
    bridgeBuffer = "";
    const child = spawn(command, [BRIDGE_PATH], {
      cwd: REPO_ROOT,
      env: {
        ...process.env,
        PYTHONUNBUFFERED: "1",
        PIXELINK_ENABLE_KILL_SWITCH: "0"
      },
      stdio: ["pipe", "pipe", "pipe"]
    });

    let resolved = false;
    const timeout = setTimeout(() => {
      if (!resolved) {
        child.kill();
        reject(new Error(`Bridge startup timed out for '${command}'`));
      }
    }, 8000);

    child.stdout.on("data", (chunk) => {
      bridgeBuffer += chunk.toString("utf8");
      const lines = bridgeBuffer.split("\n");
      bridgeBuffer = lines.pop() || "";

      for (const line of lines) {
        if (!resolved) {
          try {
            const payload = JSON.parse(line.trim());
            if (payload.status === "ready") {
              resolved = true;
              clearTimeout(timeout);
              bridgeProcess = child;
              bridgeReady = true;
              applyBridgeReadyPayload(payload);
              setupBridgeProcessListeners(child);
              resolve();
              continue;
            }
          } catch (_) {
            // Ignore non-JSON lines before bridge ready.
          }
        }
        onBridgeLine(line);
      }
    });

    child.stderr.on("data", (chunk) => {
      const text = chunk.toString("utf8");
      // The Python bridge may emit non-fatal warnings to stderr (e.g. optional plugins
      // skipped due to missing deps). Surface those as logs so they don't look like failures.
      const lines = text.split(/\r?\n/).filter(Boolean);
      for (const line of lines) {
        if (line.startsWith("[bridge] Skipping plugin")) {
          broadcast("runtime:bridge-log", { line });
        } else {
          broadcast("runtime:bridge-error", { error: line });
        }
      }
    });

    child.on("error", (error) => {
      clearTimeout(timeout);
      if (!resolved) {
        reject(error);
      }
    });

    child.on("exit", (code) => {
      clearTimeout(timeout);
      if (!resolved) {
        reject(new Error(`Bridge exited early with code ${code}`));
      }
    });
  });
}

async function startBridge() {
  const commands = getPythonCommandCandidates();
  let lastError = null;
  for (const command of commands) {
    try {
      await spawnBridge(command);
      return;
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error("Unable to start Python bridge");
}

function setupBridgeProcessListeners(child) {
  child.on("exit", (code) => {
    bridgeReady = false;
    runtimeState.backend = "offline";
    broadcast("runtime:update", runtimeState);
    failPendingRequests(new Error(`Bridge exited with code ${code}`));
  });

  child.on("error", (error) => {
    bridgeReady = false;
    runtimeState.backend = "offline";
    broadcast("runtime:update", runtimeState);
    failPendingRequests(error);
  });
}

function sendBridgeRequest(payload) {
  if (!bridgeProcess || !bridgeReady) {
    return Promise.reject(new Error("Python bridge is not ready"));
  }

  return new Promise((resolve, reject) => {
    bridgeRequestSeq += 1;
    const requestId = `req-${Date.now()}-${bridgeRequestSeq}`;
    const requestPayload = { ...payload, request_id: requestId };
    // Agent + tool calls and voice listen can take 20–60+ seconds
    const ms = (payload.action === "process_input" || payload.action === "capture_voice_input") ? 60000 : 12000;
    const timeout = setTimeout(() => {
      bridgePending.delete(requestId);
      reject(new Error(`Bridge request timeout for action '${payload.action}' (${requestId})`));
    }, ms);

    bridgePending.set(requestId, { resolve, reject, timeout });

    try {
      bridgeProcess.stdin.write(`${JSON.stringify(requestPayload)}\n`);
    } catch (error) {
      clearTimeout(timeout);
      bridgePending.delete(requestId);
      reject(error);
    }
  });
}

async function processRuntimeInput(text, source = "text") {
  const result = await sendBridgeRequest({ action: "process_input", text, source });
  applyRuntimeResult(result);
  return result;
}

async function captureVoiceInput(prompt = "", options = {}) {
  const { continuous = false } = options;
  runtimeState.voiceCaptureActive = true;
  broadcast("runtime:update", runtimeState);

  let result;
  try {
    result = await sendBridgeRequest({
      action: "capture_voice_input",
      prompt
    });
  } catch (err) {
    runtimeState.voiceCaptureActive = false;
    runtimeState.voicePhase = "idle";
    broadcast("runtime:update", runtimeState);
    throw err;
  }
  applyRuntimeResult(result);

  // Continuous voice: auto-start next listen when AI starts speaking (unless voice is off)
  const canContinue =
    continuous &&
    runtimeState.voice?.inputEnabled &&
    (result.status !== "error" || result.error?.code === "VOICE_INPUT_EMPTY");
  if (canContinue) {
    result._continuous = true;
    runtimeState.voicePhase = "listening";
    setImmediate(() => captureVoiceInput("", { continuous: true }));
  } else {
    runtimeState.voiceCaptureActive = false;
    runtimeState.voicePhase = "idle";
  }
  broadcast("runtime:update", runtimeState);
  return result;
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 500,
    height: 360,
    minWidth: 420,
    minHeight: 280,
    show: false,
    title: "PixelLink",
    backgroundColor: "#f2f4f8",
    titleBarStyle: "hiddenInset",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  });

  mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
  mainWindow.on("close", (event) => {
    if (!isQuitting) {
      event.preventDefault();
      mainWindow.hide();
    }
  });
}

function createLauncherWindow() {
  const launcherSize = 62;
  const { workArea } = screen.getPrimaryDisplay();
  const x = Math.round(workArea.x + workArea.width - launcherSize - 18);
  const y = Math.round(workArea.y + workArea.height - launcherSize - 18);

  launcherWindow = new BrowserWindow({
    width: launcherSize,
    height: launcherSize,
    x,
    y,
    show: true,
    frame: false,
    transparent: true,
    resizable: false,
    movable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    hasShadow: false,
    title: "PixelLink Launcher",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  });

  launcherWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  launcherWindow.loadFile(path.join(__dirname, "renderer", "launcher.html"));
}

function openMainWindow() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }
  mainWindow.show();
  mainWindow.focus();
}

function registerIpcHandlers() {
  ipcMain.handle("runtime:get-state", async () => ({ runtime: runtimeState }));

  ipcMain.handle("runtime:send-input", async (_event, payload) => {
    const text = String(payload?.text || "");
    const source = String(payload?.source || "text");
    return processRuntimeInput(text, source);
  });

  ipcMain.handle("runtime:capture-voice-input", async (_event, payload) => {
    const prompt = String(payload?.prompt || "");
    const continuous = Boolean(payload?.continuous);
    return captureVoiceInput(prompt, { continuous });
  });

  ipcMain.handle("runtime:confirm", async (_event, payload) => {
    const source = String(payload?.source || "text");
    return processRuntimeInput("confirm", source);
  });

  ipcMain.handle("runtime:cancel", async (_event, payload) => {
    const source = String(payload?.source || "text");
    return processRuntimeInput("cancel", source);
  });

  ipcMain.handle("runtime:update-preferences", async (_event, payload) => {
    const speed = Number(payload?.speed || runtimeState.speed);
    const permissionProfile = payload?.permissionProfile || runtimeState.permissionProfile;
    runtimeState.speed = speed;
    runtimeState.permissionProfile = permissionProfile;
    const response = await sendBridgeRequest({
      action: "update_preferences",
      speed,
      permission_profile: permissionProfile,
      voice_output_enabled: payload?.voiceOutputEnabled,
      voice_input_enabled: payload?.voiceInputEnabled
    });
    const normalizedVoice = normalizeVoiceState(response.voice);
    if (normalizedVoice) {
      runtimeState.voice = {
        ...runtimeState.voice,
        ...normalizedVoice
      };
    }
    broadcast("runtime:update", runtimeState);
    return response;
  });

  ipcMain.handle("ui:open-main", async () => {
    openMainWindow();
    return { ok: true };
  });

  ipcMain.handle("ui:hide-main", async () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.hide();
    }
    return { ok: true };
  });
}

async function shutdownBridge() {
  if (!bridgeProcess || !bridgeReady) {
    return;
  }
  try {
    await sendBridgeRequest({ action: "shutdown" });
  } catch (_) {
    // Ignore errors during quit.
  }
  bridgeReady = false;
  bridgeProcess.kill();
}

app.whenReady().then(async () => {
  registerIpcHandlers();
  createMainWindow();
  createLauncherWindow();

  try {
    await startBridge();
  } catch (error) {
    runtimeState.backend = "offline";
    broadcast("runtime:bridge-error", { error: String(error.message || error) });
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
      createLauncherWindow();
    } else {
      openMainWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("before-quit", async () => {
  isQuitting = true;
  await shutdownBridge();
});
