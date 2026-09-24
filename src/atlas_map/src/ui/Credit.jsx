import "./ui.css";

// The terrain credits (GMRT is CC BY 4.0) stay on screen whatever the legend is doing.
export default function Credit({ credit, auv = false, subsurface = false }) {
  return (
    <div className="credit" aria-label="Map credits">
      Bathymetry: {credit ?? "GMRT, Ryan et al. (2009), CC BY 4.0"}{auv && " · Axial summit: MBARI AUV survey, 1 m"}{subsurface && " · Subsurface: M. Kidiwela, axial_visuals"}
    </div>
  );
}
