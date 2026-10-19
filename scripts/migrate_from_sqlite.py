import os
import sys
import sqlite3
from pathlib import Path
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import engine, Base, SessionLocal
from app.models.user import User, FarmerProfile, ConsumerProfile, DeliveryPartnerProfile
from app.models.crop import Crop
from app.models.wallet import Wallet
from app.models.logs import PlatformSetting
from app.utils.security import hash_password

KNOWN_PASSWORDS = {
    "admin@directharvest.com": "admin123",
    "rudresh.narkhede19@gmail.com": "asdfghjkl;",
    "rohan@gmail.com": "qwertyuiop",
    "lishika@gmail.com": "asdfghjkl;",
    "shreya@gmail.com": "asdfghjkl;",
    "saanthosh@gmail.com": "asdfghjkl;",
    "krishamreliya240489@acropolis.in": "Krish@2005",
    "sourabhmakwani230489@acropolis.in": "Sourabh@2005",
    "labhanshgade55@gmail.com": "Labhansh@2005",
}

def migrate():
    sqlite_path = Path("E:/assignment/coding/DirectHarvest/backend/database/database.db")
    if not sqlite_path.exists():
        print(f"⚠️ SQLite database not found at {sqlite_path}. Skipping migration.")
        return

    print(f"Connecting to legacy SQLite database: {sqlite_path}")
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Initialize MySQL schema
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # 1. Migrate Users
        print("\n--- Migrating Users ---")
        cur.execute("SELECT * FROM users")
        user_rows = cur.fetchall()

        for u in user_rows:
            email = u["email"].lower().strip()
            existing = db.query(User).filter(User.email == email).first()
            if existing:
                print(f"User {email} already exists in MySQL. Skipping.")
                continue

            raw_pwd = KNOWN_PASSWORDS.get(email, "DirectHarvest@123")
            pwd_hash = hash_password(raw_pwd)

            new_user = User(
                id=u["id"],
                full_name=u["full_name"],
                email=email,
                phone=u["phone"],
                password_hash=pwd_hash,
                role=u["role"],
                address=u["address"],
                status=u["status"] or "Active"
            )
            db.add(new_user)
            db.flush()

            # Create corresponding role profile
            if u["role"] == "farmer":
                if not db.query(FarmerProfile).filter(FarmerProfile.farmer_id == new_user.id).first():
                    db.add(FarmerProfile(farmer_id=new_user.id, trust_score=5.0))
                if not db.query(Wallet).filter(Wallet.user_id == new_user.id).first():
                    db.add(Wallet(user_id=new_user.id, available_balance=0.0))
            elif u["role"] == "consumer":
                if not db.query(ConsumerProfile).filter(ConsumerProfile.consumer_id == new_user.id).first():
                    db.add(ConsumerProfile(consumer_id=new_user.id))
            elif u["role"] == "delivery":
                if not db.query(DeliveryPartnerProfile).filter(DeliveryPartnerProfile.delivery_id == new_user.id).first():
                    db.add(DeliveryPartnerProfile(delivery_id=new_user.id, vehicle_type="Bike", license_number="MP-09-AB-1234"))

            print(f"Migrated user: {new_user.full_name} ({new_user.role}) - Password set to '{raw_pwd}'")

        db.commit()

        # 2. Migrate Crops
        print("\n--- Migrating Crops ---")
        cur.execute("SELECT * FROM crops")
        crop_rows = cur.fetchall()

        for c in crop_rows:
            existing = db.query(Crop).filter(Crop.crop_id == c["crop_id"]).first()
            if existing:
                print(f"Crop #{c['crop_id']} already exists in MySQL. Skipping.")
                continue

            # Ensure quantity is >= 0 to comply with MySQL positive stock constraint
            qty = float(c["quantity_available"] if c["quantity_available"] is not None else 0.0)
            if qty < 0:
                print(f"Notice: Correcting negative stock ({qty}) for '{c['crop_name']}' to 10.0 KG")
                qty = 10.0

            new_crop = Crop(
                crop_id=c["crop_id"],
                farmer_id=c["farmer_id"],
                crop_name=c["crop_name"],
                category=c["category"] or "Vegetables",
                quantity_available=qty,
                unit="KG",
                farmer_price=float(c["farmer_price"] if c["farmer_price"] else 30.0),
                ai_suggested_price=float(c["ai_suggested_price"]) if c["ai_suggested_price"] else float(c["farmer_price"] or 30.0),
                description=c["description"] or "Fresh farm produce.",
                crop_image=c["crop_image"],
                quality_grade=c["quality_grade"] or "A",
                freshness_score=float(c["freshness_score"] if c["freshness_score"] else 90.0),
                demand_score=float(c["demand_score"] if c["demand_score"] else 80.0),
                demand_level=c["demand_level"] or "Medium",
                market_suitability=c["market_suitability"] or "Good",
                status="available" if qty > 0 else "out_of_stock"
            )
            db.add(new_crop)
            print(f"Migrated crop: #{new_crop.crop_id} {new_crop.crop_name} (₹{new_crop.farmer_price}/KG, {new_crop.quantity_available} KG)")

        db.commit()
        print("\n✅ Migration from SQLite to MySQL completed successfully!")

    except Exception as e:
        db.rollback()
        print(f"❌ Error during migration: {e}")
        raise e
    finally:
        conn.close()
        db.close()

if __name__ == "__main__":
    migrate()
