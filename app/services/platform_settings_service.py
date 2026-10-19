import time
import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.logs import PlatformSetting
from app.utils.ist_time import get_ist_now, format_ist_datetime

logger = logging.getLogger("platform_settings_service")

# Global in-memory cache and version tracking
_settings_cache: Dict[str, str] = {}
_last_fetch_time: float = 0.0
_state_version: float = time.time()
CACHE_TTL_SECONDS: float = 2.0


class PlatformSettingsService:
    @classmethod
    def get_state_version(cls) -> float:
        """Returns the current monotonic/timestamp version of platform settings."""
        global _state_version
        return _state_version

    @classmethod
    def bump_version(cls, reason: str = "settings_changed"):
        """Call this whenever settings or admin features are updated to notify all clients."""
        global _state_version, _last_fetch_time
        _state_version = time.time()
        _last_fetch_time = 0.0  # Force immediate cache reload
        logger.info("Platform settings version bumped to %s (Reason: %s)", _state_version, reason)

    @classmethod
    def _refresh_cache(cls, db: Optional[Session] = None):
        """Reload all platform settings from the database into the in-memory cache."""
        global _settings_cache, _last_fetch_time
        try:
            if db is not None:
                rows = db.query(PlatformSetting).all()
            else:
                with SessionLocal() as session:
                    rows = session.query(PlatformSetting).all()

            new_cache = {r.key: str(r.value or "").strip() for r in rows}
            _settings_cache = new_cache
            _last_fetch_time = time.time()
        except Exception:
            logger.exception("Failed to refresh platform settings cache.")

    @classmethod
    def get_setting(cls, key: str, default: str = "", db: Optional[Session] = None) -> str:
        """Retrieve a platform setting string value."""
        global _settings_cache, _last_fetch_time
        now = time.time()
        if now - _last_fetch_time > CACHE_TTL_SECONDS or not _settings_cache:
            cls._refresh_cache(db)
        return _settings_cache.get(key, default)

    @classmethod
    def get_bool(cls, key: str, default: bool = False, db: Optional[Session] = None) -> bool:
        """Retrieve a platform setting as a boolean."""
        val = cls.get_setting(key, default="", db=db)
        if not val:
            return default
        return val.lower() in ("true", "1", "yes", "on")

    @classmethod
    def is_ai_enabled(cls, db: Optional[Session] = None) -> bool:
        """
        Check if the AI feature is enabled across the platform.
        Defaults to True if no record exists yet.
        """
        raw_val = cls.get_setting("ai_enabled", default="", db=db)
        if not raw_val:
            return True
        return raw_val.lower() in ("true", "1", "yes", "on")

    @classmethod
    def get_ai_status(cls, db: Optional[Session] = None) -> str:
        """Returns 'connected' or 'disconnected'."""
        return "connected" if cls.is_ai_enabled(db=db) else "disconnected"

    @classmethod
    def set_setting(cls, key: str, value: str, db: Optional[Session] = None) -> str:
        """Persist a setting into the database and bump the state version immediately."""
        clean_val = str(value).strip()

        def _do_update(s: Session):
            setting = s.query(PlatformSetting).filter(PlatformSetting.key == key).first()
            if setting:
                setting.value = clean_val
            else:
                s.add(PlatformSetting(key=key, value=clean_val))
            s.commit()

        if db is not None:
            _do_update(db)
        else:
            with SessionLocal() as session:
                _do_update(session)

        cls.bump_version(reason=f"updated_{key}")
        return clean_val

    @classmethod
    def get_full_state(cls, db: Optional[Session] = None) -> Dict[str, Any]:
        """Provides a complete JSON-serializable snapshot of platform settings."""
        ai_enabled = cls.is_ai_enabled(db=db)
        return {
            "ai_enabled": ai_enabled,
            "ai_status": "connected" if ai_enabled else "disconnected",
            "version": cls.get_state_version(),
            "commission_rate": float(cls.get_setting("commission_rate", "0.05", db=db) or 0.05),
            "ai_model": cls.get_setting("ai_model", "gpt-4o-mini", db=db),
            "timestamp": format_ist_datetime(get_ist_now()),
        }
