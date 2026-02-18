import os
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse

from app.api.pdfs import router as pdfs_router
from app.api.batches import router as batches_router
from app.api.items import router as items_router


def _parse_cors_origins(env_value: str | None) -> List[str]:
    """
    Parses comma-separated origins:
      CORS_ALLOW_ORIGINS="http://localhost:5173,http://127.0.0.1:5173"
    Empty/None -> default list.
    """
    if not env_value:
        return [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    parts = [p.strip() for p in env_value.split(",")]
    return [p for p in parts if p]


app = FastAPI(title="pdf2xlsx-app")


# ----------------------------
# Healthcheck (for Docker)
# ----------------------------
@app.get("/health", include_in_schema=False)
def health() -> PlainTextResponse:
    return PlainTextResponse("ok")


# ----------------------------
# CORS
# ----------------------------
allow_origins = _parse_cors_origins(os.getenv("CORS_ALLOW_ORIGINS"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# ----------------------------
# API routers
# ----------------------------
# IMPORTANT: nginx проксирует /api/ -> http://backend:8000/api/
# Поэтому все роутеры вешаем под /api
app.include_router(batches_router, prefix="/api")
app.include_router(items_router, prefix="/api")
app.include_router(pdfs_router, prefix="/api")
