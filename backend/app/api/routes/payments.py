from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from typing import Optional
from urllib.parse import urlsplit
from app.api.dependencies import get_current_user, get_db
from app.db.models.user import User
from app.db.models.payment import Payment
from app.db.models.payment_event import PaymentEvent
from app.db.models.session import SessionEvent
from app.schemas.payment import PaymentResponse, PaymentListResponse
from app.schemas.timeline import TimelineResponse, PaymentEventResponse
from app.services.lifecycle.engine import lifecycle_engine

router = APIRouter(prefix="/payments", tags=["Payments"])

@router.get("/workspace")
def get_payment_workspace(
    limit: int = Query(250, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Actual payment aggregates plus a bounded recent row set for the investigation UI."""
    total = db.query(func.count(Payment.id)).scalar() or 0
    successful_statuses = ("CAPTURED", "REFUNDED")
    failed_statuses = ("DENIED", "CAPTURE_FAILED", "DISPUTED")
    pending_statuses = ("CREATED", "APPROVED", "CAPTURE_PENDING", "CAPTURE_UNCERTAIN")
    successful = db.query(func.count(Payment.id)).filter(Payment.status.in_(successful_statuses)).scalar() or 0
    failed = db.query(func.count(Payment.id)).filter(Payment.status.in_(failed_statuses)).scalar() or 0
    processed_amounts = [
        {"currency": currency, "amount": str(amount or 0)}
        for currency, amount in db.query(Payment.currency, func.sum(Payment.amount))
        .filter(Payment.status.in_(successful_statuses)).group_by(Payment.currency).all()
    ]
    avg_latency, latency_count = db.query(
        func.avg(PaymentEvent.latency_ms), func.count(PaymentEvent.latency_ms)
    ).filter(PaymentEvent.latency_ms.isnot(None)).one()

    status_breakdown = [
        {"status": status, "count": count}
        for status, count in db.query(Payment.status, func.count(Payment.id))
        .group_by(Payment.status).order_by(func.count(Payment.id).desc()).all()
    ]
    daily_volume = [
        {"date": str(day), "count": count}
        for day, count in db.query(func.date(Payment.created_at), func.count(Payment.id))
        .group_by(func.date(Payment.created_at)).order_by(func.date(Payment.created_at)).all()
    ]
    failure_sources = [
        {"provider": provider or "Unknown", "count": count}
        for provider, count in db.query(Payment.source_mode, func.count(Payment.id))
        .filter(Payment.status.in_(failed_statuses)).group_by(Payment.source_mode)
        .order_by(func.count(Payment.id).desc()).all()
    ]
    high_latency_count = db.query(func.count(func.distinct(PaymentEvent.payment_id)))\
        .filter(PaymentEvent.latency_ms >= 2000).scalar() or 0
    high_latency_ids = [row[0] for row in db.query(PaymentEvent.payment_id).distinct()\
        .filter(PaymentEvent.latency_ms >= 2000).limit(100).all()]
    repeated_failures = db.query(Payment.customer_ref, func.count(Payment.id))\
        .filter(Payment.status.in_(failed_statuses)).group_by(Payment.customer_ref)\
        .having(func.count(Payment.id) >= 2).order_by(func.count(Payment.id).desc()).limit(20).all()
    anomalies = []
    repeated_customer_refs = [customer_ref for customer_ref, _count in repeated_failures]
    failed_rows = db.query(Payment.customer_ref, Payment.id).filter(
        Payment.customer_ref.in_(repeated_customer_refs), Payment.status.in_(failed_statuses)
    ).order_by(Payment.created_at.desc()).all() if repeated_customer_refs else []
    failed_ids_by_customer = {}
    for customer_ref, payment_id in failed_rows:
        failed_ids_by_customer.setdefault(customer_ref, []).append(payment_id)
    for customer_ref, count in repeated_failures:
        ids = failed_ids_by_customer.get(customer_ref, [])[:100]
        anomalies.append({"kind": "repeat_customer_failures", "title": "Repeated payment failures for one customer",
            "evidence": f"{count} failed transactions share the same customer reference.", "count": count, "payment_ids": ids})
    if high_latency_count:
        anomalies.append({"kind": "high_observed_latency", "title": "Payment events over 2 seconds",
            "evidence": f"{high_latency_count} transaction(s) have a recorded payment event latency of at least 2,000 ms.",
            "count": high_latency_count, "payment_ids": high_latency_ids})

    items = db.query(Payment).order_by(Payment.created_at.desc()).limit(limit).all()
    durations = dict(db.query(PaymentEvent.payment_id, func.avg(PaymentEvent.latency_ms))
        .filter(PaymentEvent.payment_id.in_([p.id for p in items]) if items else False,
                PaymentEvent.latency_ms.isnot(None))
        .group_by(PaymentEvent.payment_id).all())
    transactions = []
    for payment in items:
        row = PaymentResponse.model_validate(payment).model_dump(mode="json")
        row["provider"] = payment.source_mode
        row["processing_duration_ms"] = round(float(durations[payment.id])) if payment.id in durations else None
        transactions.append(row)

    # This correlation only counts browser network events carrying the exact payment ID.
    endpoint_failures = {}
    correlated_network_events = []
    correlated = db.query(SessionEvent).join(Payment, SessionEvent.payment_id == Payment.id)\
        .filter(Payment.status.in_(failed_statuses), SessionEvent.category == "network")\
        .order_by(SessionEvent.occurred_at.desc()).limit(5000).all()
    for event in correlated:
        payload = event.payload_redacted or {}
        if not isinstance(payload, dict):
            payload = {}
        raw_endpoint = payload.get("url") or event.route or "Unknown endpoint"
        # Keep endpoint rollups free of query-string credentials and customer values.
        endpoint = urlsplit(str(raw_endpoint)).path or str(raw_endpoint).split("?", 1)[0]
        bucket = endpoint_failures.setdefault(endpoint, {"count": 0, "payment_ids": set()})
        bucket["count"] += 1
        bucket["payment_ids"].add(event.payment_id)
        correlated_network_events.append({
            "event_id": event.id,
            "payment_id": event.payment_id,
            "endpoint": endpoint,
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            "method": payload.get("method"),
            "status": payload.get("status"),
            "duration_ms": payload.get("duration_ms"),
            "trace_id": event.trace_id,
        })
    failures_by_endpoint = [{"endpoint": endpoint, "count": bucket["count"], "payment_ids": sorted(bucket["payment_ids"])}
        for endpoint, bucket in sorted(endpoint_failures.items(), key=lambda item: item[1]["count"], reverse=True)[:20]]

    return {
        "total_transactions": total,
        "successful_count": successful,
        "failed_count": failed,
        "pending_count": db.query(func.count(Payment.id)).filter(Payment.status.in_(pending_statuses)).scalar() or 0,
        "success_rate_percent": round((successful / total) * 100, 1) if total else 0,
        "processed_amounts": processed_amounts,
        "average_event_latency_ms": round(float(avg_latency)) if avg_latency is not None else None,
        "latency_sample_count": int(latency_count or 0),
        "status_breakdown": status_breakdown,
        "daily_volume": daily_volume,
        "failure_sources": failure_sources,
        "failures_by_endpoint": failures_by_endpoint,
        "endpoint_event_sample_limit": 5000,
        "correlated_network_events": correlated_network_events,
        "anomalies": anomalies,
        "transactions": transactions,
        "transaction_sample_limit": limit,
    }

@router.get("", response_model=PaymentListResponse)
def list_payments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    source_mode: Optional[str] = None,
    actor: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: Optional[str] = None,
    sort_order: Optional[str] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Lists payments with search, pagination, and multi-field filters."""
    query = db.query(Payment)

    if status:
        query = query.filter(Payment.status == status)
    if source_mode:
        query = query.filter(Payment.source_mode == source_mode)
    if actor:
        query = query.filter(Payment.actor == actor)
    if search:
        search_fmt = f"%{search}%"
        query = query.filter(
            or_(
                Payment.id.ilike(search_fmt),
                Payment.paypal_order_id.ilike(search_fmt),
                Payment.paypal_capture_id.ilike(search_fmt),
                Payment.customer_ref.ilike(search_fmt),
                Payment.failure_code.ilike(search_fmt),
                Payment.failure_reason.ilike(search_fmt),
            )
        )

    total = query.count()
    sortable = {
        "id": Payment.id,
        "paypal_order_id": Payment.paypal_order_id,
        "paypal_capture_id": Payment.paypal_capture_id,
        "session_id": Payment.session_id,
        "failure_code": Payment.failure_code,
        "failure_reason": Payment.failure_reason,
        "currency": Payment.currency,
        "created_at": Payment.created_at,
        "amount": Payment.amount,
        "status": Payment.status,
        "source_mode": Payment.source_mode,
        "customer_ref": Payment.customer_ref,
    }
    sort_column = sortable.get(sort_by or "created_at", Payment.created_at)
    sort_expression = sort_column.asc() if sort_order == "asc" else sort_column.desc()
    items = (
        query.order_by(sort_expression, Payment.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return PaymentListResponse(
        items=[PaymentResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )

@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(payment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Retrieves full details of a single payment."""
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail=f"Payment {payment_id} not found")
    return PaymentResponse.model_validate(payment)

@router.get("/{payment_id}/timeline", response_model=TimelineResponse)
def get_payment_timeline(payment_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Retrieves unified, chronological lifecycle event timeline."""
    payment = db.query(Payment).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail=f"Payment {payment_id} not found")

    events = lifecycle_engine.get_timeline(db, payment_id)

    duration_ms = None
    if len(events) >= 2:
        start = events[0].occurred_at
        end = events[-1].occurred_at
        duration_ms = int((end - start).total_seconds() * 1000)

    return TimelineResponse(
        payment_id=payment.id,
        current_status=payment.status,
        events=[PaymentEventResponse.model_validate(e) for e in events],
        total_events=len(events),
        duration_ms=duration_ms,
    )
