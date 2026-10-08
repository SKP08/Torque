import { EffectComposer, Bloom } from "@react-three/postprocessing";

export default function Glow() {
    return (
        <EffectComposer>
            <Bloom
                intensity={2.5}
                luminanceThreshold={0.1}
                luminanceSmoothing={0.9}
            />
        </EffectComposer>
    );
}