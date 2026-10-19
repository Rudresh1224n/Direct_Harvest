import pytest
from app.utils.email_validator import validate_authentic_email
from app.models.user import User


def test_email_authenticity_validator():
    # Authentic emails
    assert validate_authentic_email("valid.farmer@gmail.com") == "valid.farmer@gmail.com"
    assert validate_authentic_email("business@microsoft.com") == "business@microsoft.com"

    # Disposable domains rejected in production mode
    with pytest.raises(ValueError) as exc:
        validate_authentic_email("fakeuser@asdf.com", allow_test_domains=False)
    assert "disposable or dummy" in str(exc.value).lower()

    with pytest.raises(ValueError) as exc:
        validate_authentic_email("user@tempmail.com", allow_test_domains=False)
    assert "disposable or dummy" in str(exc.value).lower()

    # Invalid syntax
    with pytest.raises(ValueError):
        validate_authentic_email("notanemail")

    # Nonexistent domain DNS lookup
    with pytest.raises(ValueError) as exc:
        validate_authentic_email("someone@definitelynotarealdomain1234567xyz.com", allow_test_domains=False)
    assert "could not be verified" in str(exc.value).lower() or "exist" in str(exc.value).lower()


def test_farmer_new_routes(client, farmer_headers):
    # 1. Farmer Inbox
    r_inbox = client.get("/farmer/inbox", headers=farmer_headers)
    assert r_inbox.status_code == 200
    assert "Farmer Communications Inbox" in r_inbox.text or "WhatsApp Dispatch Logs" in r_inbox.text

    # 2. Farmer Revenue History alias (/farmer/revenue)
    r_rev = client.get("/farmer/revenue", headers=farmer_headers)
    assert r_rev.status_code == 200
    assert "Farmer Revenue History Ledger" in r_rev.text or "Revenue History" in r_rev.text

    # 3. Farmer Wallet Page & Action
    r_wallet = client.get("/farmer/wallet", headers=farmer_headers)
    assert r_wallet.status_code == 200
    assert "Farmer Earnings Wallet" in r_wallet.text

    r_withdraw = client.post("/farmer/wallet", data={"amount": 10.0}, headers=farmer_headers, follow_redirects=False)
    assert r_withdraw.status_code in (200, 302, 303)

    # 4. Farmer Trust Score
    r_trust = client.get("/farmer/trust-score", headers=farmer_headers)
    assert r_trust.status_code == 200
    assert "Trust Score" in r_trust.text


def test_delivery_inbox_route(client, delivery_headers):
    r_inbox = client.get("/delivery/inbox", headers=delivery_headers)
    assert r_inbox.status_code == 200
    assert "Delivery Communications Inbox" in r_inbox.text or "WhatsApp Dispatch Logs" in r_inbox.text


def test_forgot_password_otp_lifecycle(client, db):
    from app.utils.security import hash_password
    test_email = "otp_tester_lifecycle@gmail.com"
    test_phone = "9900112233"

    # Clean existing if any
    existing = db.query(User).filter(User.email == test_email).first()
    if existing:
        db.delete(existing)
        db.commit()

    test_user = User(
        full_name="Dedicated OTP Tester",
        email=test_email,
        phone=test_phone,
        password_hash=hash_password("InitialPassword123!"),
        role="consumer",
        status="Active",
    )
    db.add(test_user)
    db.commit()
    db.refresh(test_user)

    phone = test_phone

    try:
        # 1. Access forgot-password page
        r_page = client.get("/forgot-password")
        assert r_page.status_code == 200
        assert "Forgot Password" in r_page.text

        # 2. Send OTP
        r_send = client.post("/api/send-otp", json={"phone": phone})
        assert r_send.status_code == 200
        send_data = r_send.json()
        assert send_data["success"] is True
        assert "otp_preview" in send_data
        otp_code = send_data["otp_preview"]
        assert otp_code is not None

        # 3. Verify OTP with incorrect code
        r_bad = client.post("/api/verify-otp", json={"phone": phone, "otp": "000000"})
        assert r_bad.status_code == 400
        assert r_bad.json()["success"] is False

        # 4. Verify OTP with correct code
        r_ok = client.post("/api/verify-otp", json={"phone": phone, "otp": otp_code})
        assert r_ok.status_code == 200
        assert r_ok.json()["success"] is True

        # 5. Reset password with mismatching confirmation
        r_mismatch = client.post("/api/reset-password", json={
            "phone": phone,
            "password": "NewSecretPassword123!",
            "confirm_password": "MismatchingPassword123!"
        })
        assert r_mismatch.status_code == 400
        assert "do not match" in r_mismatch.json()["message"].lower()

        # 6. Reset password successfully
        r_reset = client.post("/api/reset-password", json={
            "phone": phone,
            "password": "NewSecretPassword123!",
            "confirm_password": "NewSecretPassword123!"
        })
        assert r_reset.status_code == 200
        assert r_reset.json()["success"] is True

        # 7. Login with newly updated password
        r_login = client.post("/api/auth/login", json={
            "email": test_email,
            "password": "NewSecretPassword123!"
        })
        assert r_login.status_code == 200
        assert "access_token" in r_login.json()
    finally:
        # Cleanup
        db.delete(test_user)
        db.commit()


def test_order_whatsapp_recipient_customer_and_farmer(client, db, consumer_headers, test_setup):
    from app.models.crop import Crop
    from app.services.order_service import OrderService

    consumer_id = test_setup["consumer"]
    farmer_id = test_setup["farmer"]

    farmer = db.query(User).filter(User.id == farmer_id).first()
    farmer.phone = "9822334455"
    db.commit()

    crop = db.query(Crop).filter(Crop.farmer_id == farmer_id, Crop.quantity_available > 5.0).first()
    assert crop is not None

    # Clear cart and add crop
    OrderService.clear_cart(db, consumer_id)
    OrderService.add_to_cart(db, consumer_id, crop.crop_id, 1.0)

    # Place order with customer's chosen checkout phone
    checkout_phone = "9899887766"
    resp = client.post("/place-order", data={
        "name": "Jane Consumer",
        "phone": checkout_phone,
        "address": "42 Farm View Avenue",
        "city": "Indore",
        "state": "MP",
        "pincode": "452001",
        "payment_method": "Cash on Delivery",
    }, headers=consumer_headers, follow_redirects=False)

    assert resp.status_code == 302
    redirect_url = resp.headers["location"]
    assert f"phone={checkout_phone}" in redirect_url

    # Check order confirmation page
    success_resp = client.get(redirect_url, headers=consumer_headers)
    assert success_resp.status_code == 200
    html = success_resp.text

    # 1. Customer receipt must target customer's phone
    assert "api.whatsapp.com/send?phone=919899887766" in html
    # 2. Farmer alert must target farmer's phone
    assert "api.whatsapp.com/send?phone=919822334455" in html
    # 3. Must NOT send order message to admin's phone
    assert "api.whatsapp.com/send?phone=919691793254" not in html
    assert "Admin: 9691793254" not in html

