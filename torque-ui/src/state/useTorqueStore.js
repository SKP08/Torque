import { create } from "zustand";

// States in which the overlay is on screen.
const ACTIVE = new Set(["listening", "thinking", "searching", "speaking"]);

// Keep the card up briefly after Torque finishes, so the last words are readable.
const LINGER_MS = 700;

// Inside the Electron overlay the card appears and disappears; in a plain
// browser tab it stays visible so the page isn't blank.
export const IS_OVERLAY = typeof window !== "undefined" && Boolean(window.torqueOverlay);

const HOLD_DEFAULT_MS = 10000;
const HOLD_MAX_MS = 60000;

let hideTimer = null;
let hudTimer = null;
let hudHoldMs = HOLD_DEFAULT_MS;

// Panels stay up while Torque is talking, then for `hold` more seconds.
function armHudTimer(get, set) {
  clearTimeout(hudTimer);

  if (!get().hud || ACTIVE.has(get().state)) return;

  hudTimer = setTimeout(() => set({ hud: null }), hudHoldMs);
}

const useTorqueStore = create((set, get) => ({
  hud: null,
  state: "loading",
  message: "",
  heard: "",
  level: 0,
  connected: false,
  visible: !IS_OVERLAY,

  setHud: (payload) => {
    if (!payload || typeof payload !== "object" || !payload.kind) {
      clearTimeout(hudTimer);
      set({ hud: null });
      return;
    }

    const hold = Number(payload.hold);

    hudHoldMs = Number.isFinite(hold) ? Math.min(Math.max(hold, 3), HOLD_MAX_MS / 1000) * 1000 : HOLD_DEFAULT_MS;

    set({ hud: { ...payload, id: Date.now() } });
    armHudTimer(get, set);
  },

  setState: (state) => {
    clearTimeout(hideTimer);

    if (ACTIVE.has(state)) {
      // A new turn starts: forget what was heard last time.
      set((s) => ({
        state,
        visible: true,
        heard: state === "listening" ? "" : s.heard,
        message: state === "listening" ? "" : s.message,
      }));
      return;
    }

    set({ state });
    armHudTimer(get, set);

    if (IS_OVERLAY) {
      hideTimer = setTimeout(() => set({ visible: false }), LINGER_MS);
    }
  },

  setMessage: (message) => set({ message }),
  setHeard: (heard) => set({ heard }),
  setLevel: (level) => set({ level }),
  setConnected: (connected) => set({ connected }),

  // Called once the exit animation has finished.
  clearAfterHide: () => set({ heard: "", message: "", level: 0 }),
}));

export default useTorqueStore;
