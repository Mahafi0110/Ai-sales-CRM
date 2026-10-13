def test_dashboard_redirects_when_logged_out(client):
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_login_page_renders(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert "Sign in" in r.text


def test_form_login_then_dashboard_then_logout(client, make_user):
    make_user(name="Ada Admin")
    r = client.post("/login", data={"email": "admin@example.com", "password": "password123"}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "Ada Admin" in page.text
    out = client.post("/logout", follow_redirects=False)
    assert out.status_code == 303
    client.cookies.clear()
    assert client.get("/dashboard", follow_redirects=False).status_code == 303


def test_form_login_wrong_password_shows_error(client, make_user):
    make_user()
    r = client.post("/login", data={"email": "admin@example.com", "password": "nope-nope"})
    assert r.status_code == 401
    assert "Incorrect email or password" in r.text
