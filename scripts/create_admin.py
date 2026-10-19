import sys
from pathlib import Path
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models.user import User
from app.utils.security import hash_password
from app.utils.constants import ROLE_ADMIN

def create_admin(
    full_name="Administrator",
    email="admin@directharvest.com",
    password="admin123",
    phone="9999999999"
):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email.lower().strip()).first()
        if user:
            user.password_hash = hash_password(password)
            user.role = ROLE_ADMIN
            user.status = "Active"
            db.commit()
            print(f"✅ Administrator updated: {email} (Password reset to specified password)")
        else:
            admin_user = User(
                full_name=full_name,
                email=email.lower().strip(),
                phone=phone,
                password_hash=hash_password(password),
                role=ROLE_ADMIN,
                address="Bhopal, Madhya Pradesh",
                status="Active"
            )
            db.add(admin_user)
            db.commit()
            print(f"✅ Administrator created: {email} / {password}")
    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Create or update DirectHarvest administrator account")
    parser.add_argument("--name", default="Administrator")
    parser.add_argument("--email", default="admin@directharvest.com")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--phone", default="9999999999")
    args = parser.parse_args()

    create_admin(args.name, args.email, args.password, args.phone)
