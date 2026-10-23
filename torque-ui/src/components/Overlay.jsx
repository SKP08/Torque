import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";

import OrbScene from "../scene/OrbScene";
import LevelBars from "./LevelBars";
import useTorqueStore from "../state/useTorqueStore";

const LABELS = {
  loading: "Starting up",
  idle: "Say \"Hey Torque\"",
  listening: "Listening",
  thinking: "Thinking",
  searching: "Searching the web",
  speaking: "Torque",
};

const overlay = typeof window !== "undefined" ? window.torqueOverlay : undefined;

export default function Overlay() {
  const state = useTorqueStore((s) => s.state);
  const message = useTorqueStore((s) => s.message);
  const heard = useTorqueStore((s) => s.heard);
  const visible = useTorqueStore((s) => s.visible);
  const connected = useTorqueStore((s) => s.connected);
  const clearAfterHide = useTorqueStore((s) => s.clearAfterHide);

  // The native window is shown before the card animates in...
  useEffect(() => {
    if (visible) overlay?.show();
  }, [visible]);

  // ...and hidden once the card has animated out.
  function onExitComplete() {
    clearAfterHide();
    overlay?.hide();
  }

  const label = connected ? LABELS[state] ?? "" : "Waiting for Torque";
  const reply = state === "speaking" || state === "idle" ? message : "";

  return (
    <div className="stage">
      <AnimatePresence onExitComplete={onExitComplete}>
        {visible && (
          <motion.div
            key="card"
            className={`card state-${state}`}
            initial={{ opacity: 0, y: 36, scale: 0.94 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.96 }}
            transition={{ type: "spring", stiffness: 380, damping: 32, mass: 0.8 }}
          >
            <div className="orb">
              <OrbScene />
            </div>

            <div className="text">
              <div className="label">
                <span>{label}</span>
                {state === "listening" && <LevelBars />}
              </div>

              {heard && <div className="heard">&ldquo;{heard}&rdquo;</div>}

              {reply && <div className="reply">{reply}</div>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
