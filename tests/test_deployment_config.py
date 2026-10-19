import os
from pathlib import Path
import pytest
from app.config import Settings
from app.database import normalize_database_url, get_sanitized_db_url


def test_normalize_database_url_converts_mysql_scheme():
    url = "mysql://avnadmin:pass123@mysql-service.aivencloud.com:12345/defaultdb"
    normalized = normalize_database_url(url)
    assert normalized.startswith("mysql+pymysql://")


def test_normalize_database_url_strips_ssl_mode():
    url = "mysql+pymysql://avnadmin:pass123@mysql-service.aivencloud.com:12345/defaultdb?ssl-mode=REQUIRED&charset=utf8mb4"
    normalized = normalize_database_url(url)
    assert "ssl-mode" not in normalized
    assert "charset=utf8mb4" in normalized


def test_get_sanitized_db_url_masks_password():
    url = "mysql+pymysql://avnadmin:super_secret_p%40ss@mysql-service.aivencloud.com:12345/defaultdb"
    sanitized = get_sanitized_db_url(url)
    assert "super_secret" not in sanitized
    assert "avnadmin" in sanitized
    assert "mysql-service.aivencloud.com" in sanitized


def test_production_rejects_missing_or_localhost_database():
    orig_env = Settings.APP_ENV
    orig_url = Settings.DATABASE_URL
    orig_key = Settings.SECRET_KEY
    orig_base = Settings.BASE_URL
    orig_ca = Settings.AIVEN_CA_PATH
    orig_debug = Settings.DEBUG

    try:
        Settings.APP_ENV = "production"
        Settings.DEBUG = False
        Settings.SECRET_KEY = "a" * 32
        Settings.BASE_URL = "https://directharvest.onrender.com"
        Settings.AIVEN_CA_PATH = "non_existent_ca.pem"

        # Missing database URL
        Settings.DATABASE_URL = ""
        with pytest.raises(RuntimeError, match="DATABASE_URL environment variable is required"):
            Settings.validate()

        # Localhost database URL
        Settings.DATABASE_URL = "mysql+pymysql://root:root@localhost:3306/directharvest"
        with pytest.raises(RuntimeError, match="cannot point to 'localhost'"):
            Settings.validate()

        # Missing CA file
        Settings.DATABASE_URL = "mysql+pymysql://avnadmin:secret@mysql-service.aivencloud.com:12345/defaultdb"
        with pytest.raises(RuntimeError, match="Aiven CA certificate not found"):
            Settings.validate()

    finally:
        Settings.APP_ENV = orig_env
        Settings.DATABASE_URL = orig_url
        Settings.SECRET_KEY = orig_key
        Settings.BASE_URL = orig_base
        Settings.AIVEN_CA_PATH = orig_ca
        Settings.DEBUG = orig_debug
