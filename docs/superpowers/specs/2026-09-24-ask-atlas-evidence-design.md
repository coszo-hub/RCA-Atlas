# Ask Atlas on the map: evidence you can see

Status: approved 2026-09-24 (Derek). Second of two PRs; stacks on the HUD dock PR
(`docs/superpowers/specs/2026-09-24-hud-dock-design.md`, branch `atlas-hud-dock`), which turns the
terrain controls, legend and help into icons in the top-right. Do not change those here.

## Goal

The 3D map (`src/atlas_map`) is the main interface; Ask Atlas becomes its left sidebar. When an answer
cites sensor evidence, the map shows exactly what and where it came from: the terrain dims, a glowing
spike rises from each cited location, and each spike is numbered to match the answer's citations. This
replaces the abstract 2D "Evidence map" of `src/atlas_ui`. It is for a live demo: maximum clarity and wow.

Search/retrieval is not rebuilt. The answer backend stays the RCA Atlas Cloudflare Worker
(`src/atlas_worker`, deployed at `https://rca-atlas.quakehunt.workers.dev`, `POST /v1/answer`), which
fetches Graph-RAG `/v1/context` and asks an LLM.

## Demo questions (all four must work well)

1. Instrument: "What's been measuring Axial's inflation before the next eruption?" / "What instruments are
   on Southern Hydrate Ridge?"
2. Events: "How many earthquakes at Axial yesterday?" (Worker's live hypo71 catalog route)
3. Data access: "How do I get the DAS data?" / "Where can I download the BPR record?"
4. Broad science: "What's known about the 2015 Axial eruption?" (mostly documents; highlight whatever
   sensors/sites the evidence links to)

## Look (approved)

Reference mockup: `/Users/yaoderek/conductor/workspaces/rca-atlas/surabaya/.context/hybrid.png`, HTML
source `/Users/yaoderek/conductor/workspaces/rca-atlas/surabaya/.superpowers/brainstorm/92470-1790285335/content/hybrid.html`.
"Field journal" answer + "instrument console" evidence table:

- Sidebar in the existing chat slot (left, `INSET.chat` = 412 px incl. margins), solid `#151514`,
  hairline border, 8 px radius. Header: small-caps "ASK ATLAS" left, "RCA · COSZO" right.
- The question renders as a serif italic headline (Newsreader, ~17 px) with a hairline beneath, and a
  monospace stats line under it: `4 on the map · 1 paper · 1.9 s · gemini-2.5-flash`.
- The answer is serif (Newsreader, ~13.5 px, line-height 1.55). Citations are superscript monospace numbers
  in the evidence's family colour; the active one is inverted (dark text on `#ffcc66`).
- "EVIDENCE ON THE MAP" label with `← n / N →` stepper, then a table: `# | INSTRUMENT | SITE | DEPTH`,
  monospace cells, hairline rows, number in family colour. The active row is highlighted and expands a
  second line with the excerpt in serif italic.
- "FURTHER READING": non-located sources as serif links with ↗.
- Composer at the bottom: hairline top rule, "Ask a follow-up…", a small model picker ("Auto ▾") and ↵.
  Models: the list the Worker accepts (`auto`, `gemini-2.5-flash`, `gemini-3.5-flash-lite`,
  `groq-gpt-oss-120b`, `groq-gpt-oss-20b`, `groq-qwen3-8-27b`, `gpt-5.4-mini`).
- Empty state: the four demo questions as one-click suggestions.
- Load Newsreader (Google Fonts or self-hosted woff2 under `public/`), Georgia fallback.
- The sidebar minimizes to a tab like today's chat panel (keep `localStorage["atlas.chat.open"]` and the
  `--left-inset` / camera inset plumbing).

## Behaviour

Reveal sequence:
1. Ask: the question appears as the headline; a quiet "Reading the corpus…" line shows while waiting.
   The map does not change yet.
2. Answer arrives: resolve evidence (below). If anything is located: the terrain mutes (`U.mute`, as the
   family focus does), site rings that are not cited fade (existing focus/opacity mechanism), spikes rise
   staggered ~120 ms apart (~600 ms each, eased), and the camera flies to frame all located evidence in
   the free area between the panels (reuse `fit` / `fitDist` / insets).
3. Hovering a superscript, a table row, or a spike sets the active item: its spike grows (~1.8× height),
   brightens, and gets a pulsing halo ring at its base; the others dim slightly.
4. Clicking any of those flies to the item (`flyToPoint`) and opens an in-scene card anchored above the
   spike: serif title ("2 · Bottom pressure tilt, International District"), monospace refdes · depth, serif
   italic excerpt, and buttons "Live data →" (opens the existing sensor panel via `openSensor`) and
   "Site" (opens the site panel). ← / → (and the stepper) step through evidence in order with the same
   fly-to. That is the "tour".
5. Located evidence outside the viewport gets an edge chip (number + short label + arrow) clamped to the
   free-area edge in its direction; clicking it flies there.
6. Escape: first clears the active item/card; second clears all evidence and restores terrain/rings.
7. A new question: old spikes sink (~300 ms) before the new rise. Earlier Q&A stay in the thread;
   clicking an earlier answer re-shows its evidence.

Evidence kinds (from the resolver):
- `sensor`: spike in the family colour rising from the seafloor at the sensor's lon/lat.
- `site`: white spike at the site.
- `cable` (DAS / fibre routes): no spike; the matching cable or DAS-coverage line glows with a pulse
  travelling along it, number tag at its midpoint. `main` now ships `das.json` and DAS coverage lines in
  `AtlasScene`; reuse them.
