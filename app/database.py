
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings


# Create the database engine.
# pool_pre_ping checks connections before reusing them.
connect_args = {}
engine_options = {
    "pool_pre_ping": True,
}

if settings.DATABASE_URL.startswith("sqlite"):
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

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    **engine_options,
)

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
