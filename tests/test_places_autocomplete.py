import pytest
from app.services.places_service import PlacesService


def test_places_service_local_matching():
    # 1. Search for MG Road
    res_mg = PlacesService.search_places("mg road")
    assert len(res_mg) > 0
    assert any("MG Road" in item["street"] for item in res_mg)

    # 2. Search for Vijay Nagar
    res_vijay = PlacesService.search_places("vijay nagar")
    assert len(res_vijay) > 0
    assert any("Vijay Nagar" in item["area"] or "Vijay Nagar" in item["street"] for item in res_vijay)

    # 3. Search for Arera Colony Bhopal
    res_arera = PlacesService.search_places("arera")
    assert len(res_arera) > 0
    assert any("Bhopal" in item["city"] for item in res_arera)

    # 4. Search for Scheme
    res_scheme = PlacesService.search_places("scheme 54")
    assert len(res_scheme) > 0
    assert "Scheme No 54" in res_scheme[0]["street"]


def test_api_places_autocomplete_endpoint(client):
    # Test API endpoint
    r = client.get("/api/places/autocomplete?q=palasia")
    assert r.status_code == 200
    data = r.json()
    assert data["success"] is True
    assert data["count"] > 0
    assert any("Palasia" in s["formatted"] for s in data["suggestions"])


def test_registration_with_detailed_address(client, db):
    test_email = "detailed_address_user@gmail.com"
    from app.models.user import User, ConsumerProfile
    existing = db.query(User).filter(User.email == test_email).first()
    if existing:
        db.query(ConsumerProfile).filter(ConsumerProfile.consumer_id == existing.id).delete()
        db.delete(existing)
        db.commit()
    r = client.post(
        "/register",
        data={
            "full_name": "Detailed Address Tester",
            "email": test_email,
            "password": "Password123!",
            "confirm_password": "Password123!",
            "phone": "9876543219",
            "role": "consumer",
            "address": "Flat 402, Block C, Silver Heights, MG Road, Near Apollo Hospital, Indore, Madhya Pradesh - 452001",
            "city": "Indore",
            "state": "Madhya Pradesh",
            "pincode": "452001"
        },
        follow_redirects=False
    )
    assert r.status_code in (200, 302, 303)

    from app.models.user import User
    db.rollback()
    user = db.query(User).filter(User.email == test_email).first()
    assert user is not None
    assert "Flat 402" in user.address
    assert "Silver Heights" in user.address
    assert "Indore" in user.address
