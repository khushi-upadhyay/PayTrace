import logging
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.api.dependencies import get_db
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/health", tags=["Health"])

@router.get("")
def get_health(db: Session = Depends(get_db)):
    """Health check validating API, database connectivity, and configuration status."""
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        logger.error("Health check database probe failed", exc_info=True)
        db_status = "unhealthy"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "app_env": settings.APP_ENV,
        "database": db_status,
        "paypal_environment": settings.paypal_mode,
        "paypal_configured": settings.is_paypal_configured,
        "ai_investigator": "live" if settings.is_ai_configured else "deterministic_fallback",
        "version": "1.0.0",
    }
