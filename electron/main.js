const { app, BrowserWindow, ipcMain, screen, systemPreferences } = require("electron");
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
  pipelineState: "idle",
  pendingConfirmation: false,
  pendingClarification: false,
  clarificationPrompt: "",
  lastResult: null,
  voice: {
    requestedInput: true,
    requestedOutput: true,
    inputEnabled: false,
    outputEnabled: false,
    errors: {},
    model: {
      model: "",
      state: "unavailable",
      stage: "unavailable",
      message: "Voice input is unavailable.",
      progress: 0,
      cached: null,
      error: ""
    }
  },
  eyeControl: {
    active: false,
    available: false,
    lastGaze: null,
    lastBlink: null,
    lastEar: null,
    blinkState: "open",
    gazeNorm: null,
    irisTracking: false,
    controlMode: "face",
    backend: null,
    previewActive: false,
    lastError: null
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
    mcp_create_reminder: true,
    mcp_create_note: true,
    mcp_list_reminders: true,
    mcp_list_notes: true,
    mcp_get_events: true,
    mcp_create_event: true,
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

function normalizeVoiceModelState(payload) {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  return {
    model: payload.model ?? runtimeState.voice.model.model,
    state: payload.state ?? runtimeState.voice.model.state,
    stage: payload.stage ?? runtimeState.voice.model.stage,
    message: payload.message ?? runtimeState.voice.model.message,
    progress: Number.isFinite(Number(payload.progress)) ? Number(payload.progress) : runtimeState.voice.model.progress,
    cached: payload.cached ?? runtimeState.voice.model.cached,
    error: payload.error ?? runtimeState.voice.model.error
  };
}

function normalizeVoiceState(payload) {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const model = normalizeVoiceModelState(payload.model || payload.voice_model);
  return {
    requestedInput: payload.requestedInput ?? payload.requested_input ?? runtimeState.voice.requestedInput,
    requestedOutput: payload.requestedOutput ?? payload.requested_output ?? runtimeState.voice.requestedOutput,
    inputEnabled: payload.inputEnabled ?? payload.input_enabled ?? runtimeState.voice.inputEnabled,
    outputEnabled: payload.outputEnabled ?? payload.output_enabled ?? runtimeState.voice.outputEnabled,
    errors: payload.errors && typeof payload.errors === "object" ? payload.errors : runtimeState.voice.errors,
    model: model || runtimeState.voice.model
  };
}

function normalizeEyeState(payload) {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  return {
    active: Boolean(payload.active),
    available: Boolean(payload.available),
    lastGaze: payload.last_gaze ?? null,
    lastBlink: payload.last_blink ?? null,
    lastEar: payload.last_ear ?? null,
    blinkState: payload.blink_state ?? "open",
    gazeNorm: payload.gaze_norm ?? null,
    irisTracking: Boolean(payload.iris_tracking),
    controlMode: payload.control_mode ?? "face",
    backend: payload.backend ?? null,
    previewActive: Boolean(payload.preview_active),
    lastError: payload.last_error ?? null
  };
}

function applyRuntimeResult(result) {
  runtimeState.lastResult = result;
  if (result.pipeline_state) {
    runtimeState.pipelineState = result.pipeline_state;
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
  if (result.eye_control && typeof result.eye_control === "object") {
    const normalizedEye = normalizeEyeState(result.eye_control);
    if (normalizedEye) {
      runtimeState.eyeControl = normalizedEye;
    }
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
  if (payload.eye_control && typeof payload.eye_control === "object") {
    const normalizedEye = normalizeEyeState(payload.eye_control);
    if (normalizedEye) {
      runtimeState.eyeControl = normalizedEye;
    }
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

  if (payload.status === "pipeline_state") {
    runtimeState.pipelineState = payload.state || "idle";
    broadcast("runtime:pipeline-state", { state: runtimeState.pipelineState });
    broadcast("runtime:update", runtimeState);
    return;
  }

  if (payload.status === "voice_model_status") {
    const model = normalizeVoiceModelState(payload.voice_model || payload.model);
    if (model) {
      runtimeState.voice = {
        ...runtimeState.voice,
        model
      };
      broadcast("runtime:voice-model-status", model);
      broadcast("runtime:update", runtimeState);
    }
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

function classifyBridgeStderrLine(line) {
  const text = String(line || "").trim();
  if (!text) {
    return "ignore";
  }
  // Expected noisy startup logs from MediaPipe / TensorFlow Lite / macOS camera stack.
  if (
    text.startsWith("W0000 ") ||
    text.startsWith("I0000 ") ||
    text.includes("inference_feedback_manager.cc") ||
    text.includes("face_landmarker_graph.cc") ||
    text.includes("gl_context.cc") ||
    text.includes("TensorFlow Lite XNNPACK delegate") ||
    text.includes("AVCaptureDeviceTypeExternal is deprecated") ||
    text.includes("Class AVFAudioReceiver is implemented in both") ||
    text.includes("Class AVFFrameReceiver is implemented in both")
  ) {
    return "ignore";
  }
  if (text.startsWith("[eye] ")) {
    return "log";
  }
  if (text.startsWith("[bridge] Skipping plugin")) {
    return "log";
  }
  return "error";
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
      const lines = text.split(/\r?\n/).filter(Boolean);
      for (const line of lines) {
        const classification = classifyBridgeStderrLine(line);
        if (classification === "log") {
          broadcast("runtime:bridge-log", { line });
        } else if (classification === "error") {
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
    const timeoutMs = payload.action === "capture_voice_input" || payload.action === "process_input" ? 120000 : 12000;
    const timeout = setTimeout(() => {
      bridgePending.delete(requestId);
      reject(new Error(`Bridge request timeout for action '${payload.action}' (${requestId})`));
    }, timeoutMs);

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

async function captureVoiceInput(prompt = "") {
  const result = await sendBridgeRequest({
    action: "capture_voice_input",
    prompt
  });
  applyRuntimeResult(result);
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
    return captureVoiceInput(prompt);
  });

  ipcMain.handle("runtime:confirm", async (_event, payload) => {
    const source = String(payload?.source || "text");
    return processRuntimeInput("confirm", source);
  });

  ipcMain.handle("runtime:cancel", async (_event, payload) => {
    const source = String(payload?.source || "text");
    return processRuntimeInput("cancel", source);
  });

  ipcMain.handle("eye:start", async () => {
    const result = await sendBridgeRequest({ action: "eye_control_start" });
    applyRuntimeResult(result);
    return result;
  });

  ipcMain.handle("eye:stop", async () => {
    const result = await sendBridgeRequest({ action: "eye_control_stop" });
    applyRuntimeResult(result);
    return result;
  });

  ipcMain.handle("eye:get-state", async () => {
    const result = await sendBridgeRequest({ action: "eye_control_get_state" });
    if (result && result.eye_control) {
      const normalizedEye = normalizeEyeState(result.eye_control);
      if (normalizedEye) {
        runtimeState.eyeControl = normalizedEye;
        broadcast("runtime:update", runtimeState);
      }
    }
    return result;
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
  // Request microphone permission on macOS before starting the bridge
  if (process.platform === "darwin") {
    const micStatus = systemPreferences.getMediaAccessStatus("microphone");
    if (micStatus !== "granted") {
      try {
        await systemPreferences.askForMediaAccess("microphone");
      } catch (_) {
        // Permission denied or unavailable - bridge will handle gracefully
      }
    }
  }

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
