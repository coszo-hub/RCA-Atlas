from __future__ import annotations

import socket
import urllib.error
from typing import Callable

from . import errors


def _is_timeout(exc: BaseException) -> bool:
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return True
    return isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, (socket.timeout, TimeoutError))


def call_toolkit(source: str, fn: Callable[[], dict]) -> dict:
    try:
        result = fn()
    except ValueError as exc:
        raise errors.UpstreamError(source, str(exc), 422) from None
    except Exception as exc:
        if _is_timeout(exc):
            raise errors.UpstreamError(source, f"{source} did not respond in time", 504) from None
        raise errors.UpstreamError(source, f"{source} request failed: {exc}") from None
    if not isinstance(result, dict) or not result.get("ok"):
        err = (result or {}).get("error") if isinstance(result, dict) else None
        message = err.get("message") if isinstance(err, dict) else str(err or "unavailable")
        raise errors.UpstreamError(source, message)
    return result
