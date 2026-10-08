import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import * as THREE from "three";
import useTorqueStore from "../state/useTorqueStore";

export default function VoiceRing() {
  const mesh = useRef();

  const state = useTorqueStore((s) => s.state);

  useFrame(({ clock }) => {
    if (!mesh.current) return;

    const t = clock.elapsedTime;

    // Show ONLY while speaking/responding
    const visible = state === "speaking";

    const targetOpacity = visible ? 1 : 0;

    const targetScale = visible
      ? 1.48 + Math.sin(t * 12) * 0.05
      : 1.35;

    mesh.current.scale.lerp(
      new THREE.Vector3(targetScale, targetScale, targetScale),
      0.08
    );

    if (visible) {
      mesh.current.rotation.z += 0.006;
    }

    mesh.current.material.opacity = THREE.MathUtils.lerp(
      mesh.current.material.opacity,
      targetOpacity,
      0.08
    );
  });

  return (
    <mesh ref={mesh}>
      <torusGeometry args={[1.35, 0.02, 32, 256]} />

      <meshBasicMaterial
        color="#7BD8FF"
        transparent
        opacity={0}
      />
    </mesh>
  );
}