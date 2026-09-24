from __future__ import annotations

import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Callable, TypeVar

from .errors import Busy

T = TypeVar("T")


class TTLCache:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock, self._data, self._lock = clock, {}, threading.Lock()

    def get_or_set(self, key: str, ttl: float, fn: Callable[[], T]) -> T:
        with self._lock:
            hit = self._data.get(key)
            if hit and hit[0] > self._clock():
                return hit[1]
        value = fn()   # exceptions propagate; nothing is stored
        with self._lock:
            self._data[key] = (self._clock() + ttl, value)
        return value


class HostLimiter:
    def __init__(self, limit: int, wait: float):
        self._wait = wait
        self._sems = defaultdict(lambda: threading.BoundedSemaphore(limit))

    @contextmanager
    def slot(self, source: str):
        sem = self._sems[source]
        if not sem.acquire(timeout=self._wait):
            raise Busy(source)
        try:
            yield
        finally:
            sem.release()
