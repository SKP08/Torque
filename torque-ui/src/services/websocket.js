const URL = "ws://localhost:8765";

const MIN_DELAY = 500;
const MAX_DELAY = 5000;

/**
 * Connects to Torque and keeps reconnecting (with backoff) until the
 * returned function is called.
 */
export function connect({ onMessage, onStatus }) {
  let socket = null;
  let timer = null;
  let delay = MIN_DELAY;
  let closed = false;

  function open() {
    socket = new WebSocket(URL);

    socket.onopen = () => {
      delay = MIN_DELAY;
      onStatus?.(true);
    };

    socket.onmessage = (event) => {
      try {
        onMessage(JSON.parse(event.data));
      } catch {
        console.warn("Ignoring malformed message from Torque");
      }
    };

    socket.onclose = () => {
      onStatus?.(false);

      if (closed) return;

      timer = setTimeout(open, delay);
      delay = Math.min(delay * 2, MAX_DELAY);
    };

    socket.onerror = () => socket.close();
  }

  open();

  return {
    send(data) {
      if (socket?.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify(data));
      }
    },

    close() {
      closed = true;
      clearTimeout(timer);
      socket?.close();
    },
  };
}
