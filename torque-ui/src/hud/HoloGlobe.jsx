import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import { arcPoints, graticuleSegments, lonLatToVector, rotationFor, wrapAngle } from "./geo";
import { worldBorders } from "./worldData";

const CYAN = "#7bd8ff";
const AMBER = "#ffc857";

function lineGeometry(positions) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  return geometry;
}

function Marker({ lon, lat, color = AMBER }) {
  const ring = useRef();
  const position = useMemo(() => lonLatToVector(lon, lat, 1.01), [lon, lat]);
  const quaternion = useMemo(
    () => new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), new THREE.Vector3(...position).normalize()),
    [position],
  );

  useFrame(({ clock }) => {
    if (!ring.current) return;
    const t = (clock.elapsedTime % 1.6) / 1.6;
    ring.current.scale.setScalar(1 + t * 2.4);
    ring.current.material.opacity = 0.9 * (1 - t);
  });

  return (
    <group position={position} quaternion={quaternion}>
      <mesh>
        <circleGeometry args={[0.018, 20]} />
        <meshBasicMaterial color={color} />
      </mesh>
      <mesh ref={ring}>
        <ringGeometry args={[0.03, 0.036, 32]} />
        <meshBasicMaterial color={color} transparent depthWrite={false} />
      </mesh>
    </group>
  );
}

function Arc({ from, to, color = CYAN, offset = 0 }) {
  const pulse = useRef();
  const points = useMemo(() => arcPoints(from, to).map((p) => new THREE.Vector3(...p)), [from, to]);
  const geometry = useMemo(() => new THREE.BufferGeometry().setFromPoints(points), [points]);

  useFrame(({ clock }) => {
    if (!pulse.current) return;
    const t = (clock.elapsedTime * 0.35 + offset) % 1;
    pulse.current.position.copy(points[Math.min(points.length - 1, Math.floor(t * points.length))]);
  });

  return (
    <group>
      <line geometry={geometry}>
        <lineBasicMaterial color={color} transparent opacity={0.55} />
      </line>
      <mesh ref={pulse}>
        <sphereGeometry args={[0.014, 8, 8]} />
        <meshBasicMaterial color="#ffffff" />
      </mesh>
    </group>
  );
}

function Globe({ target, arcs, home, markers }) {
  const group = useRef();
  const borders = useMemo(() => lineGeometry(worldBorders()), []);
  const grid = useMemo(() => lineGeometry(graticuleSegments(20, 1.0, 4)), []);

  const aim = useMemo(() => {
    if (target) return rotationFor(target.lon, target.lat);
    return null;
  }, [target]);

  useFrame((state, delta) => {
    const g = group.current;
    if (!g) return;

    const k = 1 - Math.exp(-delta * 2.2);

    if (aim) {
      g.rotation.x += (aim[0] - g.rotation.x) * k;
      g.rotation.y += wrapAngle(aim[1] - g.rotation.y) * k;
    } else {
      g.rotation.y += delta * 0.12;
    }

    // Dolly in on a target; stay pulled back for the whole-world view.
    const z = aim ? 3.1 : 3.6;
    state.camera.position.z += (z - state.camera.position.z) * k;
  });

  return (
    <group ref={group} rotation={[0.25, aim ? -0.6 : 0, 0]}>
      <mesh>
        <sphereGeometry args={[0.995, 48, 32]} />
        <meshBasicMaterial color="#04202c" transparent opacity={0.62} />
      </mesh>
      <lineSegments geometry={grid}>
        <lineBasicMaterial color={CYAN} transparent opacity={0.13} />
      </lineSegments>
      <lineSegments geometry={borders}>
        <lineBasicMaterial color={CYAN} transparent opacity={0.85} />
      </lineSegments>

      {target && <Marker lon={target.lon} lat={target.lat} />}
      {home && <Marker lon={home.lon} lat={home.lat} color="#5eead4" />}

      {(markers ?? []).map((m) => (
        <Marker key={`m${m.lon},${m.lat}`} lon={m.lon} lat={m.lat} color={CYAN} />
      ))}

      {(arcs ?? []).map((arc, i) => (
        <Arc key={`${arc.to.lon},${arc.to.lat},${i}`} from={arc.from} to={arc.to} offset={(i * 0.37) % 1} />
      ))}
    </group>
  );
}

export default function HoloGlobe({ target = null, arcs = null, home = null, markers = null }) {
  return (
    <Canvas
      className="holo-globe"
      camera={{ position: [0, 0, 5], fov: 38 }}
      gl={{ alpha: true, antialias: true }}
      dpr={[1, 2]}
    >
      <Globe target={target} arcs={arcs} home={home} markers={markers} />
    </Canvas>
  );
}
