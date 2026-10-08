import { useEffect } from "react";
import useTorqueStore from "../state/useTorqueStore";
import { connect } from "../services/websocket";

export default function useKeyboardState() {
  const setState = useTorqueStore((s) => s.setState);
  const setMessage = useTorqueStore((s) => s.setMessage);

  useEffect(() => {

    connect((data) => {

      if (data.state) {
        setState(data.state);
      }

      if (data.message !== undefined) {
        setMessage(data.message);
      }

    });

  }, []);

  // Temporary keyboard fallback
  useEffect(() => {

    function key(e) {

      switch (e.key) {

        case "1":
          setState("idle");
          setMessage("");
          break;

        case "2":
          setState("listening");
          setMessage("I'm listening...");
          break;

        case "3":
          setState("thinking");
          setMessage("Thinking...");
          break;

        case "4":
          setState("speaking");
          setMessage("Opening Spotify...");
          break;

      }

    }

    window.addEventListener("keydown", key);

    return () => window.removeEventListener("keydown", key);

  }, []);

}