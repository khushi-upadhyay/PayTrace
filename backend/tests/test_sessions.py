import uuid
from datetime import datetime, timedelta


def test_session_lifecycle_and_privacy_redaction(client):
    """
    Tests creating a browser recording session, batching interaction events,
    verifying automatic PII/credential redaction, and retrieving bounded replay.
    """
    # 1. Create a session
    create_res = client.post(
        "/api/v1/sessions",
        json={
            "visitor_ref": "shopper_test_session",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "metadata": {"screen": "1920x1080", "secret_token": "should-be-redacted"}
        }
    )
    assert create_res.status_code == 200
    sess_data = create_res.json()
    session_id = sess_data["id"]
    assert sess_data["visitor_ref"] == "shopper_test_session"
    assert sess_data["recording_enabled"] is True
    assert sess_data["metadata_redacted"]["screen"] == "1920x1080"
    assert sess_data["metadata_redacted"]["secret_token"] == "[REDACTED]"

    # 2. Batch rrweb interaction events with sensitive fields
    batch_res = client.post(
        f"/api/v1/sessions/{session_id}/events",
        json={
            "events": [
                {
                    "event_type": "checkout_start",
                    "payload": {"step": "cart_loaded"}
                },
                {
                    "event_type": "input",
                    "payload": {
                        "field": "credit_card",
                        "card_number": "4111 2222 3333 4444",
                        "cvv": "123",
                        "password": "buyer_secret_password",
                        "accessToken": "buyer_access_token",
                        "rrweb_node": {
                            "tagName": "input",
                            "attributes": {"type": "email", "value": "buyer@example.test"},
                        },
                    }
                },
                {
                    "event_type": "click",
                    "payload": {"button": "paypal_button_clicked"}
                }
            ]
        }
    )
    assert batch_res.status_code == 200
    assert batch_res.json()["events_ingested"] == 3

    # 3. Retrieve bounded replay events
    replay_res = client.get(f"/api/v1/sessions/{session_id}/replay?limit=100")
    assert replay_res.status_code == 200
    replay_data = replay_res.json()
    assert replay_data["total_events"] == 4
    assert replay_data["investigation_events"] == 4
    assert replay_data["rrweb_events"] == 0
    assert replay_data["user_agent"].startswith("Mozilla/")
    assert replay_data["metadata_redacted"]["secret_token"] == "[REDACTED]"

    # Verify sensitive data is redacted
    input_ev = next(e for e in replay_data["events"] if e["event_type"] == "input")
    payload = input_ev["payload"]
    assert payload["card_number"] == "[REDACTED]"
    assert payload["cvv"] == "[REDACTED]"
    assert payload["password"] == "[REDACTED]"
    assert payload["accessToken"] == "[REDACTED]"
    assert payload["rrweb_node"]["attributes"]["value"] == "[REDACTED]"


def test_rrweb_events_are_idempotent_and_sessions_are_listed(client):
    session = client.post("/api/v1/sessions", json={"visitor_ref": "anon_replay_test"}).json()
    event_id = str(uuid.uuid4())
    event = {
        "id": event_id,
        "event_type": "rrweb",
        "occurred_at": "2026-10-25T10:00:00Z",
        "payload": {"type": 2, "timestamp": 1792922400000, "data": {"node": {"text": "masked content"}}},
    }

    first = client.post(f"/api/v1/sessions/{session['id']}/events", json={"events": [event]})
    retry = client.post(f"/api/v1/sessions/{session['id']}/events", json={"events": [event]})
    assert first.status_code == 200
    assert first.json()["events_ingested"] == 1
    assert retry.status_code == 200
    assert retry.json()["events_ingested"] == 0

    replay = client.get(f"/api/v1/sessions/{session['id']}/replay").json()
    assert replay["total_events"] == 2
    rrweb = next(event for event in replay["events"] if event["event_type"] == "rrweb")
    assert rrweb["payload"]["type"] == 2
    assert rrweb["category"] == "replay"
    assert rrweb["occurred_at"].endswith("Z")

    listed = client.get("/api/v1/sessions").json()
    matching = next(item for item in listed if item["id"] == session["id"])
    assert matching["events_count"] == 2
    assert matching["user_agent"] is None


