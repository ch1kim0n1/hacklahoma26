const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("pixelink", {
  getState: () => ipcRenderer.invoke("runtime:get-state"),
  sendInput: (text, source = "text") => ipcRenderer.invoke("runtime:send-input", { text, source }),
  captureVoiceInput: (prompt = "") => ipcRenderer.invoke("runtime:capture-voice-input", { prompt }),
  confirm: (source = "text") => ipcRenderer.invoke("runtime:confirm", { source }),
  cancel: (source = "text") => ipcRenderer.invoke("runtime:cancel", { source }),
  updatePreferences: (preferences) => ipcRenderer.invoke("runtime:update-preferences", preferences),
  openMain: () => ipcRenderer.invoke("ui:open-main"),
  hideMain: () => ipcRenderer.invoke("ui:hide-main"),
  onRuntimeUpdate: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("runtime:update", listener);
    return () => ipcRenderer.removeListener("runtime:update", listener);
  },
  onBridgeError: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("runtime:bridge-error", listener);
    return () => ipcRenderer.removeListener("runtime:bridge-error", listener);
  },
  onBridgeLog: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("runtime:bridge-log", listener);
    return () => ipcRenderer.removeListener("runtime:bridge-log", listener);
  },
  onVoiceModelStatus: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("runtime:voice-model-status", listener);
    return () => ipcRenderer.removeListener("runtime:voice-model-status", listener);
  }
});
