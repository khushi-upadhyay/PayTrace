from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.db.models.incident import Incident
from app.db.models.payment import Payment
from app.db.models.session import Session as BrowserSession
from app.db.models.user import User

router = APIRouter(prefix="/search", tags=["Workspace Search"])


@router.get("")
def search_workspace(q: str = Query(..., min_length=2, max_length=128), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Search persisted workspace records; results link to existing detail views."""
    term = q.strip()
    if len(term) < 2:
        return {"items": []}
    pattern = f"%{term}%"
    results = []
    payments = db.query(Payment).filter(or_(
        Payment.id.ilike(pattern), Payment.paypal_order_id.ilike(pattern),
        Payment.customer_ref.ilike(pattern), Payment.failure_code.ilike(pattern),
    )).order_by(Payment.created_at.desc()).limit(8).all()
    for payment in payments:
        if term.lower() in (payment.paypal_order_id or "").lower():
            kind, label = "PayPal order", payment.paypal_order_id
        elif term.lower() in (payment.customer_ref or "").lower():
            kind, label = "Customer", payment.customer_ref
        elif term.lower() in (payment.failure_code or "").lower():
            kind, label = "Failure code", payment.failure_code
        else:
            kind, label = "Payment", payment.id
        results.append({"category": kind, "id": payment.id, "label": label, "description": f"{payment.status} · {payment.amount} {payment.currency}", "href": f"/payments/{payment.id}"})

    sessions = db.query(BrowserSession).filter(or_(BrowserSession.id.ilike(pattern), BrowserSession.visitor_ref.ilike(pattern))).order_by(BrowserSession.started_at.desc()).limit(8).all()
    for session in sessions:
        results.append({"category": "Session", "id": session.id, "label": session.id, "description": f"{session.visitor_ref} · started {session.started_at.isoformat()}", "href": f"/sessions/{session.id}"})

    incidents = db.query(Incident).filter(or_(Incident.id.ilike(pattern), Incident.detection_rule.ilike(pattern), Incident.title.ilike(pattern))).order_by(Incident.started_at.desc()).limit(8).all()
    for incident in incidents:
        results.append({"category": "Incident", "id": incident.id, "label": incident.title, "description": f"{incident.severity} · {incident.status} · {incident.detection_rule or 'rule not recorded'}", "href": f"/incidents/{incident.id}"})
    return {"items": results[:24]}
