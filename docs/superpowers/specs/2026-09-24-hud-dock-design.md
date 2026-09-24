# Map HUD dock: terrain controls, legend and help as icons

Status: approved 2026-09-24 (Derek). First of two PRs; the Ask Atlas evidence sidebar builds on it.

## Goal

The map is the main interface. The right side of the top row currently holds two tall panels (Terrain
controls, Legend) that cover a large part of the map. Collapse them into a compact dock of icon buttons in
the top-right; each opens its existing content in a popover. The title card, the regions card, the family
strip, the chat panel and the side panels stay as they are.

## Behaviour

- A dock of three square icon buttons, top-right of the map, in a single row: **Terrain**, **Legend**,
  **Help**. Each button has an accessible name and a tooltip-style title; `aria-expanded` reflects its popover.
- Clicking a button opens its popover directly beneath the dock, right-aligned to it. Only one popover is
  open at a time; opening another closes the first. Clicking the same button again, pressing Escape, or
  clicking anywhere outside the dock and popover closes it. Escape returns focus to the button.
- **Terrain popover**: exactly today's `Controls` content (view, style, colour, vertical exaggeration,
  Axial detail, subsurface toggle and quake timeline, and the per-experiment DAS controls from `main`),
  minus the hint line. The terrain state (view, style, colour, exaggeration, DAS toggles, timeline) must
  survive closing and reopening the popover, so keep the component mounted and hide it, or lift the state.
- **Legend popover**: exactly today's `Legend` content, including the DAS coverage and "Beneath Axial"
  sections. It scrolls when taller than the space between the dock and the family strip (keep the existing
  max-height fitting, measured from the popover's top).
- **Help popover**: the controls hint that used to sit at the bottom of the terrain panel
  ("Drag to move · Ctrl-drag to rotate · Scroll to zoom · arrows to move · Hover the cable or a node for details").
- The dock sits inside the map's free area: its right edge follows `--right-inset`, so it moves left of the
  site/unplaced side panel when that is open, and back when it closes or is minimized.
- The old minimize buttons/tabs for Controls and Legend (`MinButton`/`MinTab`, the `compact` props and the
  `override` state) go away for these two; the dock replaces them.

## Layout consequences

- The right stack is now ~30 px tall, so the top row no longer needs to wrap to fit it. Remove or simplify
  `hudWraps` / `HUD_ROW_WIDTH` and the `.right-stack.compact` path accordingly; `hudBottom` should count
  the dock (not open popovers) so an open popover never reframes the camera.
- `layout.test.js` and any e2e expectations tied to the wrap behaviour are updated to the new layout.

## Visual style

Match the existing panels (`--surface-1` background, `--hairline` borders, 6–8 px radius, IBM Plex).
Buttons are 30×30 px with a 16 px monochrome line icon in `--text-secondary`, `--text-primary` on hover
and when pressed. Popovers use the `.panel` look and a subtle entrance (opacity + 4 px translate, 120 ms),
disabled under `prefers-reduced-motion`. Reference mockup: the icons in the top-right of
`/Users/yaoderek/conductor/workspaces/rca-atlas/surabaya/.context/hybrid.png`.

## Testing

- New `ui/HudDock.test.jsx`: each button opens its popover; only one open at a time; Escape closes and
  restores focus; outside click closes; `aria-expanded` is correct; terrain state persists across
  close/reopen.
- Update `Controls.test.jsx` and `Legend.test.jsx` for the removed minimize/compact behaviour.
- Update `e2e/atlas.spec.js` for the dock and refresh the screenshots in `e2e/screens/`.
- `npm test` and `npm run build` pass in `src/atlas_map`.

## Out of scope

The chat panel, evidence visualisation, the title/regions cards, the family strip, and the side panels.
