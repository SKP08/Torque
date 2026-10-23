import { motion } from "framer-motion";

export default function HoloPanel({ panel, index }) {
  const hasImage = Boolean(panel.image);

  return (
    <motion.article
      className={`holo-panel${hasImage ? " has-image" : ""}`}
      initial={{ opacity: 0, x: 60, scale: 0.92, filter: "blur(8px)" }}
      animate={{ opacity: 1, x: 0, scale: 1, filter: "blur(0px)" }}
      exit={{ opacity: 0, x: 40, scale: 0.96, filter: "blur(6px)" }}
      transition={{ type: "spring", stiffness: 220, damping: 26, delay: 0.18 + index * 0.16 }}
      style={{ "--float": `${index * 0.7}s` }}
    >
      <span className="holo-scan" aria-hidden />

      {hasImage && (
        <div className="holo-image">
          <img src={panel.image} alt={panel.title} draggable={false} />
        </div>
      )}

      <div className="holo-body">
        <h2>{panel.title}</h2>
        {panel.description && <div className="holo-sub">{panel.description}</div>}
        {panel.text && <p>{panel.text}</p>}
      </div>
    </motion.article>
  );
}
