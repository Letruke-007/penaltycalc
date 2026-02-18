# backend/app/api/__init__.py
from __future__ import annotations

from fastapi import APIRouter

from .pdfs import router as pdfs_router

api_router = APIRouter()
api_router.include_router(pdfs_router)
