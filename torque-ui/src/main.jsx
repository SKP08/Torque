import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.jsx";

// Inside the Electron overlay the page background must stay transparent.
if (window.torqueOverlay) {
  document.documentElement.classList.add("overlay");
}

createRoot(document.getElementById("root")).render(<App />);
