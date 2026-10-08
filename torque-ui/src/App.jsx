import "./App.css";

import OrbScene from "./scene/OrbScene";
import GlassPanel from "./components/GlassPanel";

import useKeyboardState from "./hooks/useKeyboardState";

export default function App() {

  useKeyboardState();

  return (
    <>
      <OrbScene />
      <GlassPanel />
    </>
  );
}