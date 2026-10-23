import { useEffect } from "react";
import useTorqueStore from "../state/useTorqueStore";
import { connect } from "../services/websocket";

export default function useTorqueConnection() {
  const setState = useTorqueStore((s) => s.setState);
  const setMessage = useTorqueStore((s) => s.setMessage);
  const setConnected = useTorqueStore((s) => s.setConnected);

  useEffect(() => {
    const connection = connect({
      onMessage: (data) => {
        if (data.state) setState(data.state);
        if (data.message !== undefined) setMessage(data.message);
      },
      onStatus: setConnected,
    });

    return () => connection.close();
  }, [setState, setMessage, setConnected]);

  // Development-only fallback for working on the UI without the backend.
  useEffect(() => {
    if (!import.meta.env.DEV) return;

    const states = {
      1: ["idle", ""],
      2: ["listening", "Listening..."],
      3: ["thinking", "Thinking..."],
      4: ["searching", "Searching the web..."],
      5: ["speaking", "Opening Spotify."],
    };

    function onKey(e) {
      const entry = states[e.key];

      if (!entry) return;

      setState(entry[0]);
      setMessage(entry[1]);
    }

    window.addEventListener("keydown", onKey);

    return () => window.removeEventListener("keydown", onKey);
  }, [setState, setMessage]);
}
