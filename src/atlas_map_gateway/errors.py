from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class UpstreamError(Exception):
    def __init__(self, source: str, message: str, status: int = 502):
        super().__init__(message)
        self.source, self.message, self.status = source, message, status


class Busy(Exception):
    def __init__(self, source: str):
        super().__init__(source)
        self.source = source


def body(source: str, message: str) -> dict:
    return {"error": {"source": source, "message": message}}


def install(app: FastAPI) -> None:
    @app.exception_handler(UpstreamError)
    def _upstream(_: Request, exc: UpstreamError):
        return JSONResponse(body(exc.source, exc.message), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    def _invalid(_: Request, exc: RequestValidationError):
        parts = [f"{'.'.join(str(x) for x in e.get('loc', ())[1:]) or 'request'}: {e.get('msg', 'invalid')}" for e in exc.errors()]
        return JSONResponse(body("atlas", "; ".join(parts) or "invalid request"), status_code=422)

    @app.exception_handler(Busy)
    def _busy(_: Request, exc: Busy):
        return JSONResponse(body(exc.source, f"{exc.source} is busy; try again shortly"), status_code=503)
