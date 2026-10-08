let socket = null;

export function connect(onMessage) {
  socket = new WebSocket("ws://localhost:8765");

  socket.onopen = () => {
    console.log("✅ Connected to Torque");
  };

  socket.onmessage = (event) => {
    const data = JSON.parse(event.data);
    onMessage(data);
  };

  socket.onclose = () => {
    console.log("⚠️ Disconnected. Reconnecting...");
    setTimeout(() => connect(onMessage), 1000);
  };

  socket.onerror = (err) => {
    console.error(err);
  };
}