from sqlalchemy import select

from app.models.audit import AuditLog
from app.models.user import Role


def login(client, email="admin@example.com", password="password123"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok"}


def test_login_success_sets_cookie_and_me_works(client, make_user):
    make_user()
    r = login(client)
    assert r.status_code == 200
    assert "access_token" in r.cookies
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "admin@example.com"


def test_login_wrong_password(client, make_user):
    make_user()
    assert login(client, password="wrong-password").status_code == 401


def test_me_requires_login(client):
    assert client.get("/api/auth/me").status_code == 401


def test_bearer_token_works(client, make_user):
    make_user()
    token = login(client).json()["access_token"]
    client.cookies.clear()
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_admin_can_create_user(client, make_user):
    make_user()
    login(client)
    r = client.post("/api/users", json={"email": "rep@example.com", "full_name": "Rep One",
                                        "password": "password123", "role": "sales_rep"})
    assert r.status_code == 201
    assert r.json()["role"] == "sales_rep"
    dup = client.post("/api/users", json={"email": "rep@example.com", "full_name": "Rep One",
                                          "password": "password123"})
    assert dup.status_code == 409


def test_sales_rep_cannot_create_or_list_users(client, make_user):
    make_user(email="rep@example.com", role=Role.SALES_REP)
    login(client, email="rep@example.com")
    body = {"email": "x@example.com", "full_name": "X", "password": "password123"}
    assert client.post("/api/users", json=body).status_code == 403
    assert client.get("/api/users").status_code == 403


def test_manager_can_list_users(client, make_user):
    make_user(email="boss@example.com", role=Role.MANAGER)
    login(client, email="boss@example.com")
    assert client.get("/api/users").status_code == 200


def test_audit_log_records_login_events(client, make_user, db_session):
    make_user()
    login(client, password="bad-password")
    login(client)
    actions = [a.action for a in db_session.scalars(select(AuditLog).order_by(AuditLog.id))]
    assert actions == ["login_failed", "login"]
