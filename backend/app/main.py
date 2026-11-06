import logging
from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging import setup_logging

# Routers
from app.api.dependencies import get_current_user
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.payments import router as payments_router
from app.api.routes.paypal import router as paypal_router
from app.api.routes.webhooks import router as webhooks_router
from app.api.routes.sessions import router as sessions_router, payment_session_router
from app.api.routes.ai import router as ai_router
from app.api.routes.incidents import router as incidents_router
from app.api.routes.analytics import router as analytics_router
from app.api.routes.search import router as search_router
from app.api.routes.approvals import router as approvals_router
from app.api.routes.demo import router as demo_router
from app.api.routes.settings import router as settings_router
from app.api.routes.shelfswipe import router as shelfswipe_router
from app.api.routes.disputes import router as disputes_router

setup_logging()
logger = logging.getLogger("paytrace")

_is_dev = settings.APP_ENV.strip().lower() in {"development", "test"}

app = FastAPI(
    title="PayTrace API",
    description="Cross-Signal AI Payment Investigation & Observability Platform for PayPal",
    version="1.0.0",
    # Interactive API docs expose the full route map; keep them to development only.
    docs_url="/docs" if _is_dev else None,
    redoc_url="/redoc" if _is_dev else None,
    openapi_url="/openapi.json" if _is_dev else None,
)

# CORS configuration. Credentialed requests (Authorization header) must never be paired
# with a wildcard origin: a literal "*" alongside allow_credentials=True lets any site on
# the internet make authenticated calls against this API using a victim's stolen token.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With", "X-Checkout-Token", "Idempotency-Key"],
)

_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
    if request.url.path not in _DOCS_PATHS:
        # The API serves JSON only; the interactive docs load assets from a CDN so they are exempt.
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    if settings.APP_ENV.strip().lower() not in {"development", "test"}:
        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
    return response

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
# Operator console routes require a logged-in user. Health, auth, the customer checkout
# flow (paypal/sessions/shelfswipe) and PayPal webhooks stay public.
operator_only = [Depends(get_current_user)]

app.include_router(auth_router, prefix=api_v1_prefix)
app.include_router(health_router, prefix=api_v1_prefix)
app.include_router(payments_router, prefix=api_v1_prefix, dependencies=operator_only)
app.include_router(payment_session_router, prefix=api_v1_prefix)
app.include_router(paypal_router, prefix=api_v1_prefix)
app.include_router(sessions_router, prefix=api_v1_prefix)
app.include_router(ai_router, prefix=api_v1_prefix, dependencies=operator_only)
app.include_router(incidents_router, prefix=api_v1_prefix, dependencies=operator_only)
app.include_router(analytics_router, prefix=api_v1_prefix, dependencies=operator_only)
app.include_router(search_router, prefix=api_v1_prefix, dependencies=operator_only)
app.include_router(approvals_router, prefix=api_v1_prefix, dependencies=operator_only)
app.include_router(demo_router, prefix=api_v1_prefix, dependencies=operator_only)
app.include_router(settings_router, prefix=api_v1_prefix, dependencies=operator_only)
app.include_router(shelfswipe_router, prefix=api_v1_prefix)
app.include_router(disputes_router, prefix=api_v1_prefix, dependencies=operator_only)

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
