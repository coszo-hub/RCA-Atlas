import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { BUILD_COMMAND, BundleMissingError, loadBundle } from "./data/bundle.js";
import { AtlasScene, loadGrids } from "./scene/AtlasScene.js";
import { OverlayLayer } from "./overlay/OverlayLayer.js";
import Controls from "./ui/Controls.jsx";
import FamilyFilter from "./ui/FamilyFilter.jsx";
import Header from "./ui/Header.jsx";
import Legend from "./ui/Legend.jsx";
import RegionNav from "./ui/RegionNav.jsx";
import Credit from "./ui/Credit.jsx";
import SensorDetail from "./panels/SensorDetail.jsx";
import SitePanel from "./panels/SitePanel.jsx";
import UnplacedPanel from "./panels/UnplacedPanel.jsx";
import { INSET as inset, hudBottom, hudWraps } from "./ui/layout.js";
import Tooltip from "./ui/Tooltip.jsx";
import ChatPanel, { chatStartsOpen } from "./chat/ChatPanel.jsx";


export default function App() {
  const [bundle, setBundle] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { loadBundle().then(setBundle, setError); }, []);

  if (error) {
    return (
      <div className="app-message" role="alert">
        <div>{error instanceof BundleMissingError ? "The atlas data bundle has not been built yet." : error.message}
          {error instanceof BundleMissingError && <code>{BUILD_COMMAND}</code>}
        </div>
      </div>
    );
  }
  if (!bundle) return <div className="app-message">Loading the atlas…</div>;
  return <Atlas bundle={bundle} onError={setError} />;
}

