from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.api.dependencies import get_db
from app.core.config import settings

router = APIRouter(prefix="/health", tags=["Health"])

@router.get("")
def get_health(db: Session = Depends(get_db)):
    """Health check validating API, database connectivity, and configuration status."""
    db_status = "healthy"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "app_env": settings.APP_ENV,
        "database": db_status,
        "paypal_sandbox": "configured" if settings.is_paypal_configured else "mock_mode",
        "ai_investigator": "live" if settings.is_ai_configured else "deterministic_fallback",
        "version": "1.0.0",
    }
