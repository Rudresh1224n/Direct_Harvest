import uuid
import pytest
from app.models.user import User


def test_health_endpoints(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

    r_api = client.get("/api/health")
    assert r_api.status_code == 200
    assert r_api.json()["database"] == "connected"


def test_user_registration_and_duplicate(client, db):
    unique_email = f"test_user_{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "full_name": "Test Consumer",
        "email": unique_email,
        "password": "Password@123",
        "role": "consumer",
        "phone": "9876543210",
        "address": "123 Green Valley",
        "state": "Maharashtra",
        "district": "Pune",
        "pincode": "411001",
    }
    r = client.post("/api/auth/register", json=payload)
    assert r.status_code in (200, 201), r.text
    data = r.json()
    assert data["email"] == unique_email
    assert data["role"] == "consumer"

    # Now login with registered credentials to verify token generation
    r_login = client.post(
        "/api/auth/login",
        json={"email": unique_email, "password": "Password@123"},
    )
    assert r_login.status_code == 200
    assert "access_token" in r_login.json()

    # Attempt duplicate registration with the same email
    r_dup = client.post("/api/auth/register", json=payload)
    assert r_dup.status_code == 400
    assert "already registered" in r_dup.text.lower() or "exists" in r_dup.text.lower()


def test_user_login_success_and_failure(client, test_setup):
    email = test_setup["consumer_email"]
    login_success = client.post(
        "/api/auth/login",
        json={"email": email, "password": "password123"},
    )
    assert login_success.status_code == 200
    res = login_success.json()
    assert "token" in res or "access_token" in res

    # Bad password
    login_fail = client.post(
        "/api/auth/login",
        json={"email": email, "password": "WrongPassword!"},
    )
    assert login_fail.status_code == 401


def test_role_authorization_and_guards(client, consumer_headers, farmer_headers, delivery_headers, admin_headers):
    # Consumer should be forbidden from accessing admin API
    r_admin_forbidden = client.get("/admin/users", headers=consumer_headers, follow_redirects=False)
    # Either 403 or 307 redirect away
    assert r_admin_forbidden.status_code in (307, 403)

    # Farmer should not access admin endpoints
    r_farmer_admin = client.get("/admin/dashboard", headers=farmer_headers, follow_redirects=False)
    assert r_farmer_admin.status_code in (307, 403)

    # Delivery partner should not access farmer crop management
    r_del_farmer = client.get("/farmer/dashboard", headers=delivery_headers, follow_redirects=False)
    assert r_del_farmer.status_code in (307, 403)

    # Admin should successfully access admin dashboard
    r_admin_ok = client.get("/admin/dashboard", headers=admin_headers)
    assert r_admin_ok.status_code == 200


def test_admin_login_logout_cycle(client, db):
    # 1. Admin login with valid credentials
    r_login = client.post(
        "/login",
        data={"email": "admin@directharvest.com", "password": "admin123"},
        follow_redirects=False,
    )
    assert r_login.status_code == 303
    assert r_login.headers["location"] == "/admin/dashboard"
    assert "access_token" in r_login.cookies

    # 2. Access admin dashboard with cookie
    client.cookies.set("access_token", r_login.cookies["access_token"])
    r_dash = client.get("/admin/dashboard")
    assert r_dash.status_code == 200

    # 3. Logout
    r_logout = client.post("/logout", follow_redirects=False) if False else client.get("/logout", follow_redirects=False)
    assert r_logout.status_code == 303
    assert r_logout.headers["location"] == "/login"

    # 4. Attempt login with bogus navigate labs URL (reproducing user screenshot)
    r_bogus = client.post(
        "/login",
        data={"email": "https://apidev.navigatelabsai.com", "password": "some_random_key_6R5Q"},
        follow_redirects=False,
    )
    assert r_bogus.status_code == 401
    assert "Invalid email or password." in r_bogus.text

    # 5. Subsequent admin login must still succeed flawlessly
    r_relogin = client.post(
        "/login",
        data={"email": "admin@directharvest.com", "password": "admin123"},
        follow_redirects=False,
    )
    assert r_relogin.status_code == 303
    assert r_relogin.headers["location"] == "/admin/dashboard"

    # Always clear test client cookies to keep subsequent tests isolated
    client.cookies.clear()

