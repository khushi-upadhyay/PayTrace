from fastapi import APIRouter, Request, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.api.dependencies import get_db
from app.schemas.webhook import WebhookIngestResponse
from app.services.webhooks.processor import webhook_processor
import json

router = APIRouter(tags=["Webhooks"])

@router.post("/api/webhooks/paypal", response_model=WebhookIngestResponse, status_code=status.HTTP_200_OK)
@router.post("/api/v1/webhooks/paypal", response_model=WebhookIngestResponse, status_code=status.HTTP_200_OK)
async def handle_paypal_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Ingests PayPal webhooks with signature verification, idempotency deduplication,
    and lifecycle event correlation.
    """
    raw_body = await request.body()
    headers = {k.lower(): v for k, v in request.headers.items()}

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        return JSONResponse(status_code=400, content={"detail": "Malformed JSON body"})

    if not isinstance(payload, dict):
        return JSONResponse(status_code=400, content={"detail": "Webhook body must be a JSON object"})

    res_status, message, payment_id = await webhook_processor.process_webhook(
        db=db,
        payload=payload,
        headers=headers,
        raw_body=raw_body,
    )

    return WebhookIngestResponse(
        status=res_status,
        webhook_event_id=payload.get("id", "UNKNOWN"),
        event_type=payload.get("event_type", "UNKNOWN"),
        payment_id=payment_id,
        message=message,
    )
