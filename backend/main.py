"""Study Companion API entrypoint.

Run locally:  python main.py
Or:           uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.database import get_db, init_db
from app.routes import auth, chat, documents, progress, resources, tasks
from app.schemas import HealthResponse

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("study_companion")

settings = get_settings()
STATIC_DIR = Path(__file__).resolve().parent / "static"


def asset_version() -> str:
    """Content-derived cache key for the bundled client."""
    stamp = 0
    for name in ("app.js", "styles.css", "resources.js", "resources.css", "thesis-agent.js", "thesis-agent.css"):
        path = STATIC_DIR / name
        if path.exists():
            stat = path.stat()
            stamp = max(stamp, int(stat.st_mtime_ns) + stat.st_size)
    return str(stamp)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    logger.info(
        "%s v%s ready - database=%s ai=%s",
        settings.app_name,
        __version__,
        "sqlite" if settings.is_sqlite else "postgres",
        "anthropic" if settings.ai_enabled else "rule-based (no ANTHROPIC_API_KEY)",
    )
    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "AI study companion that turns a student's own course material into a topic map, "
        "a study plan and a hint-first coach."
    ),
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def revalidate_static(request: Request, call_next):
    """Make browsers revalidate the bundled client after an update.

    Without this a cached ``styles.css``/``app.js`` can outlive a deployment and
    the UI silently runs old code against a new API.
    """
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path in {"/", "/favicon.ico"}:
        # Never clobber a stricter value set by the handler (the shell uses no-store).
        response.headers.setdefault("Cache-Control", "no-cache, must-revalidate")
    return response


app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(tasks.router)
app.include_router(chat.router)
app.include_router(progress.router)
app.include_router(resources.router, prefix="/api")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> HTMLResponse:
        """Serve the shell with a content-derived asset version.

        The version is baked into the script/stylesheet URLs, so a browser can
        never run last deploy's client against this API - and the HTML itself is
        never cached.
        """
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(
            html.replace("__ASSET_VERSION__", asset_version()),
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health(db: Session = Depends(get_db)) -> HealthResponse:
    database = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - health must never raise
        database = f"error: {exc.__class__.__name__}"

    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        app=settings.app_name,
        version=__version__,
        ai_provider="anthropic" if settings.ai_enabled else "rules",
        database=database,
    )


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.debug)
