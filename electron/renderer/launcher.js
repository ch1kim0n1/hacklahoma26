const openBtn = document.getElementById("openBtn");
const launcherDot = document.getElementById("launcherDot");

function setDotStatus(runtime) {
  const backendOnline = runtime?.backend === "online";
  const waiting = Boolean(runtime?.pendingConfirmation || runtime?.pendingClarification);

  if (!backendOnline) {
    launcherDot.className = "dot status-offline";
    return;
  }
  if (waiting) {
    launcherDot.className = "dot status-warn";
    return;
  }
  launcherDot.className = "dot status-online";
}

openBtn.addEventListener("click", async () => {
  await window.pixelink.openMain();
});

async function boot() {
  const snapshot = await window.pixelink.getState();
  setDotStatus(snapshot.runtime);
  window.pixelink.onRuntimeUpdate((runtime) => {
    setDotStatus(runtime);
  });
}

boot().catch(() => {
  launcherDot.className = "dot status-offline";
});