def test_session_event_size_limit_and_recording_opt_out(client):
    session = client.post("/api/v1/sessions", json={}).json()
    oversized = client.post(
        f"/api/v1/sessions/{session['id']}/events",
        json={"events": [{"event_type": "rrweb", "payload": {"text": "x" * 100_001}}]},
    )
    assert oversized.status_code == 413

    stopped = client.post(f"/api/v1/sessions/{session['id']}/stop")
    assert stopped.status_code == 204
    rejected = client.post(
        f"/api/v1/sessions/{session['id']}/events",
        json={"events": [{"event_type": "rrweb", "payload": {"type": 2}}]},
    )
    assert rejected.status_code == 409


def test_checkout_payment_is_linked_to_consented_browser_session(client):
    session = client.post("/api/v1/sessions", json={"visitor_ref": "anon_checkout_test"}).json()
    order = client.post(
        "/api/v1/paypal/orders",
        json={"amount": "9.99", "currency": "USD", "session_id": session["id"]},
    )
    assert order.status_code == 200
    payment = client.get(f"/api/v1/payments/{order.json()['payment_id']}")
    assert payment.status_code == 200
    assert payment.json()["session_id"] == session["id"]
    replay = client.get(f"/api/v1/sessions/{session['id']}/replay").json()
    assert replay["payment_id"] == payment.json()["id"]
    assert replay["payment_ids"] == [payment.json()["id"]]


def test_session_identity_envelope_is_idempotent_paginated_and_utc(client):
    session_id = str(uuid.uuid4())
    first = client.post("/api/v1/sessions", json={"session_id": session_id, "visitor_ref": "same-visit"})
    repeated = client.post("/api/v1/sessions", json={"session_id": session_id, "visitor_ref": "same-visit"})
    assert first.status_code == repeated.status_code == 200
    assert first.json()["id"] == repeated.json()["id"] == session_id
    assert first.json()["started_at"].endswith("Z")
    occurred_at = (datetime.fromisoformat(first.json()["started_at"].replace("Z", "+00:00")) + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")

    event_id = str(uuid.uuid4())
    event = {
        "id": event_id,
        "event_type": "network",
        "category": "network",
        "source": "browser",
        "tab_id": "tab-1",
        "segment_id": "segment-1",
        "occurred_at": occurred_at,
        "session_offset_ms": 1000,
        "route": "/api/v1/paypal/orders/:id/capture",
        "order_id": "19F21486TU6821704",
        "severity": "error",
        "trace_id": "request-123",
        "attributes": {"method": "POST", "status": 502, "duration_ms": 1400},
        "payload": {"name": "POST PayPal capture"},
    }
    posted = client.post(f"/api/v1/sessions/{session_id}/events", json={"events": [event]})
    retried = client.post(f"/api/v1/sessions/{session_id}/events", json={"events": [event]})
    assert posted.json()["events_ingested"] == 1
    assert retried.json()["events_ingested"] == 0

    first_page = client.get(f"/api/v1/sessions/{session_id}/replay?limit=1").json()
    assert first_page["total_events"] == 2
    assert first_page["returned_events"] == 1
    assert first_page["has_more"] is True
    second_page = client.get(f"/api/v1/sessions/{session_id}/replay?limit=1&offset=1").json()
    stored = second_page["events"][0]
    assert stored["tab_id"] == "tab-1"
    assert stored["segment_id"] == "segment-1"
    assert stored["session_offset_ms"] == 1000
    assert stored["occurred_at"].startswith(occurred_at.rstrip("Z"))
    assert stored["received_at"].endswith("Z")
    assert stored["order_id"] == "19F21486TU6821704"
    assert stored["attributes"]["duration_ms"] == 1400
    assert stored["payload"]["name"] == "POST PayPal capture"


def test_missing_timestamp_is_marked_unavailable_and_routes_are_sanitized(client):
    session = client.post("/api/v1/sessions", json={}).json()
    posted = client.post(f"/api/v1/sessions/{session['id']}/events", json={"events": [{
        "event_type": "route_changed",
        "category": "lifecycle",
        "route": "/api/v1/customers/private.person@example.test",
        "payload": {"name": "route_changed"},
    }]})
    assert posted.status_code == 200
    events = client.get(f"/api/v1/sessions/{session['id']}/replay").json()["events"]
    route_event = next(event for event in events if event["event_type"] == "route_changed")
    assert route_event["occurred_at"].endswith("Z")
    assert route_event["attributes"]["timestamp_source"] == "ingestion_fallback"
    assert route_event["session_offset_ms"] is None
    assert route_event["route"] == "/api/v1/customers/:id"
