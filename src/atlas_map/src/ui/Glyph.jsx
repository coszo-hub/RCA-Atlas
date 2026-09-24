const SHAPES = {
  circle: c => <circle cx="6" cy="6" r="4.6" fill={c} />,
  triangle: c => <polygon points="6,1.2 10.8,10 1.2,10" fill={c} />,
  square: c => <rect x="1.8" y="1.8" width="8.4" height="8.4" fill={c} />,
  diamond: c => <polygon points="6,0.8 11.2,6 6,11.2 0.8,6" fill={c} />,
  hexagon: c => <polygon points="6,0.9 10.6,3.5 10.6,8.5 6,11.1 1.4,8.5 1.4,3.5" fill={c} />,
  bar: c => <rect x="0.8" y="4.3" width="10.4" height="3.4" fill={c} />,
};
export default function Glyph({ glyph, color, size = 11 }) {
  return <svg width={size} height={size} viewBox="0 0 12 12" aria-hidden="true" style={{ flex: "none" }}>{SHAPES[glyph](color)}</svg>;
}
