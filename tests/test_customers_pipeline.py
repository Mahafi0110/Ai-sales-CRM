def make_customer(client, name="Acme Corp", **extra):
    return client.post("/api/customers", json={"name": name, "email": "hello@acme.com", **extra}).json()


def make_opp(client, customer_id, title="Big deal", value="1000", **extra):
    return client.post("/api/opportunities", json={"title": title, "customer_id": customer_id, "value": value, **extra})


def test_customer_crud_and_search(client, team, login_as):
    login_as("rep1@example.com")
    c = make_customer(client, industry="Retail")
    make_customer(client, name="Other Ltd", email="info@other.com")
    assert client.patch(f"/api/customers/{c['id']}", json={"phone": "555"}).json()["phone"] == "555"
    assert [x["name"] for x in client.get("/api/customers?q=acme").json()] == ["Acme Corp"]


def test_customer_history(client, team, login_as):
    login_as("rep1@example.com")
    c = make_customer(client)
    r = client.post(f"/api/customers/{c['id']}/interactions", json={"type": "call", "summary": "Discussed pricing"})
    assert r.status_code == 201
    client.post(f"/api/customers/{c['id']}/interactions", json={"type": "email", "summary": "Sent proposal"})
    history = client.get(f"/api/customers/{c['id']}/interactions").json()
    assert [h["summary"] for h in history] == ["Sent proposal", "Discussed pricing"]


def test_customer_isolation(client, team, login_as):
    login_as("rep1@example.com")
    c = make_customer(client)
    login_as("rep2@example.com")
    assert client.get("/api/customers").json() == []
    assert client.get(f"/api/customers/{c['id']}").status_code == 403
    assert client.post(f"/api/customers/{c['id']}/interactions", json={"summary": "sneaky"}).status_code == 403
    assert make_opp(client, c["id"]).status_code == 403


def test_pipeline_stages_and_summary(client, team, login_as):
    login_as("rep1@example.com")
    c = make_customer(client)
    a = make_opp(client, c["id"], "Deal A", "1000").json()
    b = make_opp(client, c["id"], "Deal B", "500").json()
    d = make_opp(client, c["id"], "Deal C", "200").json()
    assert client.post(f"/api/opportunities/{a['id']}/stage", json={"stage": "won"}).json()["closed_at"] is not None
    client.post(f"/api/opportunities/{b['id']}/stage", json={"stage": "lost"})
    client.post(f"/api/opportunities/{d['id']}/stage", json={"stage": "proposal"})
    s = client.get("/api/pipeline/summary").json()
    by_stage = {x["stage"]: x for x in s["stages"]}
    assert by_stage["won"]["count"] == 1 and float(by_stage["won"]["value"]) == 1000
    assert by_stage["proposal"]["count"] == 1
    assert s["open_count"] == 1 and float(s["open_value"]) == 200
    assert s["win_rate"] == 50.0
    # reopening clears the closed date
    reopened = client.post(f"/api/opportunities/{a['id']}/stage", json={"stage": "negotiation"}).json()
    assert reopened["closed_at"] is None


def test_win_rate_is_none_without_closed_deals(client, team, login_as):
    login_as("rep1@example.com")
    c = make_customer(client)
    make_opp(client, c["id"])
    assert client.get("/api/pipeline/summary").json()["win_rate"] is None


def test_negative_value_rejected(client, team, login_as):
    login_as("rep1@example.com")
    c = make_customer(client)
    assert make_opp(client, c["id"], value="-5").status_code == 422


def test_manager_sees_everyones_pipeline(client, team, login_as):
    login_as("rep1@example.com")
    c = make_customer(client)
    make_opp(client, c["id"], value="700")
    login_as("rep2@example.com")
    assert float(client.get("/api/pipeline/summary").json()["open_value"]) == 0
    login_as("manager@example.com")
    assert float(client.get("/api/pipeline/summary").json()["open_value"]) == 700
