
import os
from pathlib import Path
from dotenv import load_dotenv

# Project root: the directory containing app/, frontend/, and requirements.txt
BASE_DIR = Path(__file__).resolve().parent.parent

# Load local environment variables from the project root.
# Production platforms should configure these variables securely.
load_dotenv(BASE_DIR / ".env")


def get_bool(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable safely."""
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {"true", "1", "yes", "on"}


class Settings:
    """Central configuration for the DirectHarvest application."""

    # Application
    BASE_DIR = BASE_DIR
    APP_NAME = os.getenv("APP_NAME", "DirectHarvest AI")
    APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
    PORT = int(os.getenv("PORT", "7860"))
    DEBUG = get_bool("DEBUG", APP_ENV == "development")

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
    if not DATABASE_URL and APP_ENV != "production":
        DATABASE_URL = "mysql+pymysql://root:root@localhost:3306/directharvest?charset=utf8mb4"

    # Aiven Cloud MySQL TLS/SSL CA certificate path
    AIVEN_CA_PATH = os.getenv("AIVEN_CA_PATH", str(BASE_DIR / "ca.pem")).strip()

    # Authentication
    SECRET_KEY = os.getenv("SECRET_KEY", "").strip()
    ALGORITHM = os.getenv("ALGORITHM", "HS256").strip()
    ACCESS_TOKEN_EXPIRE_MINUTES = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")
    )

    # Optional frontend origins, separated by commas.
    # Example: http://localhost:7860,http://127.0.0.1:7860
    CORS_ORIGINS = [
        origin.strip().rstrip("/")
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:7860,http://127.0.0.1:7860",
        ).split(",")
        if origin.strip()
    ]

    # WhatsApp Cloud API
    WHATSAPP_ACCESS_TOKEN = os.getenv(
        "WHATSAPP_ACCESS_TOKEN", ""
    ).strip()

    ADMIN_PHONE = os.getenv(
        "ADMIN_PHONE", "+91 9691793254"
    ).strip()

    WHATSAPP_PHONE_NUMBER_ID = os.getenv(
        "WHATSAPP_PHONE_NUMBER_ID", ""
    ).strip()

    WHATSAPP_API_VERSION = os.getenv(
        "WHATSAPP_API_VERSION", "v23.0"
    ).strip()

    # Optional Twilio WhatsApp configuration
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()

    TWILIO_WHATSAPP_FROM = os.getenv(
        "TWILIO_WHATSAPP_FROM",
        "whatsapp:+14155238886",
    ).strip()

    # Optional public base URL for links in messages.
    # Set this to your deployed HTTPS domain in production.
    BASE_URL = os.getenv(
        "BASE_URL", f"http://localhost:{PORT}"
    ).strip().rstrip("/")

    # File storage
    STATIC_DIR = BASE_DIR / "frontend" / "static"
    TEMPLATES_DIR = BASE_DIR / "frontend" / "templates"

    UPLOAD_DIR = BASE_DIR / os.getenv(
        "UPLOAD_DIR",
        "frontend/static/uploads/crop_images",
    )

    # Business defaults
    DEFAULT_DELIVERY_CHARGE = float(
        os.getenv("DEFAULT_DELIVERY_CHARGE", "30.0")
    )

    DEFAULT_COMMISSION_RATE = float(
        os.getenv("DEFAULT_COMMISSION_RATE", "0.05")
    )

    # Optional AI configuration
    AI_ENABLED = get_bool("AI_ENABLED", False)

    # Keep secrets out of logs and frontend responses.
    @classmethod
    def validate(cls):
        # Normalize database URL dialect if needed
        if cls.DATABASE_URL.startswith("mysql://"):
            cls.DATABASE_URL = "mysql+pymysql://" + cls.DATABASE_URL[len("mysql://"):]

        if cls.APP_ENV == "production":
            if not cls.DATABASE_URL:
                raise RuntimeError(
                    "Production configuration error: DATABASE_URL environment variable is required. "
                    "Set DATABASE_URL to your Aiven MySQL connection string in Render environment variables."
                )

            if "localhost" in cls.DATABASE_URL or "127.0.0.1" in cls.DATABASE_URL:
                raise RuntimeError(
                    "Production configuration error: DATABASE_URL cannot point to 'localhost' or '127.0.0.1'. "
                    "Ensure your Render production service is configured with your remote Aiven MySQL database URL."
                )

            if not (cls.DATABASE_URL.startswith("mysql://") or cls.DATABASE_URL.startswith("mysql+pymysql://")):
                raise RuntimeError(
                    "Production configuration error: DATABASE_URL must use MySQL via PyMySQL driver "
                    "(e.g. mysql+pymysql://avnadmin:PASSWORD@HOST:PORT/DATABASE_NAME)."
                )

            if len(cls.SECRET_KEY) < 32:
                raise RuntimeError(
                    "Production requires a SECRET_KEY of at least "
                    "32 characters. Configure it in the environment."
                )

            if cls.DEBUG:
                raise RuntimeError(
                    "DEBUG must be false in production."
                )

            if not cls.BASE_URL.startswith("https://"):
                raise RuntimeError(
                    "Production BASE_URL must use HTTPS (e.g. https://your-service.onrender.com)."
                )

            # Check CA certificate for Aiven in production
            ca_path = Path(cls.AIVEN_CA_PATH).resolve()
            ca_cert_env = os.getenv("AIVEN_CA_CERT", "").strip()
            if ca_cert_env and not ca_path.exists():
                try:
                    ca_path.parent.mkdir(parents=True, exist_ok=True)
                    ca_path.write_text(ca_cert_env, encoding="utf-8")
                except Exception as exc:
                    raise RuntimeError(
                        f"Failed to write AIVEN_CA_CERT to '{ca_path}': {exc}"
                    ) from exc

            if not ca_path.is_file():
                raise RuntimeError(
                    f"Production configuration error: Aiven CA certificate not found at '{ca_path}'. "
                    "Aiven Cloud MySQL requires verified TLS encryption. "
                    "Please download 'ca.pem' from your Aiven Console and add it to the project root, "
                    "or configure AIVEN_CA_PATH or AIVEN_CA_CERT in the Render environment variables."
                )

        elif not cls.SECRET_KEY:
            # Convenient for local development only.
            # Existing login tokens will become invalid after restart.
            cls.SECRET_KEY = os.urandom(32).hex()


settings = Settings()
settings.validate()

# Ensure required local directories exist.
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.STATIC_DIR.mkdir(parents=True, exist_ok=True)
settings.TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
