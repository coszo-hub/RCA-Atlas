// Widths the side panels take from the map, including their 16 px margins (see --left-inset / --right-inset).
// The side panel's is its default width (440 px); App uses the panel's current, draggable width (ui/sideWidth.js).
export const INSET = { chat: 412, side: 472, none: 16 };

// The lowest edge of the top-row HUD the map must keep clear of: the left stack (header, regions) and the right
// stack (the dock). The dock's popovers hang below it out of flow, so they are not counted and opening one never
// reframes the camera.
export const hudBottom = (leftStack, rightStack) =>
  Math.max(0, ...[leftStack, rightStack].filter(Boolean).map(el => el.getBoundingClientRect().bottom));
