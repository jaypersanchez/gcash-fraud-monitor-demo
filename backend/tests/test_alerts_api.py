def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.get_json().get("status") == "ok"


def test_refresh_and_list_alerts(client):
    refresh_resp = client.post("/api/alerts/refresh", json={})
    assert refresh_resp.status_code == 200
    generated = refresh_resp.get_json().get("generated_alerts")
    assert generated >= 1

    list_resp = client.get("/api/alerts")
    assert list_resp.status_code == 200
    alerts = list_resp.get_json()
    assert isinstance(alerts, list)
    assert len(alerts) >= generated