function Atlas({ bundle, onError }) {
  const canvasRef = useRef(null), overlayRef = useRef(null), layerRef = useRef(null), hudRef = useRef(null), rightRef = useRef(null);
  const [scene, setScene] = useState(null);
  const [regionKey, setRegionKey] = useState("overview");
  const [focus, setFocus] = useState(new Set());
  const [hover, setHover] = useState(null);   // {kind, item, x, y}
  const [siteId, setSiteId] = useState(null);   // the site panel (Task 7) opens for it
  const [sensorId, setSensorId] = useState(null);   // the sensor detail (Task 8) opens for it
  const [unplacedOpen, setUnplacedOpen] = useState(false);   // the list of sensors with no position and no site
  const [chatOpen, setChatOpen] = useState(chatStartsOpen);   // ChatPanel owns and persists it; the top row follows it
  const [width, setWidth] = useState(innerWidth);
  const [deep, setDeep] = useState(false);   // Axial's subsurface (earthquakes, magma chamber, faults) is shown
  useEffect(() => { const on = () => setWidth(innerWidth); addEventListener("resize", on); return () => removeEventListener("resize", on); }, []);

  // One right-hand panel at a time: a site (with its sensors) or the unplaced list (with theirs).
  const showSite = useCallback(site => {
    setSiteId(site.id); setUnplacedOpen(false); setSensorId(null); setHover(null); layerRef.current?.setSelected(site.id);
  }, []);
  const openSite = useCallback((site, sc) => { showSite(site); sc.flyToPoint(site.lon, site.lat, 6); }, [showSite]);
  const closeSite = useCallback(() => { setSiteId(null); setSensorId(null); layerRef.current?.setSelected(null); }, []);
  const openUnplaced = useCallback(() => { closeSite(); setUnplacedOpen(true); }, [closeSite]);
  const closeUnplaced = useCallback(() => { setUnplacedOpen(false); setSensorId(null); }, []);
  // A located sensor flies to its site. One with no recorded position opens its detail without a flight:
  // inside its named site's panel when it has one, else inside the unplaced list.
  const openSensor = useCallback((id, sc) => {
    const sensor = bundle.sensorById[id], site = sensor && bundle.siteById[sensor.site];
    if (!sensor) return false;
    if (site && sensor.lat != null) openSite(site, sc);
    else if (site) showSite(site);
    else openUnplaced();
    setSensorId(id);
    return true;
  }, [bundle, openSite, showSite, openUnplaced]);
  const selectRegion = useCallback((key, sc) => {
    setRegionKey(key); sc.flyTo(sc.fit(key === "overview" ? bundle.overview : bundle.regions.find(r => r.key === key).view));
  }, [bundle]);

  useEffect(() => {
    let sc, layer, cancelled = false;
    loadGrids(bundle.terrainMeta).then(async grids => {
      if (cancelled) return;
      sc = new AtlasScene(canvasRef.current, bundle, grids);
      await sc.ready;   // the cable, moorings, and markers sample the final elevAt (with the AUV survey)
      if (cancelled) return;
      sc.addCable(bundle.cable);
      sc.addMoorings(bundle.sites);
      const at = ev => ({ x: ev.clientX, y: ev.clientY });
      layer = new OverlayLayer(overlayRef.current, bundle, sc, {
        onRegionClick: key => selectRegion(key, sc),
        onSiteClick: site => openSite(site, sc),
        onSiteHover: (site, ev) => setHover(ev ? { kind: "site", item: site, ...at(ev) } : null),
        onNodeHover: (node, ev) => setHover(ev ? { kind: "node", item: node, ...at(ev) } : null),
        onNodeClick: node => sc.flyToPoint(node.lon, node.lat, 30),
        onCableHover: (line, ev) => setHover(h => (ev ? { kind: "cable", item: line, ...at(ev) } : h?.kind === "cable" ? null : h)),
      });
      layerRef.current = layer;
      sc.onFrame = () => layer.update();
      // Test hook for the browser tests: fly to a view, or open a site or a sensor by id.
      window.__atlas = {
        scene: sc, layer, flyTo: view => sc.flyTo(view), lod: () => sc.auv?.stats(),
        open: id => {
          if (bundle.sensorById[id]) return openSensor(id, sc);
          if (!bundle.siteById[id]) return false;
          openSite(bundle.siteById[id], sc);
          return true;
        },
      };
      setScene(sc);
    }).catch(err => { if (!cancelled) onError?.(err); });
    return () => { cancelled = true; layer?.dispose(); sc?.dispose(); };
  }, [bundle, openSite, openSensor, selectRegion, onError]);

  useEffect(() => {
    if (!scene) return;
    layerRef.current?.setFocus(focus);
    scene.setMute(focus.size ? 0.55 : 0);
  }, [focus, scene]);

  const panelOpen = !!siteId || unplacedOpen;
  // The top row wraps when the map between the panels is too narrow for header and controls side by side;
  // then the controls and legend collapse to toggles so they do not sit over the middle of the map.
  const wraps = hudWraps(width, chatOpen, panelOpen);
  useLayoutEffect(() => {
    document.documentElement.style.setProperty("--right-inset", `${panelOpen ? inset.side : inset.none}px`);
  }, [panelOpen]);

  // The map centers on the area the panels leave free: between the chat and side panels, below the top-row
  // HUD (header and regions, plus the controls when they wrap under them), and above the family strip.
  // Layout effects, so the first framing (the overview, fitted to that area) is in place before the first paint.
  useLayoutEffect(() => {
    const head = hudRef.current, right = rightRef.current;
    if (!scene || !head) return;
    const strip = document.querySelector(".families"), row = head.parentElement;
    const settle = () => scene.setInsetsY(hudBottom(head, right), strip ? innerHeight - strip.getBoundingClientRect().top : inset.none);
    settle();
    const ro = new ResizeObserver(settle);
    for (const el of [head, right, row, strip]) if (el) ro.observe(el);
    addEventListener("resize", settle);
    return () => { ro.disconnect(); removeEventListener("resize", settle); };
  }, [scene]);
  useLayoutEffect(() => {
    if (!scene) return;
    const first = !scene.framed;
    scene.setInsets(chatOpen ? inset.chat : inset.none, panelOpen ? inset.side : inset.none, first);
    if (first) scene.jumpTo(scene.fit(bundle.overview));
  }, [scene, chatOpen, panelOpen, bundle]);

  const site = siteId ? bundle.siteById[siteId] : null;
  const sensor = sensorId ? bundle.sensorById[sensorId] : null;
  const detail = backLabel => sensor && <SensorDetail key={sensorId} sensor={sensor} bundle={bundle} backLabel={backLabel} onBack={() => setSensorId(null)} />;
  return (
    <>
      <canvas ref={canvasRef} className="atlas-scene" aria-label="3D map of the seafloor off Oregon" />
      <div id="atlas-overlay" ref={overlayRef} />
      {scene && (
        <>
          {/* The top row spans the map between the side panels and wraps when it is narrow:
              header and regions on the left, view controls and legend on the right. */}
          <div className="hud-top">
            <div className="left-stack" ref={hudRef}>
              <Header bundle={bundle} onPick={r => (r.kind === "site" ? openSite(bundle.siteById[r.id], scene) : openSensor(r.id, scene))} />
              <RegionNav regions={bundle.regions} sensors={bundle.sensors} active={regionKey} onSelect={key => selectRegion(key, scene)}
                unplaced={bundle.unplaced?.length ?? 0} unplacedOpen={unplacedOpen} onUnplaced={() => (unplacedOpen ? closeUnplaced() : openUnplaced())} />
            </div>
            <div className={`right-stack${wraps ? " compact" : ""}`} ref={rightRef}>
              <Controls scene={scene} compact={wraps} deep={deep} onDeep={setDeep} />
              <Legend credit={bundle.terrainMeta.credit} compact={panelOpen || wraps} auv={!!scene.auv}
                subsurface={deep ? scene.subsurface?.credit : null} />
            </div>
          </div>
          <Credit credit={bundle.terrainMeta.credit} auv={!!scene.auv} subsurface={deep} />
          <FamilyFilter families={bundle.families} sensors={bundle.sensors} focus={focus} onChange={setFocus} />
          <Tooltip hover={hover} bundle={bundle} />
          <ChatPanel selection={{ site, sensor }} onOpenChange={setChatOpen} />
          {site && (
            <SitePanel key={siteId} site={site} bundle={bundle} elevAt={scene.elevAt}
              onClose={closeSite} onBack={() => setSensorId(null)} onSensor={setSensorId}>
              {detail(site.label)}
            </SitePanel>
          )}
          {!site && unplacedOpen && (
            <UnplacedPanel bundle={bundle} onClose={closeUnplaced} onBack={() => setSensorId(null)} onSensor={setSensorId}>
              {detail("Unplaced sensors")}
            </UnplacedPanel>
          )}
        </>
      )}
    </>
  );
}
