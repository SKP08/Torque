import { Canvas, useFrame } from "@react-three/fiber";
import { useRef } from "react";
import Glow from "./Glow";
import "../shaders/OrbMaterial";
import VoiceRing from "../components/VoiceRing";
import useTorqueStore from "../state/useTorqueStore";

function Orb() {
  const mesh = useRef();
  const material = useRef();

  const state = useTorqueStore((s) => s.state);

  useFrame(({ clock }) => {
    const t = clock.elapsedTime;

    if (material.current) material.current.time = t;

    if (!mesh.current) return;

    mesh.current.rotation.y += 0.002;

    let target;

    switch (state) {
      case "listening":
        target = 1.08;
        break;

      case "thinking":
        target = 1.14;
        break;

      case "searching":
        target = 1.1 + Math.sin(t * 5) * 0.03;
        break;

      case "loading":
        target = 0.92 + Math.sin(t * 3) * 0.02;
        break;

      case "speaking":
        target = 1.05 + Math.sin(t * 8) * 0.04;
        break;

      default:
        target = 1 + Math.sin(t * 2) * 0.02;
    }

    mesh.current.scale.lerp(
      {
        x: target,
        y: target,
        z: target,
      },
      0.08
    );
  });

  return (
    <mesh ref={mesh}>
      <sphereGeometry args={[1, 96, 96]} />
      <orbMaterial ref={material} />
    </mesh>
  );
}

export default function OrbScene() {
  return (
    <Canvas
      dpr={[1, 1.5]}
      camera={{
        position: [0, 0, 3],
        fov: 45,
      }}
    >
      <ambientLight intensity={0.3} />

      <pointLight
        position={[3, 3, 3]}
        intensity={15}
        color="#66ddff"
      />

      {/* Voice Ring */}
      <VoiceRing />

      {/* Main Orb */}
      <Orb />

      {/* Bloom */}
      <Glow />
    </Canvas>
  );
}