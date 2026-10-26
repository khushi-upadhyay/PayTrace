def test_shelfswipe_deck_seeds_deterministic_demo_catalog(client):
    first = client.get(
        "/api/v1/shelfswipe/deck",
        params={"query": "birthday gift under $40", "buyer_ref": "test-buyer"},
    )
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["total_matches"] >= 5
    assert first_data["deck"][0]["id"]
    assert first_data["query"] == "birthday gift under $40"

    second = client.get("/api/v1/shelfswipe/deck", params={"buyer_ref": "test-buyer"})
    assert second.status_code == 200
    assert {item["id"] for item in first_data["deck"]} == {
        item["id"] for item in second.json()["deck"]
    }


def test_shelfswipe_records_valid_swipe(client):
    deck = client.get("/api/v1/shelfswipe/deck").json()["deck"]
    response = client.post(
        "/api/v1/shelfswipe/swipe",
        json={"buyer_ref": "test-buyer", "product_id": deck[0]["id"], "direction": "right"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "recorded"


def test_shelfswipe_search_can_return_an_empty_deck(client):
    response = client.get(
        "/api/v1/shelfswipe/deck",
        params={"query": "nonexistent-material-xyz", "buyer_ref": "test-buyer"},
    )
    assert response.status_code == 200
    assert response.json()["deck"] == []
    assert response.json()["total_matches"] == 0
