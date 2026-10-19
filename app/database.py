import logging
import os
import ssl
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

logger = logging.getLogger("directharvest.database")


def normalize_database_url(raw_url: str) -> str:
    """
    Sanitize and normalize database connection URL for SQLAlchemy + PyMySQL.
    - Converts mysql:// to mysql+pymysql://
    - Removes incompatible query parameters like ssl-mode that PyMySQL does not support
    - Safely URL-encodes special characters in user and password
    """
    if not raw_url:
        return raw_url

    url = raw_url.strip()
    if url.startswith("mysql://"):
        url = "mysql+pymysql://" + url[len("mysql://"):]

    # Safely handle special characters in credentials
    # Pattern: scheme://user:password@host:port/database?query
    try:
        if "://" in url and "@" in url:
            scheme, remainder = url.split("://", 1)
            last_at_idx = remainder.rfind("@")
            user_pass = remainder[:last_at_idx]
            host_and_rest = remainder[last_at_idx + 1:]

            if ":" in user_pass:
                user, password = user_pass.split(":", 1)
                from urllib.parse import quote_plus, unquote_plus
                safe_user = quote_plus(unquote_plus(user))
                safe_pwd = quote_plus(unquote_plus(password))
                url = f"{scheme}://{safe_user}:{safe_pwd}@{host_and_rest}"
    except Exception as exc:
        logger.warning("Error normalizing credentials in database URL: %s", exc)

    try:
        parsed = urlparse(url)
        if parsed.query:
            query_params = parse_qs(parsed.query, keep_blank_values=True)
            # Remove parameters incompatible with PyMySQL driver
            modified = False
            for key in ["ssl-mode", "sslmode"]:
                if key in query_params:
                    query_params.pop(key, None)
                    modified = True
            if modified:
                new_query = urlencode(query_params, doseq=True)
                url = urlunparse(parsed._replace(query=new_query))
    except Exception as exc:
        logger.warning("Could not parse query parameters in database URL: %s", exc)

    return url


def get_sanitized_db_url(url: str = None) -> str:
    """Return database URL with password masked for safe logging."""
    target = url or settings.DATABASE_URL
    if not target:
        return "(empty DATABASE_URL)"
    try:
        return make_url(target).render_as_string(hide_password=True)
    except Exception:
        # Fallback mask if URL parsing fails
        if "@" in target:
            prefix, rest = target.split("@", 1)
            scheme = prefix.split("://", 1)[0]
            return f"{scheme}://***:***@{rest}"
        return "mysql+pymysql://***"


def build_engine():
    """
    Configure and create SQLAlchemy engine with PyMySQL and verified TLS/SSL for Aiven.
    """
    raw_url = settings.DATABASE_URL
    # Support discrete environment variables if DATABASE_URL is not set
    if not raw_url and os.getenv("DB_HOST"):
        from urllib.parse import quote_plus
        db_user = os.getenv("DB_USER", "avnadmin").strip()
        db_pass = os.getenv("DB_PASSWORD", "").strip()
        db_host = os.getenv("DB_HOST", "").strip()
        db_port = os.getenv("DB_PORT", "3306").strip()
        db_name = os.getenv("DB_NAME", "defaultdb").strip()
        raw_url = f"mysql+pymysql://{db_user}:{quote_plus(db_pass)}@{db_host}:{db_port}/{db_name}?charset=utf8mb4"

    if not raw_url:
        if settings.APP_ENV == "production":
            raise RuntimeError(
                "DATABASE_URL is not set in production. Please configure your Aiven MySQL connection string in Render."
            )
        raw_url = "mysql+pymysql://root:root@localhost:3306/directharvest?charset=utf8mb4"

    db_url = normalize_database_url(raw_url)

    connect_args = {}
    engine_options = {
        "pool_pre_ping": True,
    }

    if db_url.startswith("sqlite"):
        # SQLite needs this option when used with FastAPI.
        connect_args["check_same_thread"] = False
    else:
        # Connection pooling for MySQL.
        engine_options.update(
            {
                "pool_recycle": 1800,
                "pool_size": 5,
                "max_overflow": 10,
            }
        )

        # Check if SSL/TLS is needed
        parsed = urlparse(db_url)
        host = (parsed.hostname or "").lower()
        is_local = host in ("localhost", "127.0.0.1", "")
        ca_path = Path(settings.AIVEN_CA_PATH).resolve()

        # SSL is required in production, when host is remote/Aiven, or when CA file is present
        needs_ssl = (
            settings.APP_ENV == "production"
            or not is_local
            or "aivencloud.com" in host
            or (ca_path.is_file() and not is_local)
        )

        if needs_ssl:
            # Handle CA certificate string from env if file is missing
            ca_cert_env = os.getenv("AIVEN_CA_CERT", "").strip()
            if ca_cert_env and not ca_path.exists():
                try:
                    ca_path.parent.mkdir(parents=True, exist_ok=True)
                    ca_path.write_text(ca_cert_env, encoding="utf-8")
                except Exception:
                    pass

            if not ca_path.is_file():
                raise RuntimeError(
                    f"Aiven MySQL requires TLS/SSL, but CA certificate was not found at '{ca_path}'. "
                    "Please download 'ca.pem' from the Aiven Console and place it at the project root, "
                    "or set the AIVEN_CA_PATH environment variable."
                )

            try:
                ssl_context = ssl.create_default_context(cafile=str(ca_path))
                ssl_context.check_hostname = True
                ssl_context.verify_mode = ssl.CERT_REQUIRED
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to initialize SSL context using CA certificate at '{ca_path}': {exc}. "
                    "Ensure the file contains a valid PEM-encoded certificate."
                ) from exc

            # Ensure SSL is not added twice if already configured in query or connect_args
            if "ssl" not in connect_args and "ssl_ca" not in parsed.query:
                connect_args["ssl"] = ssl_context
                logger.info(
                    "Configured verified TLS/SSL context for database connection using CA certificate: %s",
                    ca_path.name,
                )

    engine = create_engine(
        db_url,
        connect_args=connect_args,
        **engine_options,
    )
    return engine


engine = build_engine()

# One session per request or operation.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)

# Base class for SQLAlchemy models.
Base = declarative_base()


def get_db():
    """
    FastAPI dependency that provides a database session
    and closes it when the request finishes.
    """
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
