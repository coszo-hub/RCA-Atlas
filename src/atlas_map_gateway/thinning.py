from __future__ import annotations

import math


def minmax(times: list[float], values: list[float], max_points: int) -> tuple[list[float], list[float]]:
    """Keep each bucket's min and max (in time order) so spikes survive decimation."""
    n = len(times)
    if n <= max_points:
        return list(times), list(values)
    size = math.ceil(n / (max_points // 2))
    out_t, out_v = [], []
    for start in range(0, n, size):
        idx = range(start, min(start + size, n))
        lo = min(idx, key=lambda i: values[i])
        hi = max(idx, key=lambda i: values[i])
        for i in sorted({lo, hi}):
            out_t.append(times[i])
            out_v.append(values[i])
    return out_t, out_v
