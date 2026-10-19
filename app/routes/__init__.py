from app.routes.public_routes import router as public_router
from app.routes.auth_routes import router as auth_router
from app.routes.consumer_routes import router as consumer_router
from app.routes.farmer_routes import router as farmer_router
from app.routes.delivery_routes import router as delivery_router
from app.routes.admin_routes import router as admin_router
from app.routes.api_routes import router as api_router

__all__ = [
    "public_router",
    "auth_router",
    "consumer_router",
    "farmer_router",
    "delivery_router",
    "admin_router",
    "api_router",
]
