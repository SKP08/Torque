import { useEffect } from "react";
import useTorqueStore from "../state/useTorqueStore";
import { connect } from "../services/websocket";

// If Torque is gone for this long, an overlay window has no reason to exist.
const QUIT_AFTER_MS = 15000;

export default function useTorqueConnection() {
  useEffect(() => {
    const store = useTorqueStore.getState();
    let quitTimer = null;

    const connection = connect({
      onMessage: (data) => {
        if (typeof data.level === "number") {
          store.setLevel(data.level);
          return;
        }

        // Order matters: the state change decides whether text is cleared.
        if (data.state) store.setState(data.state);
        if (data.heard !== undefined) store.setHeard(data.heard);
        if (data.message !== undefined) store.setMessage(data.message);
      },

      onStatus: (connected) => {
        store.setConnected(connected);

        clearTimeout(quitTimer);

        if (!connected && window.torqueOverlay) {
          quitTimer = setTimeout(() => window.torqueOverlay.quit(), QUIT_AFTER_MS);
        }
      },
    });

    return () => {
      clearTimeout(quitTimer);
      connection.close();
    };
  }, []);

  // Development-only fallback for working on the UI without the backend.
  useEffect(() => {
    if (!import.meta.env.DEV) return;

    const steps = {
      1: ["idle", ""],
      2: ["listening", "Listening..."],
      3: ["thinking", "Thinking..."],
      4: ["searching", "Searching the web..."],
      5: ["speaking", "Opening Spotify."],
    };

    function onKey(e) {
      const step = steps[e.key];

      if (!step) return;

      const store = useTorqueStore.getState();

      store.setState(step[0]);
      store.setMessage(step[1]);

      if (step[0] === "thinking") store.setHeard("open spotify");
    }

    window.addEventListener("keydown", onKey);

    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
