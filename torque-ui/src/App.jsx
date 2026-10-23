import "./App.css";

import OrbScene from "./scene/OrbScene";
import GlassPanel from "./components/GlassPanel";

import useTorqueConnection from "./hooks/useTorqueConnection";

export default function App() {
  useTorqueConnection();

  return (
    <>
      <OrbScene />
      <GlassPanel />
    </>
  );
}
