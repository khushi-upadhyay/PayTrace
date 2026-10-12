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
                        "password": "buyer_secret_password"
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
    assert replay_data["total_events"] == 3

    # Verify sensitive data is redacted
    input_ev = next(e for e in replay_data["events"] if e["event_type"] == "input")
    payload = input_ev["payload"]
    assert payload["card_number"] == "[REDACTED]"
    assert payload["cvv"] == "[REDACTED]"
    assert payload["password"] == "[REDACTED]"
