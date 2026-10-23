import "./App.css";

import Overlay from "./components/Overlay";

import useTorqueConnection from "./hooks/useTorqueConnection";

export default function App() {
  useTorqueConnection();

  return <Overlay />;
}
