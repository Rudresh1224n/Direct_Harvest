
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine, get_sanitized_db_url
from app import models  # Ensure all SQLAlchemy models are registered
from app.routes import (
    public_router,
    auth_router,
    consumer_router,
    farmer_router,
    delivery_router,
    admin_router,
    api_router,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("directharvest")


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Initialize required local resources when the application starts."""
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (settings.UPLOAD_DIR / "packages").mkdir(parents=True, exist_ok=True)
    settings.STATIC_DIR.mkdir(parents=True, exist_ok=True)

    sanitized_url = get_sanitized_db_url()
    logger.info("Initializing database connection to: %s", sanitized_url)

    # Verify cloud database connectivity and create missing tables
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connectivity check passed.")

        Base.metadata.create_all(bind=engine)
        logger.info("Database schema checked and tables verified successfully.")

        # Seed default administrator account if not present
        from app.database import SessionLocal
        from app.models.user import User
        from app.utils.constants import ROLE_ADMIN
        from app.utils.security import hash_password
        with SessionLocal() as db:
            admin_user = (
                db.query(User)
                .filter(User.email == "admin@directharvest.com")
                .first()
            )
            admin_phone = "".join(ch for ch in settings.ADMIN_PHONE if ch.isdigit())[-10:] if settings.ADMIN_PHONE else "9691793254"
            if not admin_user:
                admin_user = User(
                    full_name="Administrator",
                    email="admin@directharvest.com",
                    phone=admin_phone,
                    password_hash=hash_password("admin123"),
                    role=ROLE_ADMIN,
                    address="Bhopal, Madhya Pradesh",
                    status="Active",
                )
                db.add(admin_user)
                db.commit()
                logger.info("Created default administrator account: admin@directharvest.com / admin123")
            else:
                if admin_user.status != "Active":
                    admin_user.status = "Active"
                    db.commit()
    except Exception as exc:
        logger.error("Database connection/initialization failed for: %s", sanitized_url)
        logger.exception("Database startup error details: %s", exc)
        raise

    # Initialize Excel Credentials and start background watcher
    try:
        from app.database import SessionLocal
        from app.services.excel_credential_service import ExcelCredentialService
        with SessionLocal() as db:
            ExcelCredentialService.initialize_or_export_all(db)

        def _watch_excel_loop():
            import time
            while True:
                try:
                    time.sleep(1)
                    with SessionLocal() as session:
                        ExcelCredentialService.check_and_sync_if_modified(session)
                except Exception:
                    pass

        import threading
        watcher = threading.Thread(target=_watch_excel_loop, daemon=True, name="ExcelWatcher")
        watcher.start()
        logger.info("Excel credentials synchronization daemon started.")
    except Exception:
        logger.exception("Excel credentials initialization failed.")

    logger.info("%s started.", settings.APP_NAME)

    yield

    engine.dispose()
    logger.info("%s stopped.", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "DirectHarvest AI — a farmer-to-consumer marketplace "
        "with crop image analysis, pricing insights, and delivery management."
    ),
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS is restricted to configured frontend origins.
# Same-origin deployments usually do not need cross-origin requests.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# Static files and uploaded crop images.
app.mount(
    "/static",
    StaticFiles(directory=str(settings.STATIC_DIR)),
    name="static",
)

# Uploaded crop images and delivery package verification photos.
app.mount(
    "/uploads",
    StaticFiles(directory=str(settings.UPLOAD_DIR)),
    name="uploads",
)

# Register existing application routers.
app.include_router(public_router)
app.include_router(auth_router)
app.include_router(consumer_router)
app.include_router(farmer_router)
app.include_router(delivery_router)
app.include_router(admin_router)
app.include_router(api_router)


@app.get("/health", tags=["System"])
def health_check():
    """Lightweight process health check."""
    return {
        "status": "ok",
        "application": settings.APP_NAME,
    }


@app.get("/api/health", tags=["System"])
def api_health_check():
    """Check that the API can also reach the database."""
    from sqlalchemy import text

    from app.database import SessionLocal

    db = SessionLocal()

    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "database": "connected",
            "application": settings.APP_NAME,
        }
    except Exception:
        logger.exception("Database health check failed.")
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "database": "unavailable",
            },
        )
    finally:
        db.close()


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG,
    )
