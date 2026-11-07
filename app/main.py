"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .ratelimit import RateLimitMiddleware
from .routers import auth, compounds, screening

logger = logging.getLogger("iksir")
logging.basicConfig(level=logging.INFO)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Fail fast on bad configuration, then create tables."""
    problems = settings.validate()
    if problems:
        for problem in problems:
            logger.error("configuration problem: %s", problem)
        raise RuntimeError(
            "Refusing to start with an invalid production configuration: " + "; ".join(problems)
        )

    init_db()
    logger.info(
        "Iksir started (env=%s, db=%s)",
        settings.environment,
        settings.database_url.split("://", 1)[0],
    )
    yield


app = FastAPI(
    title="Iksir",
    description=(
        "Compound screening workbench. Parses SMILES, computes descriptors from "
        "published fragment methods, and scores compounds against real target "
        "pocket profiles. Ligand-based triage -- not docking."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# Middleware order matters: the rate limiter runs outside CORS so that a
# throttled cross-origin request still gets a readable body.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth.router)
app.include_router(compounds.router)
app.include_router(screening.router)


@app.middleware("http")
async def security_headers(request: Request, call_next):  # noqa: ANN001
    """Add the baseline security headers to every response.

    None of these change behaviour; they close off classes of attack that the
    app has no reason to be exposed to. No CSP here because the app serves no
    inline scripts -- when it does, add one.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log the traceback but never leak internals to the client."""
    logger.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our side. The error has been logged."},
    )


@app.get("/api/health", tags=["meta"], summary="Health check")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "1.0.0", "environment": settings.environment}


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    return {"status": "ok"}


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")
