import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { BUILD_COMMAND, BundleMissingError, loadBundle } from "./data/bundle.js";
import { AtlasScene, loadGrids } from "./scene/AtlasScene.js";
import { OverlayLayer } from "./overlay/OverlayLayer.js";
import FamilyFilter from "./ui/FamilyFilter.jsx";
import Header from "./ui/Header.jsx";
import HudDock from "./ui/HudDock.jsx";
import RegionNav from "./ui/RegionNav.jsx";
import Credit from "./ui/Credit.jsx";
import SensorDetail from "./panels/SensorDetail.jsx";
import SitePanel from "./panels/SitePanel.jsx";
import UnplacedPanel from "./panels/UnplacedPanel.jsx";
import { INSET as inset, hudBottom } from "./ui/layout.js";
import Tooltip from "./ui/Tooltip.jsx";
import AskPanel, { askStartsOpen } from "./ask/AskPanel.jsx";
import { EvidenceLayer } from "./scene/EvidenceLayer.js";
import { frameView, hypoMeters } from "./scene/evidenceMath.js";
import { tourOf } from "./evidence/resolve.js";


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
  const evidenceRef = useRef(null), evLayerRef = useRef(null);
  const [scene, setScene] = useState(null);
  const [regionKey, setRegionKey] = useState("overview");
  const [focus, setFocus] = useState(new Set());
  const [hover, setHover] = useState(null);   // {kind, item, x, y}
  const [siteId, setSiteId] = useState(null);   // the site panel (Task 7) opens for it
  const [sensorId, setSensorId] = useState(null);   // the sensor detail (Task 8) opens for it
  const [unplacedOpen, setUnplacedOpen] = useState(false);   // the list of sensors with no position and no site
  const [sideMin, setSideMin] = useState(false);   // the site or unplaced panel is minimized to a tab; opening one restores it
  const [chatOpen, setChatOpen] = useState(askStartsOpen);   // AskPanel owns and persists it; the top row follows it
  // Ask Atlas, shared by the panel and the evidence layer: the answer whose evidence is on the map, the item selected
  // (click, ←/→; its station is in the side panel), and the one under the pointer (a superscript, a table row, or a spike).
  const [ask, setAsk] = useState({ evidence: null, activeN: null, hoverN: null });
  const [deep, setDeep] = useState(false);   // Axial's subsurface (earthquakes, magma chamber, faults) is shown
  const evidenceDeep = useRef(false);   // the subsurface was turned on to show an answer's earthquakes

  // One right-hand panel at a time: a site (with its sensors) or the unplaced list (with theirs).
  const showSite = useCallback(site => {
    setSiteId(site.id); setUnplacedOpen(false); setSensorId(null); setSideMin(false); setHover(null); layerRef.current?.setSelected(site.id);
  }, []);
  const openSite = useCallback((site, sc) => { showSite(site); sc.flyToPoint(site.lon, site.lat, 6); }, [showSite]);
  const closeSite = useCallback(() => { setSiteId(null); setSensorId(null); layerRef.current?.setSelected(null); }, []);
  const openUnplaced = useCallback(() => { closeSite(); setUnplacedOpen(true); setSideMin(false); }, [closeSite]);
  const closeUnplaced = useCallback(() => { setUnplacedOpen(false); setSensorId(null); }, []);
  // A sensor's detail, inside its site's panel when it has a site, else inside the unplaced list (no flight).
  const showSensor = useCallback(id => {
    const sensor = bundle.sensorById[id], site = sensor && bundle.siteById[sensor.site];
    if (!sensor) return false;
    if (site) showSite(site); else openUnplaced();
    setSensorId(id);
    return true;
  }, [bundle, showSite, openUnplaced]);
  // Opening one also flies to its site when it has a recorded position.
  const openSensor = useCallback((id, sc) => {
    if (!showSensor(id)) return false;
    const sensor = bundle.sensorById[id], site = bundle.siteById[sensor.site];
    if (site && sensor.lat != null) sc.flyToPoint(site.lon, site.lat, 6);
    return true;
  }, [bundle, showSensor]);
  const selectRegion = useCallback((key, sc) => {
    setRegionKey(key); sc.flyTo(sc.fit(key === "overview" ? bundle.overview : bundle.regions.find(r => r.key === key).view));
  }, [bundle]);

  useEffect(() => {
    let sc, layer, evLayer, cancelled = false;
    loadGrids(bundle.terrainMeta).then(async grids => {
      if (cancelled) return;
      sc = new AtlasScene(canvasRef.current, bundle, grids);
      await sc.ready;   // the cable, moorings, and markers sample the final elevAt (with the AUV survey)
      if (cancelled) return;
      sc.addCable(bundle.cable);
      sc.addDas(bundle.das);
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
      evLayer = new EvidenceLayer(evidenceRef.current, sc, bundle, {
        onHover: n => setAsk(a => ({ ...a, hoverN: n })),
        onSelect: n => askActions.current.select(n),
      });
      evLayerRef.current = evLayer;
      sc.onFrame = () => { layer.update(); evLayer.update(); };
      // Test hook for the browser tests: fly to a view, or open a site or a sensor by id.
      window.__atlas = {
        scene: sc, layer, flyTo: view => sc.flyTo(view), lod: () => sc.auv?.stats(),
        evidence: () => ({ ...evLayer.snapshot(), located: askActions.current.evidence?.located ?? [] }),
        open: id => {
          if (bundle.sensorById[id]) return openSensor(id, sc);
          if (!bundle.siteById[id]) return false;
          openSite(bundle.siteById[id], sc);
          return true;
        },
      };
      setScene(sc);
    }).catch(err => { if (!cancelled) onError?.(err); });
    return () => { cancelled = true; evLayer?.dispose(); layer?.dispose(); sc?.dispose(); };
  }, [bundle, openSite, openSensor, selectRegion, onError]);

  // Located evidence (or an answer's earthquakes) mutes the terrain, as a family focus does.
  const evidenceShown = !!(ask.evidence?.located.length || ask.evidence?.events);
  useEffect(() => {
    if (!scene) return;
    layerRef.current?.setFocus(focus);
    scene.setMute(focus.size || evidenceShown ? 0.55 : 0);
  }, [focus, scene, evidenceShown]);

  // A new answer on the map: the old spikes sink and the new rise; uncited site rings fade; the camera frames the
  // evidence in the free area. Earthquakes turn the terrain to glass over the caldera (the subsurface view).
  useEffect(() => {
    if (!scene) return;
    const ev = ask.evidence;
    evLayerRef.current?.show(ev);
    layerRef.current?.setEvidence(ev?.located.length ? new Set(ev.located.map(x => x.siteId).filter(Boolean)) : null);
    if (ev?.events && scene.subsurface) {
      if (!deep) { evidenceDeep.current = true; setDeep(true); }
      scene.setSubsurface(true);
    } else if (evidenceDeep.current) {
      evidenceDeep.current = false; setDeep(false); scene.setSubsurface(false);
    }
    if (ev?.located.length) {
      const off = scene.camera.position.clone().sub(scene.controls.target), flat = scene.U.flat.value > 0.5;
      const polar = flat ? 0.001 : Math.min(0.95, Math.max(0.6, Math.acos(off.y / off.length())));
      scene.flyTo(scene.fit(frameView(ev.located.map(x => [x.lon, x.lat]), { az: Math.atan2(off.x, off.z), exag: scene.U.exag.value, polar })));
    }
  }, [ask.evidence, scene]);   // deep is read here, not followed
  useEffect(() => { evLayerRef.current?.setActive(ask.activeN); }, [ask.activeN, scene]);
  useEffect(() => { evLayerRef.current?.setHover(ask.hoverN); }, [ask.hoverN, scene]);

  // Selecting an item (null clears it) flies to it and opens its station in the side panel: a sensor's detail
  // (live data), or a site. That flight is the only one. A cable or a quake has no station, so an open panel closes
  // rather than show the previous one.
  const askActions = useRef({});
  askActions.current = {
    evidence: ask.evidence,
    select: n => {
      setAsk(a => ({ ...a, activeN: n }));
      const it = n == null ? null : tourOf(ask.evidence).find(x => x.n === n);
      if (!it || !scene) return;
      // A quake is framed at its hypocentre, from a wide view (a close one would sit inside the magma chamber's surface).
      const depth = it.time ? hypoMeters(it.depth_km, scene.subsurface?.data?.datumM) : undefined;
      const dist = it.kind === "cable" ? 70 : it.time ? Math.min(25, Math.max(12, scene.frame.dist ?? 12)) : 7;
      scene.flyToPoint(it.lon, it.lat, dist, depth);
      if (it.kind === "sensor" && showSensor(it.id)) return;
      if (it.kind === "site" && bundle.siteById[it.id]) return showSite(bundle.siteById[it.id]);
      closeSite(); setUnplacedOpen(false);
    },
  };

  // A minimized side panel is a tab at the bottom right, so the map and top row take its width back.
  const panelOpen = (!!siteId || unplacedOpen) && !sideMin;
  useLayoutEffect(() => {
    const root = document.documentElement.style;
    root.setProperty("--right-inset", `${panelOpen ? inset.side : inset.none}px`);
    root.setProperty("--side-reserve", sideMin ? "284px" : "0px");   // the family strip keeps clear of the minimized side tab (≤260 px wide)
  }, [panelOpen, sideMin]);

  // The map centers on the area the panels leave free: between the chat and side panels, below the top-row
  // HUD (header and regions, or the dock if it is lower), and above the family strip.
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
      <div id="atlas-evidence" ref={evidenceRef} />
      {scene && (
        <>
          {/* The top row spans the map between the side panels: header and regions on the left, and on the
              right the dock whose buttons open the terrain controls, the legend and help. */}
          <div className="hud-top">
            <div className="left-stack" ref={hudRef}>
              <Header bundle={bundle} onPick={r => (r.kind === "site" ? openSite(bundle.siteById[r.id], scene) : openSensor(r.id, scene))} />
              <RegionNav regions={bundle.regions} sensors={bundle.sensors} active={regionKey} onSelect={key => selectRegion(key, scene)}
                unplaced={bundle.unplaced?.length ?? 0} unplacedOpen={unplacedOpen} onUnplaced={() => (unplacedOpen ? closeUnplaced() : openUnplaced())} />
            </div>
            <div className="right-stack" ref={rightRef}>
              <HudDock scene={scene} deep={deep} onDeep={setDeep} credit={bundle.terrainMeta.credit} auv={!!scene.auv}
                subsurface={deep ? scene.subsurface?.credit : null} />
            </div>
          </div>
          <Credit credit={bundle.terrainMeta.credit} auv={!!scene.auv} subsurface={deep} />
          <FamilyFilter families={bundle.families} sensors={bundle.sensors} focus={focus} onChange={setFocus} />
          <Tooltip hover={hover} bundle={bundle} />
          <AskPanel bundle={bundle} evidence={ask.evidence} activeN={ask.activeN} hoverN={ask.hoverN} panelOpen={panelOpen}
            onShow={ev => setAsk({ evidence: ev, activeN: null, hoverN: null })} onHover={n => setAsk(a => ({ ...a, hoverN: n }))}
            onSelect={n => askActions.current.select(n)} onOpenChange={setChatOpen} />
          {site && (
            <SitePanel key={siteId} site={site} bundle={bundle} elevAt={scene.elevAt}
              onClose={closeSite} onBack={() => setSensorId(null)} onSensor={setSensorId} minimized={sideMin} onMinimize={setSideMin}>
              {detail(site.label)}
            </SitePanel>
          )}
          {!site && unplacedOpen && (
            <UnplacedPanel bundle={bundle} onClose={closeUnplaced} onBack={() => setSensorId(null)} onSensor={setSensorId}
              minimized={sideMin} onMinimize={setSideMin}>
              {detail("Unplaced sensors")}
            </UnplacedPanel>
          )}
        </>
      )}
    </>
  );
}
