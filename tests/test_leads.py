def new_lead(client, **extra):
    body = {"name": "Priya Nair", "email": "priya@acme.com", "company": "Acme", "source": "website", **extra}
    return client.post("/api/leads", json=body)


def test_create_and_get_lead(client, team, login_as):
    login_as("rep1@example.com")
    r = new_lead(client)
    assert r.status_code == 201
    lead = r.json()
    assert lead["status"] == "new"
    assert lead["owner_id"] == team["rep1"].id
    assert client.get(f"/api/leads/{lead['id']}").json()["company"] == "Acme"


def test_requires_login(client):
    assert client.get("/api/leads").status_code == 401


def test_invalid_email_rejected(client, team, login_as):
    login_as("rep1@example.com")
    assert new_lead(client, email="not-an-email").status_code == 422


def test_search_and_status_filter(client, team, login_as):
    login_as("rep1@example.com")
    new_lead(client, name="Alpha One", company="Zeta Corp", email="a@z.com")
    second = new_lead(client, name="Beta Two", company="Omega Ltd", email="b@o.com").json()
    client.post(f"/api/leads/{second['id']}/status", json={"status": "contacted"})
    assert [l["name"] for l in client.get("/api/leads?q=zeta").json()] == ["Alpha One"]
    assert [l["name"] for l in client.get("/api/leads?status=contacted").json()] == ["Beta Two"]
    assert len(client.get("/api/leads").json()) == 2


def test_update_lead_changes_only_sent_fields(client, team, login_as):
    login_as("rep1@example.com")
    lead = new_lead(client).json()
    r = client.patch(f"/api/leads/{lead['id']}", json={"phone": "555-0100"})
    assert r.status_code == 200
    assert r.json()["phone"] == "555-0100"
    assert r.json()["company"] == "Acme"


def test_reps_only_see_their_own_leads(client, team, login_as):
    login_as("rep1@example.com")
    lead = new_lead(client).json()
    login_as("rep2@example.com")
    assert client.get("/api/leads").json() == []
    assert client.get(f"/api/leads/{lead['id']}").status_code == 403
    assert client.patch(f"/api/leads/{lead['id']}", json={"name": "Hacked"}).status_code == 403
    login_as("manager@example.com")
    assert len(client.get("/api/leads").json()) == 1


def test_only_managers_can_assign(client, team, login_as):
    login_as("rep1@example.com")
    lead = new_lead(client).json()
    body = {"owner_id": team["rep2"].id}
    assert client.post(f"/api/leads/{lead['id']}/assign", json=body).status_code == 403
    login_as("manager@example.com")
    r = client.post(f"/api/leads/{lead['id']}/assign", json=body)
    assert r.status_code == 200
    assert r.json()["owner_id"] == team["rep2"].id
    login_as("rep2@example.com")
    assert len(client.get("/api/leads").json()) == 1


def test_manager_can_pick_owner_on_create(client, team, login_as):
    login_as("manager@example.com")
    lead = new_lead(client, owner_id=team["rep1"].id).json()
    assert lead["owner_id"] == team["rep1"].id


def test_rep_cannot_pick_another_owner_on_create(client, team, login_as):
    login_as("rep1@example.com")
    lead = new_lead(client, owner_id=team["rep2"].id).json()
    assert lead["owner_id"] == team["rep1"].id


def test_convert_lead_to_customer(client, team, login_as):
    login_as("rep1@example.com")
    lead = new_lead(client).json()
    r = client.post(f"/api/leads/{lead['id']}/convert")
    assert r.status_code == 201
    customer = r.json()
    assert customer["name"] == "Priya Nair"
    updated = client.get(f"/api/leads/{lead['id']}").json()
    assert updated["status"] == "converted"
    assert updated["customer_id"] == customer["id"]
    history = client.get(f"/api/customers/{customer['id']}/interactions").json()
    assert "Converted from lead" in history[0]["summary"]
    assert client.post(f"/api/leads/{lead['id']}/convert").status_code == 409


def test_cannot_set_converted_status_by_hand(client, team, login_as):
    login_as("rep1@example.com")
    lead = new_lead(client).json()
    assert client.post(f"/api/leads/{lead['id']}/status", json={"status": "converted"}).status_code == 400
