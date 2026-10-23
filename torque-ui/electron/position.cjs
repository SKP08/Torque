// Pure placement maths, kept separate from Electron so it can be tested.

const MARGIN = 24;

/**
 * Where the overlay window goes inside a display's work area (the part not
 * covered by the taskbar). `position` is "bottom", "top" or "center".
 */
function computeBounds(workArea, size, position = "bottom") {
  const width = Math.min(size.width, workArea.width);
  const height = Math.min(size.height, workArea.height);

  const x = Math.round(workArea.x + (workArea.width - width) / 2);

  let y;

  switch (position) {
    case "top":
      y = workArea.y + MARGIN;
      break;

    case "center":
      y = workArea.y + (workArea.height - height) / 2;
      break;

    default:
      y = workArea.y + workArea.height - height - MARGIN;
  }

  return { x, y: Math.round(y), width, height };
}

/** Full-screen mode (holographic panels): the whole display, taskbar included. */
function fullBounds(display) {
  return { x: display.x, y: display.y, width: display.width, height: display.height };
}

module.exports = { computeBounds, fullBounds, MARGIN };
