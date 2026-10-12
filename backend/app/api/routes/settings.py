from fastapi import APIRouter
from app.core.config import settings

router = APIRouter(prefix="/settings", tags=["Settings"])

@router.get("")
def get_system_settings():
    """Returns safe integration configuration status without exposing credentials."""
    masked_client_id = ""
    if settings.PAYPAL_CLIENT_ID:
        cid = settings.PAYPAL_CLIENT_ID
        masked_client_id = f"{cid[:4]}...{cid[-4:]}" if len(cid) > 8 else "***"

    return {
        "paypal": {
            "is_configured": settings.is_paypal_configured,
            "environment": settings.PAYPAL_ENVIRONMENT,
            "client_id_masked": masked_client_id,
            "webhook_id_configured": bool(settings.PAYPAL_WEBHOOK_ID),
            "status_label": "Live PayPal Sandbox" if settings.is_paypal_configured else "Mock Sandbox (Credential-Free Demo)",
        },
        "ai": {
            "is_configured": settings.is_ai_configured,
            "provider": settings.AI_PROVIDER,
            "model": settings.AI_MODEL,
            "status_label": "Live LLM Provider" if settings.is_ai_configured else "Deterministic Fallback Engine (Active)",
        },
        "database": {
            "type": "PostgreSQL" if "postgres" in settings.DATABASE_URL else "SQLite (Local Dev)",
            "connected": True,
        },
        "app_env": settings.APP_ENV,
        "frontend_origin": settings.FRONTEND_ORIGIN,
    }
