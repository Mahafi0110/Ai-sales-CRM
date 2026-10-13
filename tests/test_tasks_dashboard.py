from datetime import date, timedelta


def make_task(client, title="Call back", due=None, **extra):
    body = {"title": title, **extra}
    if due:
        body["due_date"] = due.isoformat()
    return client.post("/api/tasks", json=body)


def test_task_lifecycle(client, team, login_as):
    login_as("rep1@example.com")
    t = make_task(client).json()
    assert t["status"] == "open" and t["assigned_to_id"] == team["rep1"].id
    assert client.post(f"/api/tasks/{t['id']}/complete").json()["status"] == "done"
    assert client.get("/api/tasks?status=open").json() == []
    assert client.post(f"/api/tasks/{t['id']}/reopen").json()["status"] == "open"


def test_overdue_filter(client, team, login_as):
    login_as("rep1@example.com")
    make_task(client, "Late", date.today() - timedelta(days=2))
    make_task(client, "Soon", date.today() + timedelta(days=2))
    assert [t["title"] for t in client.get("/api/tasks?overdue=true").json()] == ["Late"]


def test_tasks_ordered_by_due_date(client, team, login_as):
    login_as("rep1@example.com")
    make_task(client, "No date")
    make_task(client, "Later", date.today() + timedelta(days=5))
    make_task(client, "Sooner", date.today() + timedelta(days=1))
    assert [t["title"] for t in client.get("/api/tasks").json()] == ["Sooner", "Later", "No date"]


def test_task_privacy_and_assignment(client, team, login_as):
    login_as("rep1@example.com")
    t = make_task(client, assigned_to_id=team["rep2"].id).json()
    assert t["assigned_to_id"] == team["rep1"].id  # reps cannot assign to others
    login_as("rep2@example.com")
    assert client.get("/api/tasks").json() == []
    assert client.post(f"/api/tasks/{t['id']}/complete").status_code == 403
    login_as("manager@example.com")
    assigned = make_task(client, "From boss", assigned_to_id=team["rep2"].id).json()
    assert assigned["assigned_to_id"] == team["rep2"].id
    login_as("rep2@example.com")
    assert [x["title"] for x in client.get("/api/tasks").json()] == ["From boss"]


def test_task_cannot_link_to_someone_elses_lead(client, team, login_as):
    login_as("rep1@example.com")
    lead = client.post("/api/leads", json={"name": "Private Lead"}).json()
    login_as("rep2@example.com")
    assert make_task(client, lead_id=lead["id"]).status_code == 403


def test_dashboard_numbers(client, team, login_as):
    login_as("rep1@example.com")
    for name in ("L1", "L2", "L3"):
        client.post("/api/leads", json={"name": name})
    leads = client.get("/api/leads").json()
    client.post(f"/api/leads/{leads[0]['id']}/status", json={"status": "unqualified"})
    client.post(f"/api/leads/{leads[1]['id']}/convert")
    c = client.post("/api/customers", json={"name": "Cust"}).json()
    client.post("/api/opportunities", json={"title": "Deal", "customer_id": c["id"], "value": "250.50"})
    make_task(client, "Overdue", date.today() - timedelta(days=1))
    make_task(client, "Fine", date.today() + timedelta(days=3))
    d = client.get("/api/dashboard").json()
    assert d["open_leads"] == 1
    assert d["customers"] == 2  # one created directly, one from conversion
    assert d["open_opportunities"] == 1 and float(d["pipeline_value"]) == 250.5
    assert d["open_tasks"] == 2 and d["overdue_tasks"] == 1
    assert d["leads_by_status"]["unqualified"] == 1
    assert len(d["recent_leads"]) == 3
    assert d["upcoming_tasks"][0]["title"] == "Overdue"


def test_dashboard_is_scoped_for_reps(client, team, login_as):
    login_as("rep1@example.com")
    client.post("/api/leads", json={"name": "Mine"})
    login_as("rep2@example.com")
    assert client.get("/api/dashboard").json()["open_leads"] == 0
    login_as("manager@example.com")
    assert client.get("/api/dashboard").json()["open_leads"] == 1
