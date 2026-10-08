import { extend } from "@react-three/fiber";
import { shaderMaterial } from "@react-three/drei";

import vertexShader from "./orb.vert?raw";
import fragmentShader from "./orb.frag?raw";

const OrbMaterial = shaderMaterial(
  {
    time: 0,
  },
  vertexShader,
  fragmentShader
);

extend({ OrbMaterial });

export { OrbMaterial };