import pytest
from app.models.user import User


def test_admin_dashboard(client, admin_headers):
    r = client.get("/admin/dashboard", headers=admin_headers)
    assert r.status_code == 200
    assert "DirectHarvest" in r.text
    assert "Admin" in r.text or "Dashboard" in r.text


def test_admin_manage_pages(client, admin_headers):
    for endpoint in ["/admin/users", "/admin/crops", "/admin/orders", "/admin/reports", "/admin/notifications"]:
        r = client.get(endpoint, headers=admin_headers)
        assert r.status_code == 200, f"Failed at {endpoint}: {r.status_code}"


def test_admin_excel_export_endpoints(client, admin_headers):
    # Test users export
    r_users = client.get("/admin/reports/export/users", headers=admin_headers)
    assert r_users.status_code == 200
    assert "users.xlsx" in r_users.headers.get("Content-Disposition", "")
    assert len(r_users.content) > 1000

    # Test crops export
    r_crops = client.get("/admin/reports/export/crops", headers=admin_headers)
    assert r_crops.status_code == 200
    assert "farmer_crops.xlsx" in r_crops.headers.get("Content-Disposition", "")
    assert len(r_crops.content) > 1000

    # Test orders export
    r_orders = client.get("/admin/reports/export/orders", headers=admin_headers)
    assert r_orders.status_code == 200
    assert "orders.xlsx" in r_orders.headers.get("Content-Disposition", "")
    assert len(r_orders.content) > 1000


def test_admin_toggle_user_status(client, admin_headers, db):
    target_user = db.query(User).filter(User.role == "consumer").first()
    assert target_user is not None
    orig_status = target_user.status

    # Toggle status
    r_toggle = client.get(f"/admin/users/{target_user.id}/toggle-status", headers=admin_headers, follow_redirects=False)
    assert r_toggle.status_code in (200, 302)

    db.commit()
    db.refresh(target_user)
    expected_new = "Inactive" if orig_status == "Active" else "Active"
    assert target_user.status == expected_new

    # Toggle back
    r_toggle_back = client.get(f"/admin/users/{target_user.id}/toggle-status", headers=admin_headers, follow_redirects=False)
    assert r_toggle_back.status_code in (200, 302)
    db.commit()
    db.refresh(target_user)
    assert target_user.status == orig_status


def test_ai_settings_and_connection_normalization(client, admin_headers):
    from app.services.ai_service import AIService
    
    # Test normalization
    assert AIService.normalize_ai_url("https://platform.openai.com/") == "https://api.openai.com/v1"
    assert AIService.normalize_ai_url("https://platform.openai.com") == "https://api.openai.com/v1"
    assert AIService.normalize_ai_url("https://api.openai.com") == "https://api.openai.com/v1"
    assert AIService.normalize_ai_url("https://api.openai.com/v1") == "https://api.openai.com/v1"

    # Test test-connection endpoint
    r = client.post(
        "/admin/ai-settings/test-connection",
        json={"base_url": "https://platform.openai.com/", "api_key": "sk-dummy-test-key-12345"},
        headers=admin_headers
    )
    assert r.status_code == 200
    data = r.json()
    assert "success" in data
    assert "message" in data
    assert data["normalized_url"] == "https://api.openai.com/v1"

    # Test saving AI configuration
    r_save = client.post(
        "/admin/ai-settings",
        data={
            "base_url": "https://platform.openai.com/",
            "api_key": "sk-new-saved-key-8888",
            "model": "gpt-4o-mini",
            "ai_enabled": "true"
        },
        headers=admin_headers,
        follow_redirects=False
    )
    assert r_save.status_code == 302
    assert "/admin/ai-settings" in r_save.headers.get("location", "")


def test_admin_crop_approve_reject_delete(client, admin_headers):
    from app.database import SessionLocal
    from app.models.crop import Crop
    from app.models.user import User
    db = SessionLocal()
    farmer = db.query(User).filter(User.role == "farmer", User.status == "Active").first()
    assert farmer is not None
    crop = Crop(farmer_id=farmer.id, crop_name="Admin Test Crop", category="Vegetables", quantity_available=20.0, farmer_price=25.0, status="available")
    db.add(crop)
    db.commit()
    cid = crop.crop_id
    db.close()

    # Test reject
    r_reject = client.get(f"/admin/reject-crop/{cid}", headers=admin_headers, follow_redirects=False)
    assert r_reject.status_code == 302
    assert "success" in r_reject.headers.get("location", "")

    db_check = SessionLocal()
    assert db_check.query(Crop).filter(Crop.crop_id == cid).first().status == "rejected"
    db_check.close()

    # Test approve
    r_approve = client.get(f"/admin/approve-crop/{cid}", headers=admin_headers, follow_redirects=False)
    assert r_approve.status_code == 302
    assert "success" in r_approve.headers.get("location", "")

    db_check2 = SessionLocal()
    assert db_check2.query(Crop).filter(Crop.crop_id == cid).first().status == "available"
    db_check2.close()

    # Test delete
    r_delete = client.get(f"/admin/delete-crop/{cid}", headers=admin_headers, follow_redirects=False)
    assert r_delete.status_code == 302
    assert "success" in r_delete.headers.get("location", "")

    db_check3 = SessionLocal()
    assert db_check3.query(Crop).filter(Crop.crop_id == cid).first() is None
    db_check3.close()


