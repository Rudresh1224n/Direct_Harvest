import openpyxl
import pytest
from app.services.excel_service import ExcelService


def test_export_users_excel(db):
    stream = ExcelService.export_users(db)
    assert stream is not None
    wb = openpyxl.load_workbook(stream)
    assert "Registered Users" in wb.sheetnames
    ws = wb["Registered Users"]
    headers = [cell.value for cell in ws[1]]
    assert "User ID" in headers
    assert "Email" in headers
    # Verify passwords/hashes are NOT in headers or content
    assert "password" not in [str(h).lower() for h in headers]
    assert ws.max_row >= 2  # At least headers + existing users


def test_export_crops_excel(db):
    from app.models.crop import Crop
    from app.models.user import User
    farmer = db.query(User).filter(User.role == "farmer").first()
    if farmer and db.query(Crop).count() == 0:
        db.add(Crop(
            farmer_id=farmer.id,
            crop_name="Fresh Tomatoes",
            category="Vegetables",
            quantity_available=100.0,
            unit="KG",
            farmer_price=40.0,
            status="available",
            location="Indore",
            quality_grade="Grade A",
            freshness_score=95.0,
        ))
        db.commit()

    stream = ExcelService.export_crops(db)
    assert stream is not None
    wb = openpyxl.load_workbook(stream)
    assert "Farmer Crops" in wb.sheetnames
    ws = wb["Farmer Crops"]
    headers = [cell.value for cell in ws[1]]
    assert "Crop ID" in headers
    assert "Crop Name" in headers
    assert "Available Quantity" in headers
    assert ws.max_row >= 2


def test_export_orders_excel(db):
    stream = ExcelService.export_orders(db)
    assert stream is not None
    wb = openpyxl.load_workbook(stream)
    assert "Platform Orders" in wb.sheetnames
    ws = wb["Platform Orders"]
    headers = [cell.value for cell in ws[1]]
    assert "Order ID" in headers
    assert "Order Status" in headers
    assert "Total Amount (INR)" in headers


def test_credentials_excel_sync_and_bytes(db):
    from app.services.excel_credential_service import ExcelCredentialService, HEADERS
    from app.models.user import User
    from app.utils.security import verify_password
    import io

    # 1. Test in-memory byte sync with updated password and name
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADERS)

    # Use existing admin user
    admin = db.query(User).filter(User.email == "admin@directharvest.com").first()
    assert admin is not None

    # Append all existing users so absent purge is not triggered for valid test users
    for u in db.query(User).all():
        if u.id == admin.id:
            ws.append([
                admin.id,
                "Super Administrator Updated",
                admin.email,
                admin.phone,
                "adminNewPass123!",
                admin.role,
                admin.status,
                admin.address,
                "",
                "",
                "",
                "",
            ])
        else:
            ws.append([
                u.id,
                u.full_name or "",
                u.email,
                u.phone or "",
                "[Encrypted]",
                u.role,
                u.status,
                u.address or "",
                "",
                "",
                "",
                "",
            ])

    stream = io.BytesIO()
    wb.save(stream)
    content = stream.getvalue()

    result = ExcelCredentialService.sync_bytes_to_db(content, db)
    assert result["success"] is True
    assert result["updated"] >= 1

    # Verify database was updated
    db.refresh(admin)
    assert admin.full_name == "Super Administrator Updated"
    assert verify_password("adminNewPass123!", admin.password_hash) is True

    # Restore admin credentials cleanly
    admin.full_name = "Administrator"
    from app.utils.security import hash_password
    admin.password_hash = hash_password("admin123")
    db.commit()


def test_credentials_excel_delete_sync(db):
    from app.services.excel_credential_service import ExcelCredentialService, HEADERS
    from app.models.user import User
    from app.utils.security import hash_password
    import io

    # Create a temporary test user in DB
    temp_user = User(
        full_name="Temp To Delete",
        email="delete_me_test@example.com",
        phone="9999888877",
        password_hash=hash_password("test1234"),
        role="consumer",
        status="Active",
    )
    db.add(temp_user)
    db.commit()
    db.refresh(temp_user)
    temp_id = temp_user.id
    assert db.query(User).filter(User.id == temp_id).first() is not None

    # Construct Excel workbook with all existing DB users EXCEPT temp_user
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADERS)

    for u in db.query(User).all():
        if u.id == temp_id:
            continue
        ws.append([
            u.id,
            u.full_name or "",
            u.email,
            u.phone or "",
            "[Encrypted]",
            u.role,
            u.status,
            u.address or "",
            "",
            "",
            "",
            "",
        ])

    stream = io.BytesIO()
    wb.save(stream)
    content = stream.getvalue()

    # Sync into DB
    result = ExcelCredentialService.sync_bytes_to_db(content, db)
    assert result["success"] is True
    assert result["deleted"] == 1

    # Verify temp user was deleted from DB
    assert db.query(User).filter(User.id == temp_id).first() is None
    # Verify admin was NOT deleted
    assert db.query(User).filter(User.email == "admin@directharvest.com").first() is not None


