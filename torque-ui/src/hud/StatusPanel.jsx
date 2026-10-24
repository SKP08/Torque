import { motion } from "framer-motion";

import { formatClock, formatRate } from "./format";

const RADIUS = 34;
const CIRC = 2 * Math.PI * RADIUS;

function colour(value, invert = false) {
  const level = invert ? 100 - value : value;
  if (level >= 90) return "#ff6b6b";
  if (level >= 70) return "#ffc857";
  return "#7bd8ff";
}

function Ring({ label, value, suffix = "%", invert = false, note }) {
  const clamped = Math.max(0, Math.min(100, value ?? 0));

  return (
    <div className="ring">
      <svg viewBox="0 0 80 80" width="96" height="96" role="img" aria-label={`${label} ${clamped}${suffix}`}>
        <circle cx="40" cy="40" r={RADIUS} className="ring-track" />
        <motion.circle
          cx="40" cy="40" r={RADIUS}
          className="ring-value"
          style={{ stroke: colour(clamped, invert) }}
          strokeDasharray={CIRC}
          initial={{ strokeDashoffset: CIRC }}
          animate={{ strokeDashoffset: CIRC * (1 - clamped / 100) }}
          transition={{ duration: 1.1, ease: "easeOut" }}
          transform="rotate(-90 40 40)"
        />
        <text x="40" y="45" textAnchor="middle" className="ring-number">{clamped}{suffix}</text>
      </svg>
      <div className="ring-label">{label}</div>
      {note && <div className="ring-note">{note}</div>}
    </div>
  );
}

export default function StatusPanel({ status }) {
  const battery = status.battery;

  return (
    <motion.section
      className="holo-panel status-panel"
      initial={{ opacity: 0, scale: 0.9, filter: "blur(8px)" }}
      animate={{ opacity: 1, scale: 1, filter: "blur(0px)" }}
      exit={{ opacity: 0, scale: 0.96, filter: "blur(6px)" }}
      transition={{ type: "spring", stiffness: 220, damping: 26 }}
    >
      <span className="holo-scan" aria-hidden />
      <h2>System status</h2>

      <div className="rings">
        <Ring label="CPU" value={status.cpu} />
        <Ring label="Memory" value={status.memory} />
        {status.disk != null && <Ring label="Disk" value={status.disk} />}
        {battery && (
          <Ring label="Battery" value={battery.percent} invert note={battery.plugged ? "charging" : undefined} />
        )}
      </div>

      <div className="status-row">
        <span>↓ {formatRate(status.network?.down)}</span>
        <span>↑ {formatRate(status.network?.up)}</span>
        {status.uptime_hours != null && <span>up {status.uptime_hours} h</span>}
      </div>

      {status.timers?.length > 0 && (
        <ul className="top-list timers">
          {status.timers.map((t) => (
            <li key={t.label + t.seconds}><span>⏱ {t.label}</span><b>{formatClock(t.seconds)}</b></li>
          ))}
        </ul>
      )}

      {status.top?.length > 0 && (
        <ul className="top-list">
          {status.top.map((p) => (
            <li key={p.name}><span>{p.name}</span><b>{p.cpu}%</b></li>
          ))}
        </ul>
      )}
    </motion.section>
  );
}
