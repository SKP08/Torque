// Torque's overlay: a transparent, always-on-top, click-through window that
// shows the assistant card. Python starts this and serves the page.

const path = require("node:path");
const { app, BrowserWindow, ipcMain, screen } = require("electron");
const { computeBounds } = require("./position.cjs");

const UI_URL = process.env.TORQUE_UI_URL || "http://127.0.0.1:5174";
const POSITION = process.env.TORQUE_OVERLAY_POSITION || "bottom";
const SIZE = { width: 620, height: 260 };
const RETRY_MS = 1000;

if (!app.requestSingleInstanceLock()) {
  app.quit();
}

let win = null;

function place() {
  const display = screen.getDisplayNearestPoint(screen.getCursorScreenPoint());

  win.setBounds(computeBounds(display.workArea, SIZE, POSITION));
}

function create() {
  win = new BrowserWindow({
    ...SIZE,
    show: false,
    transparent: true,
    frame: false,
    resizable: false,
    movable: false,
    hasShadow: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    focusable: false,           // never steals focus from what you're typing in
    fullscreenable: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: false,   // keep animating while unfocused
    },
  });

  win.setAlwaysOnTop(true, "screen-saver");
  win.setIgnoreMouseEvents(true);     // clicks pass straight through

  const origin = new URL(UI_URL).origin;

  // The page is local and trusted, but nothing else should ever load here.
  win.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  win.webContents.on("will-navigate", (event, url) => {
    if (new URL(url).origin !== origin) event.preventDefault();
  });

  // Torque's server may not be up yet: keep retrying quietly.
  win.webContents.on("did-fail-load", () => {
    setTimeout(() => win && !win.isDestroyed() && win.loadURL(UI_URL), RETRY_MS);
  });

  win.loadURL(UI_URL);
}

function fromOurPage(event) {
  try {
    return new URL(event.senderFrame.url).origin === new URL(UI_URL).origin;
  } catch {
    return false;
  }
}

ipcMain.on("overlay:show", (event) => {
  if (!fromOurPage(event) || !win) return;

  place();
  win.showInactive();
});

ipcMain.on("overlay:hide", (event) => {
  if (fromOurPage(event) && win) win.hide();
});

ipcMain.on("overlay:quit", (event) => {
  if (fromOurPage(event)) app.quit();
});

app.whenReady().then(create);

// Stay alive while hidden; only quit through overlay:quit or Python.
app.on("window-all-closed", () => app.quit());
