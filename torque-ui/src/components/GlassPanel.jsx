import useTorqueStore from "../state/useTorqueStore";

export default function GlassPanel() {
  const message = useTorqueStore((s) => s.message);

  if (!message) return null;

  return (
    <div
      style={{
        position: "fixed",
        left: "50%",
        bottom: 70,
        transform: "translateX(-50%)",

        minWidth: 340,
        maxWidth: 700,

        padding: "18px 24px",

        borderRadius: 22,

        color: "white",

        fontSize: 20,

        backdropFilter: "blur(28px)",

        background: "rgba(255,255,255,.08)",

        border: "1px solid rgba(255,255,255,.15)",

        boxShadow:
          "0 15px 60px rgba(0,0,0,.35), 0 0 50px rgba(70,170,255,.18)",

        transition: ".35s",

        textAlign: "center",

        fontFamily:
          "Inter, Segoe UI, sans-serif",

        userSelect: "none",
      }}
    >
      {message}
    </div>
  );
}