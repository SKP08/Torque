import { AnimatePresence, motion } from "framer-motion";
import { lazy, Suspense } from "react";

import HoloPanel from "./HoloPanel";
import StatusPanel from "./StatusPanel";

// three.js is only needed when a globe is shown.
const HoloGlobe = lazy(() => import("./HoloGlobe"));

function InfoView({ hud }) {
  const panels = hud.panels ?? [];
  const geo = hud.geo ?? null;

  return (
    <div className={`holo-grid${geo ? " with-globe" : ""}`}>
      {geo && (
        <motion.div
          className="holo-globe-wrap"
          initial={{ opacity: 0, scale: 0.7 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.85 }}
          transition={{ type: "spring", stiffness: 120, damping: 20 }}
        >
          <Suspense fallback={null}>
            <HoloGlobe target={geo} />
          </Suspense>
          {geo.label && <div className="globe-label">{geo.label}</div>}
        </motion.div>
      )}

      <div className="holo-column">
        {panels.map((panel, i) => (
          <HoloPanel key={panel.title} panel={panel} index={i} />
        ))}
      </div>
    </div>
  );
}

function NetworkView({ hud }) {
  const home = hud.home ?? null;
  const arcs = home ? (hud.connections ?? []).map((c) => ({ from: home, to: c })) : [];

  return (
    <div className="holo-grid with-globe network">
      <motion.div
        className="holo-globe-wrap"
        initial={{ opacity: 0, scale: 0.7 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.85 }}
        transition={{ type: "spring", stiffness: 120, damping: 20 }}
      >
        <Suspense fallback={null}>
          <HoloGlobe home={home} arcs={arcs} />
        </Suspense>
      </motion.div>

      <div className="holo-column">
        <motion.section className="holo-panel" initial={{ opacity: 0, x: 60 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }}>
          <span className="holo-scan" aria-hidden />
          <h2>Network</h2>
          <ul className="top-list">
            {(hud.connections ?? []).slice(0, 8).map((c) => (
              <li key={`${c.country}-${c.process}`}>
                <span>{c.country || "Unknown"} · {c.process}</span><b>{c.count}</b>
              </li>
            ))}
          </ul>
        </motion.section>
      </div>
    </div>
  );
}

export default function HoloLayer({ hud, onGone }) {
  return (
    <AnimatePresence onExitComplete={onGone}>
      {hud && (
        <motion.div
          key={hud.id}
          className="holo-layer"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.35 }}
        >
          <span className="corner tl" /><span className="corner tr" />
          <span className="corner bl" /><span className="corner br" />

          {hud.kind === "status" && <div className="holo-center"><StatusPanel status={hud} /></div>}
          {hud.kind === "info" && <InfoView hud={hud} />}
          {hud.kind === "network" && <NetworkView hud={hud} />}

          {hud.kind === "info" && (
            <div className="holo-attribution">Source: Wikipedia · CC BY-SA 4.0 &nbsp;|&nbsp; Images: Wikimedia Commons</div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
