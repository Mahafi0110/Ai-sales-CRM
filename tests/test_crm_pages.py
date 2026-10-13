import pytest

PAGES = ["/dashboard", "/leads", "/customers", "/pipeline", "/tasks"]


def page_login(client, email="rep1@example.com", password="password123"):
    client.cookies.clear()
    r = client.post("/login", data={"email": email, "password": password}, follow_redirects=False)
    assert r.status_code == 303


@pytest.mark.parametrize("path", PAGES + ["/leads/1", "/customers/1"])
def test_pages_redirect_to_login_when_logged_out(client, path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


@pytest.mark.parametrize("path", PAGES)
def test_pages_render_when_empty(client, team, path):
    page_login(client)
    assert client.get(path).status_code == 200


def test_create_lead_through_the_form(client, team):
    page_login(client)
    r = client.post("/leads", data={"name": "Form Lead", "email": "f@x.com", "company": "FormCo"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/leads/")
    assert "Form Lead" in client.get("/leads").text
    detail = client.get(r.headers["location"])
    assert detail.status_code == 200 and "FormCo" in detail.text


def test_form_validation_error_is_shown(client, team):
    page_login(client)
    r = client.post("/leads", data={"name": "Bad", "email": "not-an-email"}, follow_redirects=True)
    assert r.status_code == 200
    assert "Please check" in r.text and "email" in r.text


def test_edit_status_and_convert_flow(client, team):
    page_login(client)
    loc = client.post("/leads", data={"name": "Flow Lead"}, follow_redirects=False).headers["location"].split("?")[0]
    client.post(f"{loc}/edit", data={"name": "Flow Lead 2", "phone": "555"})
    client.post(f"{loc}/status", data={"status": "qualified"})
    assert "Flow Lead 2" in client.get(loc).text
    r = client.post(f"{loc}/convert", follow_redirects=False)
    assert r.headers["location"].startswith("/customers/")
    assert "Flow Lead 2" in client.get("/customers").text
    again = client.post(f"{loc}/convert", follow_redirects=True)
    assert "already converted" in again.text


def test_other_reps_get_a_friendly_403(client, team):
    page_login(client, "rep1@example.com")
    loc = client.post("/leads", data={"name": "Secret"}, follow_redirects=False).headers["location"].split("?")[0]
    page_login(client, "rep2@example.com")
    r = client.get(loc)
    assert r.status_code == 403 and "text/html" in r.headers["content-type"]
    assert "Secret" not in client.get("/leads").text


def test_missing_record_is_a_friendly_404(client, team):
    page_login(client)
    r = client.get("/leads/9999")
    assert r.status_code == 404 and "<html" in r.text


def test_manager_assigns_lead_from_the_page(client, team):
    page_login(client, "manager@example.com")
    loc = client.post("/leads", data={"name": "Assign Me"}, follow_redirects=False).headers["location"].split("?")[0]
    client.post(f"{loc}/assign", data={"owner_id": str(team["rep2"].id)})
    page_login(client, "rep2@example.com")
    assert "Assign Me" in client.get("/leads").text
    # a rep cannot use the assign form
    page_login(client, "rep1@example.com")
    loc1 = client.post("/leads", data={"name": "Mine"}, follow_redirects=False).headers["location"].split("?")[0]
    r = client.post(f"{loc1}/assign", data={"owner_id": str(team["rep2"].id)}, follow_redirects=True)
    assert "Only managers" in r.text


def test_customer_history_and_pipeline_pages(client, team):
    page_login(client)
    loc = client.post("/customers", data={"name": "Pipe Customer", "company": "PipeCo"}, follow_redirects=False).headers["location"].split("?")[0]
    cid = loc.rsplit("/", 1)[1]
    client.post(f"{loc}/interactions", data={"type": "call", "summary": "Talked budget"})
    assert "Talked budget" in client.get(loc).text
    client.post("/pipeline", data={"title": "Big Deal", "customer_id": cid, "value": "1500", "stage": "proposal"})
    board = client.get("/pipeline").text
    assert "Big Deal" in board and "$1,500" in board
    opp_id = client.get("/api/opportunities").json()[0]["id"]
    client.post(f"/opportunities/{opp_id}/stage", data={"stage": "won", "next": "/pipeline"})
    assert client.get("/api/opportunities").json()[0]["stage"] == "won"
    assert "Won value" in client.get("/pipeline").text


def test_pipeline_without_customers_explains_what_to_do(client, team):
    page_login(client)
    assert "Add a customer" in client.get("/pipeline").text


def test_tasks_flow_and_safe_redirect(client, team):
    page_login(client)
    r = client.post("/tasks", data={"title": "Ring Bob", "due_date": "2020-01-01", "next": "https://evil.example"},
                    follow_redirects=False)
    assert r.headers["location"].startswith("/tasks")  # outside links are ignored
    assert "Ring Bob" in client.get("/tasks?view=overdue").text
    task_id = client.get("/api/tasks").json()[0]["id"]
    client.post(f"/tasks/{task_id}/toggle", data={"next": "/tasks"})
    assert "Ring Bob" not in client.get("/tasks").text
    assert "Ring Bob" in client.get("/tasks?view=done").text


def test_dashboard_shows_real_numbers(client, team):
    page_login(client)
    client.post("/leads", data={"name": "Dash Lead"})
    html = client.get("/dashboard").text
    assert "Dash Lead" in html and "Open leads" in html


def test_api_errors_stay_json(client, team):
    page_login(client)
    r = client.get("/api/leads/9999")
    assert r.status_code == 404 and r.json()["detail"] == "Lead not found"
