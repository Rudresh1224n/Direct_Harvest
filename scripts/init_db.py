import sys
from pathlib import Path
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import engine, Base, SessionLocal
from app.models import PlatformSetting
from app.config import settings

def init_db():
    print(f"Creating database tables on: {settings.DATABASE_URL}")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Initialize default settings
        defaults = {
            "commission_rate": "0.05",
            "ai_enabled": "True",
            "platform_name": "DirectHarvest AI"
        }
        for k, v in defaults.items():
            existing = db.query(PlatformSetting).filter(PlatformSetting.key == k).first()
            if not existing:
                db.add(PlatformSetting(key=k, value=v))
        db.commit()
        print("✅ Database schema initialized successfully.")
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
