import useTorqueStore from "../state/useTorqueStore";

export default function GlassPanel() {
  const message = useTorqueStore((s) => s.message);
  const connected = useTorqueStore((s) => s.connected);

  return (
    <>
      {/* Connection indicator */}
      <div
        title={connected ? "Connected to Torque" : "Waiting for Torque..."}
        style={{
          position: "fixed",
          top: 14,
          right: 14,
          width: 8,
          height: 8,
          borderRadius: "50%",
          background: connected ? "#4ade80" : "#f87171",
          opacity: 0.7,
          transition: ".3s",
        }}
      />

      {message && (
        <div
          style={{
            position: "fixed",
            left: "50%",
            bottom: 40,
            transform: "translateX(-50%)",

            minWidth: 240,
            maxWidth: "calc(100vw - 32px)",

            padding: "16px 22px",

            borderRadius: 22,

            color: "white",

            fontSize: 18,

            backdropFilter: "blur(28px)",

            background: "rgba(255,255,255,.08)",

            border: "1px solid rgba(255,255,255,.15)",

            boxShadow:
              "0 15px 60px rgba(0,0,0,.35), 0 0 50px rgba(70,170,255,.18)",

            textAlign: "center",

            fontFamily: "Inter, Segoe UI, sans-serif",

            userSelect: "none",
          }}
        >
          {message}
        </div>
      )}
    </>
  );
}
