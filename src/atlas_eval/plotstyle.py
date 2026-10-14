"""One figure style for every report chart: reference palette, hairline chrome, system sans."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": [f for f in ("SF Pro Text", "Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans")
                    if f in {x.name for x in font_manager.fontManager.ttflist}][:1] or ["DejaVu Sans"],
    "font.size": 9, "axes.titlesize": 10, "axes.titleweight": "regular", "axes.titlelocation": "left",
    "axes.edgecolor": AXIS, "axes.linewidth": 0.6, "axes.labelcolor": INK_2, "text.color": INK,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "grid.linestyle": "-",
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
    "lines.linewidth": 2.0, "lines.markersize": 5, "figure.dpi": 150, "savefig.dpi": 150,
})


def new(width: float = 7.0, height: float = 3.2, **kwargs):
    return plt.subplots(figsize=(width, height), **kwargs)


def save(fig, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    return path
