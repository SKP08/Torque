import { AnimatePresence, motion } from "framer-motion";

export default function Toast({ toast, onGone }) {
  return (
    <AnimatePresence onExitComplete={onGone}>
      {toast && (
        <motion.div
          key={toast.id}
          className={`holo-toast ${toast.severity === "warn" ? "warn" : ""}`}
          initial={{ opacity: 0, x: 80, filter: "blur(6px)" }}
          animate={{ opacity: 1, x: 0, filter: "blur(0px)" }}
          exit={{ opacity: 0, x: 60 }}
          transition={{ type: "spring", stiffness: 260, damping: 28 }}
          role="status"
        >
          <span className="holo-scan" aria-hidden />
          <span className="toast-mark" aria-hidden />
          <span>{toast.message}</span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
