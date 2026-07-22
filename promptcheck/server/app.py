"""FastAPI app for the PromptCheck dashboard.

Serves a read-only JSON API over the history DB, plus the built React frontend
(web/dist) if present. Create with `create_app(db_path)`.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import queries

# Frontend build output, relative to the repo root.
_WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


def create_app(db_path: str | Path = ".promptcheck/history.db") -> FastAPI:
    db_path = str(db_path)
    app = FastAPI(title="PromptCheck Dashboard", version="0.1.0")

    # Allow the Vite dev server (localhost:5173) to call the API during dev.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    def _conn():
        if not os.path.exists(db_path):
            raise HTTPException(
                404, f"No history DB at {db_path}. Run `promptcheck run` first."
            )
        return queries.open_db(db_path)

    @app.get("/api/health")
    def health():
        return {"ok": True, "db": db_path, "db_exists": os.path.exists(db_path)}

    @app.get("/api/suites")
    def suites():
        conn = _conn()
        try:
            return queries.list_suites(conn)
        finally:
            conn.close()

    @app.get("/api/suites/{name}")
    def suite(name: str):
        conn = _conn()
        try:
            detail = queries.suite_detail(conn, name)
            if detail is None:
                raise HTTPException(404, f"No suite named {name!r}.")
            return detail
        finally:
            conn.close()

    @app.get("/api/runs/{run_id}")
    def run(run_id: int):
        conn = _conn()
        try:
            detail = queries.run_detail(conn, run_id)
            if detail is None:
                raise HTTPException(404, f"No run #{run_id}.")
            return detail
        finally:
            conn.close()

    @app.get("/api/runs/{base_id}/diff/{cur_id}")
    def diff(base_id: int, cur_id: int):
        conn = _conn()
        try:
            d = queries.run_diff(conn, base_id, cur_id)
            if d is None:
                raise HTTPException(404, "One or both runs not found.")
            return d
        finally:
            conn.close()

    # Serve the built SPA at / (if it exists). API routes above take priority.
    if _WEB_DIST.exists():
        app.mount("/", StaticFiles(directory=str(_WEB_DIST), html=True), name="web")

    return app
