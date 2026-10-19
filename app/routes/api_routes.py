import os
import shutil
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models.user import User
from app.models.crop import Crop
from app.models.order import Order
from app.models.review import Review
from app.schemas.user import UserRegister, UserLogin, UserOut, TokenResponse
from app.schemas.crop import CropCreate, CropUpdate, CropOut
from app.schemas.order import CartItemAdd, CartItemUpdate, CheckoutRequest, OrderStatusUpdate, OrderOut
from app.schemas.review import ReviewCreate, ReviewOut
from app.schemas.ai import CropAnalysisResult
from app.services.auth_service import AuthService
from app.services.crop_service import CropService
from app.services.order_service import OrderService
from app.services.review_service import ReviewService
from app.services.ai_service import AIService
from app.services.insights_service import InsightsService
from app.dependencies.auth import get_current_user, require_role
from app.utils.constants import ROLE_ADMIN, ROLE_FARMER, ROLE_CONSUMER, ROLE_DELIVERY
from app.config import settings

router = APIRouter(prefix="/api", tags=["REST API"])

# ---------------- HEALTH CHECK ----------------
@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Production health check verifying application and database connectivity."""
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "app": settings.APP_NAME,
        "database": db_status
    }

# ---------------- PLATFORM STATE & LIVE SYNC ----------------
@router.get("/platform/sync-state")
async def get_platform_sync_state(db: Session = Depends(get_db)):
    """
    Real-time platform synchronization endpoint for live client updates.
    Returns current AI connection status, platform settings, and version.
    """
    from app.services.platform_settings_service import PlatformSettingsService
    return PlatformSettingsService.get_full_state(db=db)

# ---------------- AUTHENTICATION ----------------
@router.post("/auth/register", response_model=UserOut)
async def api_register(data: UserRegister, db: Session = Depends(get_db)):
    try:
        return AuthService.register_user(db, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/auth/login", response_model=TokenResponse)
async def api_login(data: UserLogin, db: Session = Depends(get_db)):
    user = AuthService.authenticate_user(db, data.email, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = AuthService.generate_token_for_user(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": user
    }

@router.get("/auth/me", response_model=UserOut)
async def api_me(current_user: User = Depends(get_current_user)):
    return current_user

# ---------------- CROPS ----------------
@router.get("/crops", response_model=List[CropOut])
async def api_list_crops(
    category: Optional[str] = None,
    search: Optional[str] = None,
    grade: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    return CropService.get_all_crops(
        db, category=category, search=search, grade=grade,
        min_price=min_price, max_price=max_price, limit=limit, offset=offset
    )

@router.get("/crops/{crop_id}", response_model=CropOut)
async def api_get_crop(crop_id: int, db: Session = Depends(get_db)):
    crop = CropService.get_crop_by_id(db, crop_id)
    if not crop:
        raise HTTPException(status_code=404, detail="Crop not found")
    return crop

@router.post("/crops", response_model=CropOut)
async def api_create_crop(
    data: CropCreate,
    current_user: User = Depends(require_role([ROLE_FARMER])),
    db: Session = Depends(get_db)
):
    return CropService.create_crop(db, current_user.id, data)

@router.put("/crops/{crop_id}", response_model=CropOut)
async def api_update_crop(
    crop_id: int,
    data: CropUpdate,
    current_user: User = Depends(require_role([ROLE_FARMER])),
    db: Session = Depends(get_db)
):
    try:
        return CropService.update_crop(db, crop_id, current_user.id, data)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.delete("/crops/{crop_id}")
async def api_delete_crop(
    crop_id: int,
    current_user: User = Depends(require_role([ROLE_FARMER])),
    db: Session = Depends(get_db)
):
    try:
        success = CropService.delete_crop(db, crop_id, current_user.id)
        if not success:
            raise HTTPException(status_code=404, detail="Crop not found")
        return {"detail": "Crop deleted successfully"}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

# ---------------- CART & CHECKOUT ----------------
@router.post("/cart")
async def api_add_to_cart(
    data: CartItemAdd,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        item = OrderService.add_to_cart(db, current_user.id, data.crop_id, data.quantity)
        return {"detail": "Added to cart", "cart_id": item.cart_id, "quantity": item.quantity}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/cart")
async def api_get_cart(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = OrderService.get_cart_items(db, current_user.id)
    out = []
    subtotal = 0.0
    for it in items:
        crop = it.crop
        price = crop.farmer_price if crop else 0.0
        line_total = round(it.quantity * price, 2)
        subtotal += line_total
        out.append({
            "cart_id": it.cart_id,
            "crop_id": it.crop_id,
            "crop_name": crop.crop_name if crop else "N/A",
            "quantity": it.quantity,
            "price_per_kg": price,
            "total_price": line_total
        })
    return {
        "items": out,
        "subtotal": round(subtotal, 2),
        "delivery_charge": settings.DEFAULT_DELIVERY_CHARGE if subtotal > 0 else 0.0,
        "total_amount": round(subtotal + (settings.DEFAULT_DELIVERY_CHARGE if subtotal > 0 else 0.0), 2)
    }

@router.post("/checkout", response_model=List[OrderOut])
async def api_checkout(
    data: CheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        orders = OrderService.checkout(
            db=db,
            consumer=current_user,
            delivery_address=data.delivery_address,
            payment_method=data.payment_method
        )
        return orders
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------------- ORDERS ----------------
@router.get("/orders", response_model=List[OrderOut])
async def api_list_orders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role == ROLE_ADMIN:
        return db.query(Order).order_by(desc(Order.order_id)).all()
    elif current_user.role == ROLE_FARMER:
        return db.query(Order).filter(Order.farmer_id == current_user.id).order_by(desc(Order.order_id)).all()
    elif current_user.role == ROLE_DELIVERY:
        return db.query(Order).filter(Order.delivery_partner_id == current_user.id).order_by(desc(Order.order_id)).all()
    else:
        return db.query(Order).filter(Order.consumer_id == current_user.id).order_by(desc(Order.order_id)).all()

@router.put("/orders/{order_id}/status", response_model=OrderOut)
async def api_update_order_status(
    order_id: int,
    data: OrderStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        return OrderService.update_order_status(
            db=db,
            order_id=order_id,
            new_status=data.status,
            delivery_partner_id=data.delivery_partner_id,
            updated_by_user=current_user
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# ---------------- REVIEWS ----------------
@router.post("/reviews", response_model=ReviewOut)
async def api_create_review(
    data: ReviewCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        return ReviewService.add_review(
            db=db,
            consumer_id=current_user.id,
            order_id=data.order_id,
            rating=data.rating,
            review_text=data.review_text
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---------------- OPENCV CROP ANALYSIS ----------------
@router.post("/analyze-crop")
async def api_analyze_crop(
    crop_name: str = Form(""),
    farmer_price: float = Form(0.0),
    file: Optional[UploadFile] = File(None)
):
    """Processes uploaded crop image via OpenCV computer vision."""
    temp_path = None
    if file and file.filename:
        temp_filename = f"temp_cv_{file.filename}"
        dest = settings.UPLOAD_DIR / temp_filename
        with open(dest, "wb") as buf:
            shutil.copyfileobj(file.file, buf)
        temp_path = str(dest)

    res = AIService.analyze_crop_image(temp_path, crop_name, farmer_price)

    # Clean up temp file if needed
    if temp_path and os.path.exists(temp_path):
        try:
            os.remove(temp_path)
        except Exception:
            pass

    return res

# ---------------- INSIGHTS ----------------
@router.get("/insights/pricing/{crop_name}")
async def api_pricing_insights(crop_name: str, db: Session = Depends(get_db)):
    return InsightsService.get_price_analytics_for_crop(db, crop_name)

@router.get("/insights/demand")
async def api_demand_insights(db: Session = Depends(get_db)):
    return InsightsService.get_market_demand_summary(db)

# ---------------- DELIVERY RIDER LIVE TRACKING & TELEMETRY ----------------
@router.get("/delivery/order/{order_id}/live-tracking")
async def api_get_order_live_tracking(order_id: int, db: Session = Depends(get_db)):
    """
    Returns live tracking payload (rider coords, farmer pickup, consumer drop-off,
    progression step, ETA, distance, package photo) for Consumer, Admin, and Rider views.
    """
    from app.services.delivery_tracking_service import DeliveryTrackingService
    data = DeliveryTrackingService.get_live_tracking_data(db, order_id)
    if not data.get("success"):
        raise HTTPException(status_code=404, detail=data.get("error", "Order not found"))
    return {
        "success": True,
        "telemetry": data,
        **data
    }

@router.post("/delivery/update-location")
async def api_update_delivery_location(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Called by delivery rider's browser/phone background geolocation watcher.
    Supports both JSON and Form payloads.
    """
    from app.services.delivery_tracking_service import DeliveryTrackingService
    from app.models.order import Order

    latitude = 0.0
    longitude = 0.0
    order_id = None
    rider_id = None
    speed = 0.0

    content_type = request.headers.get("content-type", "").lower()
    if "application/json" in content_type:
        try:
            body = await request.json()
            latitude = float(body.get("latitude", 0.0))
            longitude = float(body.get("longitude", 0.0))
            order_id = body.get("order_id")
            rider_id = body.get("rider_id")
            speed = float(body.get("speed", 0.0))
        except Exception:
            pass
    else:
        form = await request.form()
        try:
            latitude = float(form.get("latitude", 0.0))
            longitude = float(form.get("longitude", 0.0))
            order_id = form.get("order_id")
            if order_id:
                order_id = int(order_id)
            rider_id = form.get("rider_id")
            if rider_id:
                rider_id = int(rider_id)
            speed = float(form.get("speed", 0.0))
        except Exception:
            pass

    if not rider_id and order_id:
        o = db.query(Order).filter(Order.order_id == order_id).first()
        if o and o.delivery_partner_id:
            rider_id = o.delivery_partner_id

    if not rider_id:
        return {"success": False, "message": "Missing rider_id"}

    updated = DeliveryTrackingService.update_rider_gps(
        db, rider_id=rider_id, order_id=order_id, latitude=latitude, longitude=longitude, speed=speed
    )
    return {"success": updated}


# ---------------- PLACES & STREET AUTOCOMPLETE ----------------
@router.get("/places/autocomplete")
async def api_places_autocomplete(
    q: str = Query("", min_length=1, description="Query letters entered by user"),
    limit: int = Query(8, ge=1, le=20)
):
    """
    Suggests verified place, street, and locality names matching user typing.
    Tri-tier: Google Places -> OpenStreetMap Photon -> Local Curated MP/Indian Streets DB.
    """
    from app.services.places_service import PlacesService
    suggestions = PlacesService.search_places(q, limit=limit)
    return {
        "success": True,
        "query": q,
        "count": len(suggestions),
        "suggestions": suggestions
    }

