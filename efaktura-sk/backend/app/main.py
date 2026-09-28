"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ai, auth, companies, dashboard, integrations, invoices, peppol
from app.config import get_settings
from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="eFaktúra SK API", version="0.1.0", lifespan=lifespan,
                  description="Slovak e-invoicing: EN 16931 / UBL 2.1 / Peppol BIS Billing 3.0")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    api = APIRouter(prefix="/api/v1")
    for module in (auth, companies, invoices, dashboard, ai, integrations, peppol):
        api.include_router(module.router)
    app.include_router(api)

    @app.get("/healthz", include_in_schema=False)
    def healthz() -> dict:
        return {"status": "ok"}

    return app


app = create_app()
