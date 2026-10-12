import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging import setup_logging

# Routers
from app.api.routes.health import router as health_router
from app.api.routes.payments import router as payments_router
from app.api.routes.paypal import router as paypal_router
from app.api.routes.webhooks import router as webhooks_router
from app.api.routes.sessions import router as sessions_router, payment_session_router
from app.api.routes.ai import router as ai_router
from app.api.routes.incidents import router as incidents_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.approvals import router as approvals_router
from app.api.routes.demo import router as demo_router
from app.api.routes.settings import router as settings_router

setup_logging()
logger = logging.getLogger("paytrace")

app = FastAPI(
    title="PayTrace API",
    description="Cross-Signal AI Payment Investigation & Observability Platform for PayPal",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global error handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error. The investigation engine logged the failure."},
    )

# Versioned API routes (/api/v1)
api_v1_prefix = "/api/v1"
app.include_router(health_router, prefix=api_v1_prefix)
app.include_router(payments_router, prefix=api_v1_prefix)
app.include_router(payment_session_router, prefix=api_v1_prefix)
app.include_router(paypal_router, prefix=api_v1_prefix)
app.include_router(sessions_router, prefix=api_v1_prefix)
app.include_router(ai_router, prefix=api_v1_prefix)
app.include_router(incidents_router, prefix=api_v1_prefix)
app.include_router(analytics_router, prefix=api_v1_prefix)
app.include_router(approvals_router, prefix=api_v1_prefix)
app.include_router(demo_router, prefix=api_v1_prefix)
app.include_router(settings_router, prefix=api_v1_prefix)

# PayPal Webhook route (both root /api/webhooks/paypal and /api/v1/webhooks/paypal)
app.include_router(webhooks_router)

@app.get("/")
def root():
    return {
        "service": "PayTrace API",
        "tagline": "Don't just know a payment failed. Know exactly why.",
        "docs": "/docs",
        "version": "1.0.0",
    }
