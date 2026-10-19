import pytest
from app.models.crop import Crop


def test_list_crops_public(client):
    r = client.get("/api/crops")
    assert r.status_code == 200
    crops = r.json()
    assert isinstance(crops, list)
    assert len(crops) > 0


def test_filter_and_search_crops(client):
    # Search for known crop Mango
    r = client.get("/api/crops?search=Mango")
    assert r.status_code == 200
    items = r.json()
    assert all("mango" in item["crop_name"].lower() for item in items)

    # Filter with category
    r_cat = client.get("/api/crops?category=Fruits")
    assert r_cat.status_code == 200

    # Search with no matching results
    r_empty = client.get("/api/crops?search=NonExistentVegetableXYZ999")
    assert r_empty.status_code == 200
    assert len(r_empty.json()) == 0


def test_farmer_crud_crop(client, farmer_headers, db):
    # 1. Create crop
    payload = {
        "crop_name": "Organic Strawberries",
        "category": "Fruits",
        "quantity_available": 25.0,
        "unit": "KG",
        "farmer_price": 120.0,
        "description": "Sweet freshly picked organic strawberries.",
        "location": "Mahabaleshwar",
    }
    r_create = client.post("/api/crops", json=payload, headers=farmer_headers)
    assert r_create.status_code in (200, 201), r_create.text
    created = r_create.json()
    crop_id = created["crop_id"]
    assert created["crop_name"] == "Organic Strawberries"
    assert created["quantity_available"] == 25.0

    # 2. Get crop by ID
    r_get = client.get(f"/api/crops/{crop_id}")
    assert r_get.status_code == 200
    assert r_get.json()["crop_name"] == "Organic Strawberries"

    # 3. Update crop
    update_payload = {
        "farmer_price": 110.0,
        "quantity_available": 20.0,
        "description": "Updated price for fresh strawberries.",
    }
    # Farmer router or API route: let's test farmer update
    farmer_id = created["farmer_id"]
    from app.services.crop_service import CropService
    from app.schemas.crop import CropUpdate
    updated = CropService.update_crop(db, crop_id, farmer_id, CropUpdate(**update_payload))
    assert updated.farmer_price == 110.0
    assert updated.quantity_available == 20.0

    # 4. Attempt unauthorized update by another farmer (user id 50)
    with pytest.raises(PermissionError):
        CropService.update_crop(db, crop_id, 99999, CropUpdate(farmer_price=99.0))

    # 5. Delete crop
    CropService.delete_crop(db, crop_id, farmer_id)
    assert CropService.get_crop_by_id(db, crop_id) is None


def test_negative_stock_validation(client, farmer_headers):
    payload = {
        "crop_name": "Negative Stock Crop",
        "category": "Vegetables",
        "quantity_available": -10.0,
        "unit": "KG",
        "farmer_price": 50.0,
    }
    # Pydantic or service validation should reject negative stock
    r = client.post("/api/crops", json=payload, headers=farmer_headers)
    assert r.status_code in (400, 422)
