const { contextBridge, ipcRenderer } = require("electron");

// The page can only ask for these three things.
contextBridge.exposeInMainWorld("torqueOverlay", {
  show: () => ipcRenderer.send("overlay:show"),
  hide: () => ipcRenderer.send("overlay:hide"),
  quit: () => ipcRenderer.send("overlay:quit"),
});
