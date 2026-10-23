import { useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";

import OrbScene from "../scene/OrbScene";
import LevelBars from "./LevelBars";
import HoloLayer from "../hud/HoloLayer";
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
  const hud = useTorqueStore((s) => s.hud);
  const clearAfterHide = useTorqueStore((s) => s.clearAfterHide);

  // The native window is shown before anything animates in. Panels need the
  // whole screen; the card alone needs only its small window.
  useEffect(() => {
    if (hud) overlay?.mode("full");
    if (visible || hud) overlay?.show();
  }, [visible, hud]);

  // ...and hidden once everything has animated out.
  function hideIfIdle() {
    const s = useTorqueStore.getState();

    if (s.hud) return;

    overlay?.mode("card");

    if (!s.visible) overlay?.hide();
  }

  function onExitComplete() {
    clearAfterHide();
    hideIfIdle();
  }

  const label = connected ? LABELS[state] ?? "" : "Waiting for Torque";
  const reply = state === "speaking" || state === "idle" ? message : "";

  return (
    <div className="stage">
      <HoloLayer hud={hud} onGone={hideIfIdle} />

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
