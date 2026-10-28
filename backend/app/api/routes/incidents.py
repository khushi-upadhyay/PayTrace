from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from app.api.dependencies import get_current_user, get_db
from app.db.models.user import User
from app.core.time import utc_now
from app.db.models.incident import Incident
from app.db.models.payment import Payment
from app.schemas.incident import (
    IncidentListResponse,
    IncidentResponse,
    IncidentDetailResponse,
    IncidentReportResponse,
)
from app.schemas.payment import PaymentResponse
from app.services.incidents.detector import incident_detector

router = APIRouter(prefix="/incidents", tags=["Incidents"])

@router.get("", response_model=IncidentListResponse)
def list_incidents(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Lists detected payment incidents, evaluating rules on the fly."""
    incident_detector.evaluate_system_health(db)
    incidents = db.query(Incident).order_by(Incident.started_at.desc()).all()
    return IncidentListResponse(
        items=[IncidentResponse.model_validate(inc) for inc in incidents],
        total=len(incidents),
    )

@router.get("/{incident_id}", response_model=IncidentDetailResponse)
def get_incident(incident_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Retrieves detailed incident diagnosis with linked affected payments."""
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")

    # Fetch affected payments depending on rule
    affected = []
    if inc.detection_rule == "CAPTURE_TIMEOUT_SPIKE":
        affected = db.query(Payment).filter(Payment.status == "CAPTURE_UNCERTAIN").all()
    elif inc.detection_rule == "CAPTURE_DENIAL_RATE_HIGH":
        affected = db.query(Payment).filter(Payment.status.in_(["DENIED", "CAPTURE_FAILED"])).all()
    else:
        affected = db.query(Payment).filter(Payment.status != "CAPTURED").limit(10).all()

    resp = IncidentDetailResponse.model_validate(inc)
    resp.affected_payments = [PaymentResponse.model_validate(p) for p in affected]
    return resp

@router.post("/{incident_id}/report", response_model=IncidentReportResponse)
def generate_incident_report(incident_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Generates an executive diagnostic incident report."""
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found")

    findings = [
        f"Incident '{inc.title}' triggered by rule '{inc.detection_rule or 'THRESHOLD_BREACH'}'.",
        f"Affects {inc.affected_payment_count} payments representing ${inc.revenue_at_risk:.2f} {inc.currency} in potential revenue at risk.",
        f"Root Cause Assessment: {inc.root_cause or 'Under investigation'}.",
    ]

    mitigations = [
        "Enforce order reconciliation before initiating any retry capture to prevent duplicate charges.",
        "Check merchant backend HTTP timeout settings (increase read timeout or implement asynchronous webhooks).",
        "Monitor PayPal Developer Sandbox status alerts.",
    ]

    return IncidentReportResponse(
        incident_id=inc.id,
        title=inc.title,
        severity=inc.severity,
        status=inc.status,
        affected_payments_count=inc.affected_payment_count,
        revenue_at_risk=inc.revenue_at_risk,
        currency=inc.currency,
        detection_rule=inc.detection_rule,
        executive_summary=(
            f"PayTrace Incident Report: Detected {inc.severity} severity anomaly impacting {inc.affected_payment_count} payments. "
            f"Summary: {inc.ai_summary or inc.root_cause}"
        ),
        detailed_findings=findings,
        timeline_analysis=f"First breach recorded at {inc.started_at.isoformat()}. Last evaluation at {utc_now().isoformat()}.",
        recommended_mitigations=mitigations,
        generated_at=utc_now(),
    )
