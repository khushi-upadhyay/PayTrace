from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.api.dependencies import get_current_user, get_db
from app.core.config import settings
from app.db.models.user import User

router = APIRouter(prefix="/settings", tags=["Settings"])

@router.get("")
def get_system_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Returns safe integration configuration status without exposing credentials."""
    masked_client_id = ""
    if settings.PAYPAL_CLIENT_ID:
        cid = settings.PAYPAL_CLIENT_ID
        masked_client_id = f"{cid[:4]}...{cid[-4:]}" if len(cid) > 8 else "***"

    try:
        db.execute(text("SELECT 1"))
        database_connected = True
    except Exception:
        db.rollback()
        database_connected = False

    return {
        "paypal": {
            "is_configured": settings.is_paypal_configured,
            "environment": settings.paypal_mode,
            "client_id_masked": masked_client_id,
            "webhook_id_configured": bool(settings.PAYPAL_WEBHOOK_ID),
            "status_label": (
                f"PayPal {settings.paypal_mode.title()}"
                if settings.is_paypal_configured
                else "Simulated Demo (No PayPal API calls)"
            ),
        },
        "ai": {
            "is_configured": settings.is_ai_configured,
            "provider": settings.AI_PROVIDER,
            "model": settings.AI_MODEL,
            "status_label": "Live LLM Provider" if settings.is_ai_configured else "Deterministic Fallback Engine (Active)",
        },
        "database": {
            "type": "PostgreSQL" if "postgres" in settings.DATABASE_URL else "SQLite (Local Dev)",
            "connected": database_connected,
        },
        "app_env": settings.APP_ENV,
        "frontend_origin": settings.FRONTEND_ORIGIN,
    }
