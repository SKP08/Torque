import { create } from "zustand";

// States in which the overlay is on screen.
const ACTIVE = new Set(["listening", "thinking", "searching", "speaking"]);

// Keep the card up briefly after Torque finishes, so the last words are readable.
const LINGER_MS = 700;

// Inside the Electron overlay the card appears and disappears; in a plain
// browser tab it stays visible so the page isn't blank.
export const IS_OVERLAY = typeof window !== "undefined" && Boolean(window.torqueOverlay);

let hideTimer = null;

const useTorqueStore = create((set) => ({
  state: "loading",
  message: "",
  heard: "",
  level: 0,
  connected: false,
  visible: !IS_OVERLAY,

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
