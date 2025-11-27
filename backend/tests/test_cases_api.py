def test_case_actions_and_audit(client):
    refresh_resp = client.post("/api/alerts/refresh", json={})
    assert refresh_resp.status_code == 200

    alerts_resp = client.get("/api/alerts")
    alerts = alerts_resp.get_json()
    assert alerts, "Expected at least one alert after refresh"

    alert_id = alerts[0]["id"]
    alert_detail_resp = client.get(f"/api/alerts/{alert_id}")
    assert alert_detail_resp.status_code == 200
    case = alert_detail_resp.get_json().get("case")
    assert case and case.get("id")
    case_id = case["id"]

    action_resp = client.post(
        f"/api/cases/{case_id}/actions",
        json={"action": "ESCALATE", "notes": "Escalating to L2 team"},
    )
    assert action_resp.status_code == 200
    updated_case = action_resp.get_json().get("case")
    assert updated_case["status"] == "IN_PROGRESS"

    audit_resp = client.get(f"/api/cases/{case_id}/audit")
    assert audit_resp.status_code == 200
    actions = audit_resp.get_json()
    assert any(a.get("action") == "ESCALATE" for a in actions)
