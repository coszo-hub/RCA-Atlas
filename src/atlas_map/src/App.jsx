import { useEffect, useRef, useState } from "react";
import { BUILD_COMMAND, BundleMissingError, loadBundle } from "./data/bundle.js";
import { AtlasScene, loadGrids } from "./scene/AtlasScene.js";

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
  return <SceneHost bundle={bundle} />;
}

function SceneHost({ bundle, onReady }) {
  const canvasRef = useRef(null);
  useEffect(() => {
    let scene, cancelled = false;
    loadGrids(bundle.terrainMeta).then(grids => {
      if (cancelled) return;
      scene = new AtlasScene(canvasRef.current, bundle, grids);
      window.__atlas = { scene };   // test hook, see Task 12
      onReady?.(scene);
    });
    return () => { cancelled = true; scene?.dispose(); };
  }, [bundle]);
  return <canvas ref={canvasRef} className="atlas-scene" aria-label="3D map of the seafloor off Oregon" />;
}
