"""Health check endpoint."""

from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()


@router.get("/health")
def health_check():
    return {
        "success": True,
        "data": {
            "status": "ok",
            "paper_trading": settings.paper_trading,
            "app_name": settings.app_name,
        },
    }
