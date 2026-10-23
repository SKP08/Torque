const { contextBridge, ipcRenderer } = require("electron");

// The page can only ask for these few things.
contextBridge.exposeInMainWorld("torqueOverlay", {
  show: () => ipcRenderer.send("overlay:show"),
  mode: (mode) => ipcRenderer.send("overlay:mode", mode === "full" ? "full" : "card"),
  hide: () => ipcRenderer.send("overlay:hide"),
  quit: () => ipcRenderer.send("overlay:quit"),
});
