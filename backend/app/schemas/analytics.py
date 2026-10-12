from pydantic import BaseModel
from typing import List, Dict, Any
from decimal import Decimal

class AnalyticsOverviewResponse(BaseModel):
    total_payments: int
    successful_payments: int
    failed_payments: int
    uncertain_payments: int
    success_rate_percent: float
    failure_rate_percent: float
    potential_revenue_at_risk: Decimal
    currency: str = "USD"
    average_latency_ms: int
    average_webhook_delay_seconds: float
    volume_over_time: List[Dict[str, Any]]
    status_breakdown: List[Dict[str, Any]]
    failure_categories: List[Dict[str, Any]]
    open_incidents_count: int
