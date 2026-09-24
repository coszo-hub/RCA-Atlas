// Widths the side panels take from the map, including their 16 px margins (see --left-inset / --right-inset).
export const INSET = { chat: 412, side: 472, none: 16 };

// The top row fits header (320) + gap (8) + terrain controls (252) side by side; narrower, it wraps and the
// controls drop into the middle of the map. Keep in step with the `hud` container query in ui.css.
export const HUD_ROW_WIDTH = 580;
export const hudWraps = (width, chatOpen, panelOpen) =>
  width - (chatOpen ? INSET.chat : INSET.none) - (panelOpen ? INSET.side : INSET.none) < HUD_ROW_WIDTH;

// The lowest edge of the top-row HUD the map must keep clear of: the left stack (header, regions) and the right
// stack's controls and toggles. An expanded legend is left out: it opens only when there is room beside the map's
// middle, or when the user asks for it, and counting it would push the overview down under the family strip.
export function hudBottom(leftStack, rightStack) {
  const boxes = [leftStack, ...[...(rightStack?.children ?? [])].filter(el => !el.classList.contains("legend"))];
  return Math.max(0, ...boxes.filter(Boolean).map(el => el.getBoundingClientRect().bottom));
}
