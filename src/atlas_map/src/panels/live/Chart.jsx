import { useEffect, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";

const AXIS = { stroke: "#a8a69d", grid: { stroke: "rgba(255,255,255,0.06)" }, ticks: { stroke: "rgba(255,255,255,0.12)" } };

// Taller as the side panel is dragged wider, so a widened panel shows more of the series' shape, not just a longer strip.
export const chartHeight = width => Math.round(Math.min(420, Math.max(200, width * 0.48)));

// points: [[ms, value]]. Drag across to zoom, double-click to reset (uPlot's own gesture); the legend follows the crosshair.
export default function Chart({ points, unit, label }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    const data = [points.map(p => p[0] / 1000), points.map(p => p[1])];
    const w0 = el.clientWidth || 400;
    const plot = new uPlot({
      width: w0, height: chartHeight(w0),
      cursor: { drag: { x: true, y: false } },
      scales: { x: { time: true } },
      tzDate: ts => uPlot.tzDate(new Date(ts * 1e3), "Etc/UTC"),   // times in the atlas are UTC
      axes: [{ ...AXIS }, { ...AXIS, label: unit ?? "", size: 56 }],
      series: [{ label: "UTC" }, { label: label ?? "value", stroke: "#ecebe6", width: 1.5 }],
    }, data, el);
    // The panel's width changes as its edge is dragged; uPlot sizes in pixels, so follow the container.
    const ro = typeof ResizeObserver === "function" ? new ResizeObserver(() => {
      const w = el.clientWidth;
      if (w && w !== plot.width) plot.setSize({ width: w, height: chartHeight(w) });
    }) : null;
    ro?.observe(el);
    return () => { ro?.disconnect(); plot.destroy(); };
  }, [points, unit, label]);
  return <div ref={ref} className="chart" />;
}