- `events` (Axial quake count): turn on the see-through terrain (existing subsurface `see`/glass) and
  render the returned hypocentres beneath the caldera as glowing points sized by magnitude, appearing in
  time order over ~3 s. The table lists events (time, magnitude, depth) instead of instruments.
- `document`: listed under Further reading; no spike.

Spikes must stay legible from region zoom to close zoom (scale height with camera distance, clamp), render
above terrain with additive glow, and not break the existing occlusion/overlay code. Under
`prefers-reduced-motion`: no rise/sink animation or halo pulse, and flights jump (existing `motionDuration`).

## Architecture

Frontend (`src/atlas_map/src`):
- `ask/`: replaces `chat/ChatPanel` (delete it and its test). `AskPanel.jsx` (thread, headline, answer
  with superscripts, evidence table, further reading, composer, empty state), `askApi.js` (client), CSS.
- `evidence/resolve.js`: pure `resolveEvidence(response, bundle) → { located: [{ n, kind, id, lon, lat,
  depth, family, label, site, refdes, excerpt, sourceUrl }], documents: [{ n, title, url }], events }`.
  Resolution order per cited source: `INSTRUMENT-<hash>` ⇒ `sensor.instrumentId`; a refdes or canonical id
  found in the hit title/metadata/excerpt ⇒ sensor; EarthScope `station_OO_AXCC1`-style ids ⇒
  `EARTHSCOPE-OO-AXCC1`; entity/location names matching `site.name`/`site.label`/`sensor.location` ⇒ site;
  DAS / PI-portal DAS routes ⇒ `cable`; otherwise `document`. Deduplicate: one number per citation, one
  spike per location (merge numbers sharing a location).
- `scene/EvidenceLayer.js`: three.js spikes, halos, cable pulse, event points; DOM edge chips and in-scene
  card via `scene.project`. API roughly `show(items)`, `setActive(n)`, `clear()`, `update()` per frame.
- `App.jsx`: owns `ask` state `{ evidence, activeN }` shared by the panel and the layer; wire hover/click/
  keys; keep `window.__atlas` test hook and add `__atlas.evidence` for e2e.

Citation numbers: `n` is the 1-based index into the response's `answer_citations` (the Worker already
numbers sources in that order when it builds the prompt; see `generateAnswer`/`evidencePackage`). Map a
citation to its hit(s) via `hits[].citations[].source_id` (or `chunk_id`). If the answer text has no `[n]`
markers (route answers, quick answers, a model that ignores the instruction), everything still works; the
text just has no superscripts. Render `[n]`/`[n, m]` markers in the text as superscripts; unknown numbers
render as plain text.

Worker (`src/atlas_worker/src/index.js`): additive, backward compatible (the published `src/atlas_ui` must
keep working):
1. In `generateAnswer`, replace the "Do not include citations, bracketed numbers…" instruction with one
   asking the model to cite with the bracketed source numbers `[n]` from the evidence headers, placed after
   the claim, and nothing else (no ids/URLs). `src/atlas_ui` must strip `[n]` markers before display so
   the old page is unaffected (small change in `src/atlas_ui/src/main.jsx`).
2. `publicHit` adds `excerpt`: the first ~280 chars of `hit.text`, whitespace-normalized.
3. `liveAxialCount` adds `events: [{ time, lat, lon, depth_km, mag }]` parsed from the hypo71 lines it
   already reads (check the column layout against a real file; keep count semantics unchanged).
4. Tests: add `node --test` unit tests (no new deps) for event parsing, the `[n]` instruction, and
   `publicHit.excerpt`; export pure helpers for testing without changing the default export's behaviour.
Do not deploy the Worker; Derek/Maleen deploy. Until then the frontend must work against the currently
deployed Worker (no `[n]`, no `excerpt`, no `events`: fall back to hit titles and to the count only).

Dev wiring: Vite proxies `/api/ask` to `${VITE_ATLAS_ASK || "https://rca-atlas.quakehunt.workers.dev"}/v1/answer`
with `changeOrigin` and an `Origin: https://coszo.org` request header (the Worker only accepts that
origin). `VITE_ATLAS_ASK=http://127.0.0.1:8788` targets `wrangler dev` for unreleased Worker changes.
Production builds call the Worker directly (`ATLAS_WORKER` in `api/gateway.js`). The live-data gateway
path (`/api/...` in dev, Worker `/v1/live` in prod) is unchanged.

## Errors

- Worker unreachable / non-2xx: a plain one-line error in the thread with Retry; the map is untouched.
- Nothing located: no dimming; a small "No mapped instruments in this answer" note; Further reading only.
- A citation that resolves nowhere is a document. A hit matching several sensors at one site ⇒ site spike.

## Testing

- `evidence/resolve.test.js` against fixtures in `src/atlas_map/src/test/fixtures/ask/`: capture real
  responses for the four demo questions from the deployed Worker (`curl -H 'Origin: https://coszo.org'`),
  plus hand-made variants with `[n]` markers, `excerpt` and `events` for the new Worker shape.
- `ask/AskPanel.test.jsx`: asking, rendering superscripts, hover/click/←/→/Escape set/clear the active
  item, error + retry, empty-state suggestions, minimize.
- EvidenceLayer: unit-test the pure math (spike height vs distance, edge-chip clamping, stagger timing).
- Worker: `node --test` as above.
- e2e (`e2e/atlas.spec.js` + `e2e/mocks.js`): the four demo questions with fixture responses; assert spikes
  and edge chips exist via `__atlas.evidence`, click-to-fly, and save screenshots to `e2e/screens/`.
- `npm test`, `npm run build`, and `npm run e2e` pass in `src/atlas_map`.

## Out of scope

HUD dock (PR 1), search/retrieval changes, deploying the Worker, `src/atlas_ui` beyond stripping `[n]`.
