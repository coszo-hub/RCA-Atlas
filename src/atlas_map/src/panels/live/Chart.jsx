import { useEffect, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";

const AXIS = { stroke: "#a8a69d", grid: { stroke: "rgba(255,255,255,0.06)" }, ticks: { stroke: "rgba(255,255,255,0.12)" } };

// points: [[ms, value]]. Drag across to zoom, double-click to reset (uPlot's own gesture); the legend follows the crosshair.
export default function Chart({ points, unit, label }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    const data = [points.map(p => p[0] / 1000), points.map(p => p[1])];
    const plot = new uPlot({
      width: el.clientWidth || 400, height: 200,
      cursor: { drag: { x: true, y: false } },
      scales: { x: { time: true } },
      tzDate: ts => uPlot.tzDate(new Date(ts * 1e3), "Etc/UTC"),   // times in the atlas are UTC
      axes: [{ ...AXIS }, { ...AXIS, label: unit ?? "", size: 56 }],
      series: [{ label: "UTC" }, { label: label ?? "value", stroke: "#ecebe6", width: 1.5 }],
    }, data, el);
    return () => plot.destroy();
  }, [points, unit, label]);
  return <div ref={ref} className="chart" />;
}
