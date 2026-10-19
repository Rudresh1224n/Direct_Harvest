import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app.models.user import User, FarmerProfile, ConsumerProfile, DeliveryPartnerProfile
from app.models.crop import Crop
from app.models.wallet import Wallet
from app.utils.security import create_access_token, hash_password
from app.utils.constants import ROLE_ADMIN, ROLE_FARMER, ROLE_CONSUMER, ROLE_DELIVERY
STATUS_APPROVED = "Approved"


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="function")
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _get_or_create_user(db, email, role, full_name, phone):
    user = db.query(User).filter(User.role == role, User.status == "Active").first()
    if not user:
        user = db.query(User).filter(User.email == email).first()
    expected_pwd = "admin123" if (role == ROLE_ADMIN or email == "admin@directharvest.com") else "password123"
    if not user:
        user = User(
            full_name=full_name,
            email=email,
            phone=phone,
            password_hash=hash_password(expected_pwd),
            role=role,
            status="Active"
        )
        db.add(user)
        db.flush()
        if role == ROLE_FARMER:
            db.add(FarmerProfile(farmer_id=user.id, trust_score=5.0))
            db.add(Wallet(user_id=user.id, available_balance=100.0))
        elif role == ROLE_CONSUMER:
            db.add(ConsumerProfile(consumer_id=user.id))
        elif role == ROLE_DELIVERY:
            db.add(DeliveryPartnerProfile(delivery_id=user.id, vehicle_type="Bike"))
        db.commit()
        db.refresh(user)
    else:
        user.status = "Active"
        user.password_hash = hash_password(expected_pwd)
        db.commit()
        db.refresh(user)
    return user


@pytest.fixture(scope="session")
def test_setup():
    session = SessionLocal()
    try:
        admin = _get_or_create_user(session, "admin@directharvest.com", ROLE_ADMIN, "Administrator", "+91 9691793254")
        farmer = _get_or_create_user(session, "farmer.test@directharvest.com", ROLE_FARMER, "Test Farmer", "9876543210")
        consumer = _get_or_create_user(session, "consumer.test@directharvest.com", ROLE_CONSUMER, "Test Consumer", "9876543211")
        delivery = _get_or_create_user(session, "delivery.test@directharvest.com", ROLE_DELIVERY, "Test Delivery", "9876543212")

        # Ensure all existing crops have status available
        session.query(Crop).update({Crop.status: "available"})
        session.commit()

        # Ensure at least 2 active crops exist
        crops = session.query(Crop).filter(Crop.farmer_id == farmer.id, Crop.quantity_available > 5.0).all()
        if len(crops) < 2:
            c1 = Crop(
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
            )
            c2 = Crop(
                farmer_id=farmer.id,
                crop_name="Alphonso Mango",
                category="Fruits",
                quantity_available=50.0,
                unit="KG",
                farmer_price=120.0,
                status="available",
                location="Ratnagiri",
                quality_grade="Grade A+",
                freshness_score=98.0,
            )
            session.add_all([c1, c2])
            session.commit()

        return {
            "admin": admin.id,
            "farmer": farmer.id,
            "consumer": consumer.id,
            "delivery": delivery.id,
            "consumer_email": consumer.email,
        }
    finally:
        session.close()


@pytest.fixture(scope="session")
def admin_token(test_setup):
    return create_access_token({"sub": str(test_setup["admin"]), "role": ROLE_ADMIN})


@pytest.fixture(scope="session")
def farmer_token(test_setup):
    return create_access_token({"sub": str(test_setup["farmer"]), "role": ROLE_FARMER})


@pytest.fixture(scope="session")
def consumer_token(test_setup):
    return create_access_token({"sub": str(test_setup["consumer"]), "role": ROLE_CONSUMER})


@pytest.fixture(scope="session")
def delivery_token(test_setup):
    return create_access_token({"sub": str(test_setup["delivery"]), "role": ROLE_DELIVERY})


@pytest.fixture(scope="session")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def farmer_headers(farmer_token):
    return {"Authorization": f"Bearer {farmer_token}"}


@pytest.fixture(scope="session")
def consumer_headers(consumer_token):
    return {"Authorization": f"Bearer {consumer_token}"}


@pytest.fixture(scope="session")
def delivery_headers(delivery_token):
    return {"Authorization": f"Bearer {delivery_token}"}
