// A failed live request: say which source failed and offer a retry.
export default function Failure({ error, retry }) {
  return (
    <p className="degraded">
      {error.kind === "unreachable" ? "Live data unavailable: the live data service is not running." : `${error.source}: ${error.message}`}
      <button onClick={retry}>Retry</button>
    </p>
  );
}
