import { useEffect, useRef } from "react";
import useTorqueStore from "../state/useTorqueStore";

const WEIGHTS = [0.55, 0.85, 1, 0.8, 0.5];

// Microphone level bars. Updated straight on the DOM every frame so the
// 20 Hz level stream doesn't re-render React.
export default function LevelBars() {
  const bars = useRef([]);

  useEffect(() => {
    let frame;
    let smooth = 0;

    function tick(time) {
      const target = useTorqueStore.getState().level;

      smooth += (target - smooth) * 0.35;

      bars.current.forEach((bar, i) => {
        if (!bar) return;

        const wobble = 0.5 + 0.5 * Math.sin(time / 140 + i * 1.3);

        const height = 0.18 + WEIGHTS[i] * smooth * (0.55 + 0.45 * wobble);

        bar.style.transform = `scaleY(${Math.min(1, height)})`;
      });

      frame = requestAnimationFrame(tick);
    }

    frame = requestAnimationFrame(tick);

    return () => cancelAnimationFrame(frame);
  }, []);

  return (
    <div className="bars" aria-hidden="true">
      {WEIGHTS.map((_, i) => (
        <span key={i} ref={(el) => (bars.current[i] = el)} />
      ))}
    </div>
  );
}
