import { motion } from "framer-motion";

export default function Orb() {
  return (
    <motion.div
      animate={{
        scale: [1, 1.05, 1],
      }}
      transition={{
        duration: 2,
        repeat: Infinity,
        ease: "easeInOut",
      }}
      style={{
        width: 140,
        height: 140,
        borderRadius: "50%",
        background:
          "radial-gradient(circle at 30% 30%, white 0%, #6BE8FF 35%, #1EA7FF 75%, #006CFF 100%)",
        boxShadow:
          "0 0 80px rgba(0,170,255,.45), 0 0 160px rgba(0,170,255,.15)",
      }}
    />
  );
}