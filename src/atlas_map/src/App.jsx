import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { BUILD_COMMAND, BundleMissingError, loadBundle } from "./data/bundle.js";
import { AtlasScene, loadGrids } from "./scene/AtlasScene.js";
import { OverlayLayer } from "./overlay/OverlayLayer.js";
import Controls from "./ui/Controls.jsx";
import FamilyFilter from "./ui/FamilyFilter.jsx";
import Header from "./ui/Header.jsx";
import Legend from "./ui/Legend.jsx";
import RegionNav from "./ui/RegionNav.jsx";
import SensorDetail from "./panels/SensorDetail.jsx";
import SitePanel from "./panels/SitePanel.jsx";
import Tooltip from "./ui/Tooltip.jsx";
import ChatPanel, { chatStartsOpen } from "./chat/ChatPanel.jsx";

// Widths the side panels take from the map, including their 16 px margins (see --left-inset / --right-inset).
const inset = { chat: 412, site: 472, none: 16 };

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
  const canvasRef = useRef(null), overlayRef = useRef(null), layerRef = useRef(null), hudRef = useRef(null);
  const [scene, setScene] = useState(null);
  const [regionKey, setRegionKey] = useState("overview");
  const [focus, setFocus] = useState(new Set());
  const [hover, setHover] = useState(null);   // {kind, item, x, y}
  const [siteId, setSiteId] = useState(null);   // the site panel (Task 7) opens for it
  const [sensorId, setSensorId] = useState(null);   // the sensor detail (Task 8) opens for it
  const [chatOpen, setChatOpen] = useState(chatStartsOpen);   // ChatPanel owns and persists it; the legend follows it

  const openSite = useCallback((site, sc) => {
    setSiteId(site.id); setSensorId(null); setHover(null); sc.flyToPoint(site.lon, site.lat, 6); layerRef.current?.setSelected(site.id);
  }, []);
  const closeSite = useCallback(() => { setSiteId(null); setSensorId(null); layerRef.current?.setSelected(null); }, []);
  const selectRegion = useCallback((key, sc) => {
    setRegionKey(key); sc.flyTo(sc.fit(key === "overview" ? bundle.overview : bundle.regions.find(r => r.key === key).view));
  }, [bundle]);

  useEffect(() => {
    let sc, layer, cancelled = false;
    loadGrids(bundle.terrainMeta).then(grids => {
      if (cancelled) return;
      sc = new AtlasScene(canvasRef.current, bundle, grids);
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
        scene: sc, layer, flyTo: view => sc.flyTo(view),
        open: id => {
          const sensor = bundle.sensorById[id], target = bundle.siteById[sensor ? sensor.site : id];
          if (!target) return false;
          openSite(target, sc);
          if (sensor) setSensorId(id);
          return true;
        },
      };
      setScene(sc);
    }).catch(err => { if (!cancelled) onError?.(err); });
    return () => { cancelled = true; layer?.dispose(); sc?.dispose(); };
  }, [bundle, openSite, selectRegion, onError]);

  useEffect(() => {
    if (!scene) return;
    layerRef.current?.setFocus(focus);
    scene.setMute(focus.size ? 0.55 : 0);
  }, [focus, scene]);

  useEffect(() => {
    document.documentElement.style.setProperty("--right-inset", `${siteId ? inset.site : inset.none}px`);
  }, [siteId]);

  // The map centers on the area the panels leave free: between the chat and site panels, below the header
  // and regions (they sit over the array's west end), and above the family strip. Layout effects, so the
  // first framing (the overview, fitted to that area) is in place before the first paint with the HUD.
  useLayoutEffect(() => {
    const head = hudRef.current;
    if (!scene || !head) return;
    const strip = document.querySelector(".families");
    const settle = () => scene.setInsetsY(head.getBoundingClientRect().bottom, strip ? innerHeight - strip.getBoundingClientRect().top : inset.none);
    settle();
    const ro = new ResizeObserver(settle);
    ro.observe(head); if (strip) ro.observe(strip);
    addEventListener("resize", settle);
    return () => { ro.disconnect(); removeEventListener("resize", settle); };
  }, [scene]);
  useLayoutEffect(() => {
    if (!scene) return;
    const first = !scene.framed;
    scene.setInsets(chatOpen ? inset.chat : inset.none, siteId ? inset.site : inset.none, first);
    if (first) scene.jumpTo(scene.fit(bundle.overview));
  }, [scene, chatOpen, siteId, bundle]);

  const site = siteId ? bundle.siteById[siteId] : null;
  const sensor = sensorId ? bundle.sensorById[sensorId] : null;
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
              <Header bundle={bundle} onPick={r => {
                const target = r.kind === "site" ? bundle.siteById[r.id] : bundle.siteById[bundle.sensorById[r.id].site];
                openSite(target, scene);
                if (r.kind === "sensor") setSensorId(r.id);
              }} />
              <RegionNav regions={bundle.regions} sensors={bundle.sensors} active={regionKey} onSelect={key => selectRegion(key, scene)} />
            </div>
            <div className="right-stack">
              <Controls scene={scene} />
              <Legend credit={bundle.terrainMeta.credit} compact={!!siteId || chatOpen} />
            </div>
          </div>
          <FamilyFilter families={bundle.families} sensors={bundle.sensors} focus={focus} onChange={setFocus} />
          <Tooltip hover={hover} bundle={bundle} />
          <ChatPanel selection={{ site, sensor }} onOpenChange={setChatOpen} />
          {site && (
            <SitePanel key={siteId} site={site} bundle={bundle} elevAt={scene.elevAt}
              onClose={closeSite} onBack={() => setSensorId(null)} onSensor={setSensorId}>
              {sensor && <SensorDetail key={sensorId} sensor={sensor} bundle={bundle} onBack={() => setSensorId(null)} />}
            </SitePanel>
          )}
        </>
      )}
    </>
  );
}
