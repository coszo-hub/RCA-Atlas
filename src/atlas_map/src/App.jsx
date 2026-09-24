import { useEffect, useState } from "react";
import { BundleMissingError, loadBundle } from "./data/bundle.js";

export default function App() {
  const [bundle, setBundle] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { loadBundle().then(setBundle, setError); }, []);

  if (error) {
    return (
      <div className="app-message" role="alert">
        <div>{error instanceof BundleMissingError ? "The atlas data bundle has not been built yet." : error.message}
          {error instanceof BundleMissingError && <code>PYTHONPATH=src .venv/bin/python -m atlas_map_data.build_atlas_bundle</code>}
        </div>
      </div>
    );
  }
  if (!bundle) return <div className="app-message">Loading the atlas…</div>;
  return <div className="app-message">{bundle.sensors.length} sensors loaded.</div>;
}
