import { useEffect, useState } from "react";
import { BUILD_COMMAND, BundleMissingError, loadBundle } from "./data/bundle.js";

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
  return <div className="app-message">{bundle.sensors.length} sensors loaded.</div>;
}
