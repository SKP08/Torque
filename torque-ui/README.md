# torque-ui

React + Three.js orb that mirrors Torque's state. Started automatically by
the Python runtime (`npm run dev`, port 5173). It connects to
`ws://localhost:8765` and reacts to `{state, message}` messages.

Development without the backend: press keys 1-5 to preview
idle / listening / thinking / searching / speaking.
