import { useCallback, useEffect, useRef, useState } from "react";
import { BUILD_COMMAND, BundleMissingError, loadBundle } from "./data/bundle.js";
import { AtlasScene, loadGrids } from "./scene/AtlasScene.js";
import { OverlayLayer } from "./overlay/OverlayLayer.js";
import Controls from "./ui/Controls.jsx";
import FamilyFilter from "./ui/FamilyFilter.jsx";
import Header from "./ui/Header.jsx";
import Legend from "./ui/Legend.jsx";
import RegionNav from "./ui/RegionNav.jsx";
import SitePanel from "./panels/SitePanel.jsx";
import Tooltip from "./ui/Tooltip.jsx";

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
  const canvasRef = useRef(null), overlayRef = useRef(null), layerRef = useRef(null);
  const [scene, setScene] = useState(null);
  const [regionKey, setRegionKey] = useState("overview");
  const [focus, setFocus] = useState(new Set());
  const [hover, setHover] = useState(null);   // {kind, item, x, y}
  const [siteId, setSiteId] = useState(null);   // the site panel (Task 7) opens for it
  const [sensorId, setSensorId] = useState(null);   // the sensor detail (Task 8) opens for it

  const openSite = useCallback((site, sc) => {
    setSiteId(site.id); setSensorId(null); setHover(null); sc.flyToPoint(site.lon, site.lat, 6); layerRef.current?.setSelected(site.id);
  }, []);
  const closeSite = useCallback(() => { setSiteId(null); setSensorId(null); layerRef.current?.setSelected(null); }, []);
  const selectRegion = useCallback((key, sc) => {
    setRegionKey(key); sc.flyTo(key === "overview" ? bundle.overview : bundle.regions.find(r => r.key === key).view);
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
      window.__atlas = { scene: sc, layer };   // test hook, see Task 11
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
    document.documentElement.style.setProperty("--right-inset", siteId ? "472px" : "16px");
  }, [siteId]);

  return (
    <>
      <canvas ref={canvasRef} className="atlas-scene" aria-label="3D map of the seafloor off Oregon" />
      <div id="atlas-overlay" ref={overlayRef} />
      {scene && (
        <>
          <Header bundle={bundle} onPick={r => {
            const target = r.kind === "site" ? bundle.siteById[r.id] : bundle.siteById[bundle.sensorById[r.id].site];
            openSite(target, scene);
            if (r.kind === "sensor") setSensorId(r.id);
          }} />
          <Controls scene={scene} />
          <RegionNav regions={bundle.regions} sensors={bundle.sensors} active={regionKey} onSelect={key => selectRegion(key, scene)} />
          <FamilyFilter families={bundle.families} sensors={bundle.sensors} focus={focus} onChange={setFocus} />
          <Legend credit={bundle.terrainMeta.credit} />
          <Tooltip hover={hover} bundle={bundle} />
          {siteId && (
            <SitePanel key={siteId} site={bundle.siteById[siteId]} bundle={bundle} elevAt={scene.elevAt}
              onClose={closeSite} onSensor={setSensorId} />
          )}
        </>
      )}
    </>
  );
}
