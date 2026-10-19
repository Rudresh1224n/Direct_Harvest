import os
import shutil
import time
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, Depends, Form, File, UploadFile, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from app.database import get_db
from app.templates_config import templates
from app.models.user import User, FarmerProfile
from app.models.crop import Crop, CropAssessment
from app.models.order import Order
from app.models.review import Review
from app.models.wallet import Wallet, WalletTransaction
from app.services.crop_service import CropService
from app.services.order_service import OrderService
from app.services.ai_service import AIService
from app.services.trust_score_service import TrustScoreService
from app.services.wallet_service import WalletService
from app.dependencies.auth import require_role
from app.utils.constants import ROLE_FARMER, STATUS_DELIVERED, STATUS_PENDING, STATUS_ACCEPTED, STATUS_CANCELLED
from app.utils.ist_time import format_ist_datetime
from app.config import settings

router = APIRouter(prefix="/farmer", tags=["Farmer"])

# ---------------- FARMER DASHBOARD ----------------
@router.get("/dashboard", response_class=HTMLResponse)
async def farmer_dashboard(
    request: Request,
    current_user: User = Depends(require_role([ROLE_FARMER])),
    db: Session = Depends(get_db)
):
    crops = db.query(Crop).filter(Crop.farmer_id == current_user.id).all()
    orders = db.query(Order).filter(Order.farmer_id == current_user.id).order_by(desc(Order.order_id)).all()

    total_crops = len(crops)
    total_orders = len(orders)
    delivered_orders = sum(1 for o in orders if o.status == STATUS_DELIVERED)
    pending_orders = sum(1 for o in orders if o.status in (STATUS_PENDING, STATUS_ACCEPTED))
    revenue = sum(o.total_amount for o in orders if o.status == STATUS_DELIVERED)

    aov = round(revenue / delivered_orders, 2) if delivered_orders > 0 else 0.0

    # Top selling crop
    crop_counts = {}
    for o in orders:
        if o.crop:
            crop_counts[o.crop.crop_name] = crop_counts.get(o.crop.crop_name, 0) + o.quantity
    top_selling = max(crop_counts, key=crop_counts.get) if crop_counts else "None"

    # Format crops for dashboard
    from app.routes.public_routes import format_crop_for_template
    formatted_crops = [format_crop_for_template(c) for c in crops[:6]]

    recent_orders_formatted = []
    for o in orders[:5]:
        recent_orders_formatted.append({
            "order_id": o.order_id,
            "customer_name": o.consumer.full_name if o.consumer else "Customer",
            "crop_name": o.crop.crop_name if o.crop else f"Crop #{o.crop_id}",
            "total_amount": round(o.total_amount, 2),
            "status": o.status
        })

    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name
    }

    return templates.TemplateResponse(
        "farmer/farmer_dashboard.html",
        {
            "request": request,
            "farmer_name": current_user.full_name,
            "revenue": round(revenue, 2),
            "total_crops": total_crops,
            "total_orders": total_orders,
            "delivered_orders": delivered_orders,
            "pending_orders": pending_orders,
            "aov": aov,
            "top_selling_crop": top_selling,
            "crops": formatted_crops,
            "orders": orders[:5],
            "recent_orders": recent_orders_formatted,
            "chart_labels": ["Jun", "Jul", "Aug", "Sep", "Oct"],
            "chart_orders": [0, 0, 0, 0, total_orders],
            "chart_revenue": [0, 0, 0, 0, round(revenue, 2)],
            "months": ["Jun", "Jul", "Aug", "Sep", "Oct"],
            "revenues": [0, 0, 0, 0, round(revenue, 2)],
            "session": session_data,
            "ai_status": "connected"
        }
    )

# ---------------- CROP MANAGEMENT ----------------
@router.get("/manage-crops", response_class=HTMLResponse)
@router.get("/crops", response_class=HTMLResponse)
async def manage_crops_page(
    request: Request,
    current_user: User = Depends(require_role([ROLE_FARMER])),
    db: Session = Depends(get_db)
):
    raw_crops = CropService.get_crops_by_farmer(db, current_user.id)
    from app.routes.public_routes import format_crop_for_template
    formatted = [format_crop_for_template(c) for c in raw_crops]

    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name
    }

    return templates.TemplateResponse(
        "farmer/manage_crops.html",
        {
            "request": request,
            "crops": formatted,
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.get("/add-crop", response_class=HTMLResponse)
async def add_crop_page(
    request: Request,
    current_user: User = Depends(require_role([ROLE_FARMER]))
):
    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name
    }
    return templates.TemplateResponse(
        "farmer/add_crop.html",
        {
            "request": request,
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.post("/add-crop")
async def add_crop_action(
    request: Request,
    crop_name: str = Form(...),
    category: str = Form(...),
    quantity: Optional[float] = Form(None),
    quantity_available: Optional[float] = Form(None),
    farmer_price: Optional[float] = Form(None),
    price: Optional[float] = Form(None),
    description: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    crop_image: Optional[UploadFile] = File(None),
    current_user: User = Depends(require_role([ROLE_FARMER])),
    db: Session = Depends(get_db)
):
    resolved_price = farmer_price if farmer_price is not None else price
    resolved_qty = quantity if quantity is not None else quantity_available

    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name
    }

    if resolved_price is None or resolved_price < 0:
        return templates.TemplateResponse(
            "farmer/add_crop.html",
            {
                "request": request,
                "error": "Please enter a valid price per KG (must be 0 or greater).",
                "session": session_data,
                "ai_status": "connected"
            },
            status_code=400
        )

    if resolved_qty is None or resolved_qty <= 0:
        return templates.TemplateResponse(
            "farmer/add_crop.html",
            {
                "request": request,
                "error": "Please enter a valid quantity available (must be greater than 0).",
                "session": session_data,
                "ai_status": "connected"
            },
            status_code=400
        )

    saved_filename = None
    image_full_path = None

    # Handle image upload
    if crop_image and crop_image.filename:
        safe_name = "".join(c for c in crop_image.filename if c.isalnum() or c in "._-")
        filename = f"{current_user.id}_{int(time.time())}_{safe_name}"
        settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        dest_path = settings.UPLOAD_DIR / filename
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(crop_image.file, buffer)
        saved_filename = filename
        image_full_path = str(dest_path)

    # Run OpenCV Analysis
    analysis = AIService.analyze_crop_image(image_full_path, crop_name, resolved_price)

    new_crop = Crop(
        farmer_id=current_user.id,
        crop_name=crop_name.strip(),
        category=category.strip().capitalize(),
        quantity_available=resolved_qty,
        unit="KG",
        farmer_price=resolved_price,
        ai_suggested_price=analysis.get("ai_suggested_price", resolved_price),
        description=description.strip() if description else None,
        crop_image=saved_filename,
        quality_grade=analysis.get("quality_grade", "A"),
        freshness_score=analysis.get("freshness_score", 90.0),
        demand_score=analysis.get("demand_score", 80.0),
        demand_level=analysis.get("demand_level", "Medium"),
        market_suitability=analysis.get("market_suitability", "Good"),
        location=location.strip() if location else (current_user.address or "Madhya Pradesh"),
        status="available" if resolved_qty > 0 else "out_of_stock"
    )
    db.add(new_crop)
    db.flush()

    # Save assessment record
    assessment = CropAssessment(
        crop_id=new_crop.crop_id,
        image_path=saved_filename,
        quality_grade=analysis.get("quality_grade", "A"),
        freshness_score=analysis.get("freshness_score", 90.0),
        uniformity_score=analysis.get("uniformity", 90.0),
        color_distribution=str(analysis.get("metrics", {})),
        defect_percentage=analysis.get("defect_percentage", 0.0),
        suggested_price=analysis.get("ai_suggested_price", resolved_price),
        market_suitability=analysis.get("market_suitability", "Good"),
        assessment_method="OpenCV-ComputerVision"
    )
    db.add(assessment)
    db.commit()

    return RedirectResponse(url="/farmer/manage-crops?success=Crop+added+successfully!", status_code=303)

@router.get("/edit-crop/{crop_id}", response_class=HTMLResponse)
async def edit_crop_page(
    crop_id: int,
    request: Request,
    current_user: User = Depends(require_role([ROLE_FARMER])),
    db: Session = Depends(get_db)
):
    crop = db.query(Crop).filter(Crop.crop_id == crop_id, Crop.farmer_id == current_user.id).first()
    if not crop:
        return RedirectResponse("/farmer/manage-crops", status_code=302)

    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name
    }

    return templates.TemplateResponse(
        "farmer/edit_crop.html",
        {
            "request": request,
            "crop": crop,
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.post("/edit-crop/{crop_id}")
async def edit_crop_action(
    crop_id: int,
    crop_name: str = Form(...),
    category: str = Form(...),
    quantity: Optional[float] = Form(None),
    quantity_available: Optional[float] = Form(None),
    farmer_price: Optional[float] = Form(None),
    price: Optional[float] = Form(None),
    description: Optional[str] = Form(None),
    crop_image: Optional[UploadFile] = File(None),
    current_user: User = Depends(require_role([ROLE_FARMER])),
    db: Session = Depends(get_db)
):
    crop = db.query(Crop).filter(Crop.crop_id == crop_id, Crop.farmer_id == current_user.id).first()
    if not crop:
        raise HTTPException(status_code=404, detail="Crop not found")

    resolved_price = farmer_price if farmer_price is not None else price
    resolved_qty = quantity if quantity is not None else quantity_available

    crop.crop_name = crop_name.strip()
    crop.category = category.strip().capitalize()
    if resolved_qty is not None:
        crop.quantity_available = resolved_qty
        if resolved_qty == 0:
            crop.status = "out_of_stock"
        elif crop.status == "out_of_stock" and resolved_qty > 0:
            crop.status = "available"

    if resolved_price is not None:
        crop.farmer_price = resolved_price

    crop.description = description.strip() if description else None

    if crop_image and crop_image.filename:
        safe_name = "".join(c for c in crop_image.filename if c.isalnum() or c in "._-")
        filename = f"{current_user.id}_{int(time.time())}_{safe_name}"
        settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        dest_path = settings.UPLOAD_DIR / filename
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(crop_image.file, buffer)
        crop.crop_image = filename

    db.commit()
    return RedirectResponse(url="/farmer/manage-crops?success=Crop+updated+successfully!", status_code=303)

@router.get("/delete-crop/{crop_id}")
async def delete_crop_action(
    crop_id: int,
    current_user: User = Depends(require_role([ROLE_FARMER])),
    db: Session = Depends(get_db)
):
    CropService.delete_crop(db, crop_id, current_user.id)
    return RedirectResponse(url="/farmer/manage-crops", status_code=302)

# ---------------- ORDERS & FULFILLMENT ----------------
@router.get("/orders", response_class=HTMLResponse)
async def farmer_orders_page(
    request: Request,
    current_user: User = Depends(require_role([ROLE_FARMER])),
    db: Session = Depends(get_db)
):
    raw_orders = db.query(Order).filter(Order.farmer_id == current_user.id).order_by(desc(Order.order_id)).all()
    formatted = []
    for o in raw_orders:
        formatted.append({
            "order_id": o.order_id,
            "crop_name": o.crop.crop_name if o.crop else f"Crop #{o.crop_id}",
            "quantity": o.quantity,
            "total_amount": o.total_amount,
            "status": o.status,
            "payment_method": o.payment_method,
            "customer_name": o.consumer.full_name if o.consumer else "Customer",
            "delivery_address": o.delivery_address,
            "order_date": format_ist_datetime(o.order_date)
        })

    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name
    }

    return templates.TemplateResponse(
        "farmer/orders.html",
        {
            "request": request,
            "orders": formatted,
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.get("/accept-order/{order_id}")
async def accept_order_action(
    order_id: int,
    current_user: User = Depends(require_role([ROLE_FARMER])),
    db: Session = Depends(get_db)
):
    OrderService.update_order_status(db, order_id, STATUS_ACCEPTED)
    return RedirectResponse(url="/farmer/orders", status_code=302)

@router.get("/reject-order/{order_id}")
async def reject_order_action(
    order_id: int,
    current_user: User = Depends(require_role([ROLE_FARMER])),
    db: Session = Depends(get_db)
):
    OrderService.update_order_status(db, order_id, STATUS_CANCELLED)
    return RedirectResponse(url="/farmer/orders", status_code=302)

# ---------------- TRUST SCORE & WALLET ----------------
@router.get("/trust-score", response_class=HTMLResponse)
async def farmer_trust_score_page(
    request: Request,
    current_user: User = Depends(require_role([ROLE_FARMER])),
    db: Session = Depends(get_db)
):
    score_data = TrustScoreService.calculate_farmer_trust_score(db, current_user.id)
    reviews = db.query(Review).filter(Review.farmer_id == current_user.id).all()

    completed_orders = db.query(Order).filter(
        Order.farmer_id == current_user.id,
        Order.status == STATUS_DELIVERED
    ).count()

    total_orders = db.query(Order).filter(Order.farmer_id == current_user.id).count()
    success_rate = round((completed_orders / total_orders * 100), 1) if total_orders > 0 else 100.0

    farmers = db.query(FarmerProfile).order_by(desc(FarmerProfile.trust_score)).all()
    ranking = 1
    for idx, f in enumerate(farmers, 1):
        if f.farmer_id == current_user.id:
            ranking = idx
            break

    scaled_score = int(score_data["trust_score"] * 20)

    formatted_reviews = []
    for r in reviews:
        formatted_reviews.append({
            "consumer_name": r.consumer.full_name if r.consumer else "Customer",
            "rating": r.rating or 5,
            "review_text": r.review_text or "Great fresh produce!"
        })

    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name
    }

    return templates.TemplateResponse(
        "farmer/trust_score.html",
        {
            "request": request,
            "trust_score": scaled_score,
            "raw_trust_score": score_data["trust_score"],
            "score_breakdown": score_data,
            "reviews": formatted_reviews,
            "total_ratings": score_data["total_reviews"],
            "avg_rating": round(score_data["average_rating"], 1),
            "fulfillment_rate": score_data["fulfillment_percentage"],
            "ranking": ranking,
            "completed_orders": completed_orders,
            "avg_quality": 95,
            "avg_freshness": 96,
            "success_rate": success_rate,
            "chart_labels": ["May", "Jun", "Jul", "Aug", "Sep", "Oct"],
            "chart_data": [70, 75, 80, 85, 90, scaled_score],
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.get("/wallet", response_class=HTMLResponse)
async def farmer_wallet_page(
    request: Request,
    current_user: User = Depends(require_role([ROLE_FARMER])),
    db: Session = Depends(get_db)
):
    wallet = WalletService.get_or_create_wallet(db, current_user.id)
    txs = db.query(WalletTransaction).filter(WalletTransaction.wallet_id == wallet.wallet_id).order_by(desc(WalletTransaction.transaction_id)).all()

    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name
    }

    return templates.TemplateResponse(
        "farmer/wallet.html",
        {
            "request": request,
            "wallet": wallet,
            "transactions": txs,
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.post("/withdraw")
@router.post("/wallet")
async def withdraw_action(
    request: Request,
    amount: float = Form(...),
    current_user: User = Depends(require_role([ROLE_FARMER])),
    db: Session = Depends(get_db)
):
    WalletService.withdraw_funds(db, current_user.id, amount)
    return RedirectResponse(url="/farmer/wallet", status_code=302)

@router.get("/revenue", response_class=HTMLResponse)
@router.get("/revenue-history", response_class=HTMLResponse)
async def revenue_history_page(
    request: Request,
    current_user: User = Depends(require_role([ROLE_FARMER])),
    db: Session = Depends(get_db)
):
    orders = db.query(Order).filter(Order.farmer_id == current_user.id, Order.status == STATUS_DELIVERED).order_by(desc(Order.order_id)).all()
    total_rev = sum(o.total_amount for o in orders)

    revenues = []
    for o in orders:
        selling_price = round(o.total_amount / o.quantity, 2) if o.quantity else 0.0
        revenues.append({
            "order_id": o.order_id,
            "crop_name": o.crop.crop_name if o.crop else f"Crop #{o.crop_id}",
            "quantity": o.quantity,
            "selling_price": selling_price,
            "revenue": round(o.total_amount, 2),
            "date": format_ist_datetime(o.order_date or o.updated_at),
            "status": o.status
        })

    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name
    }

    return templates.TemplateResponse(
        "farmer/revenue_history.html",
        {
            "request": request,
            "orders": orders,
            "revenues": revenues,
            "total_revenue": round(total_rev, 2),
            "session": session_data,
            "ai_status": "connected"
        }
    )

# ---------------- FARMER INBOX ----------------
@router.get("/inbox", response_class=HTMLResponse)
async def farmer_inbox_page(
    request: Request,
    current_user: User = Depends(require_role([ROLE_FARMER])),
    db: Session = Depends(get_db)
):
    orders = db.query(Order).filter(Order.farmer_id == current_user.id).order_by(desc(Order.order_id)).limit(20).all()
    inbox_orders = []
    for o in orders:
        inbox_orders.append({
            "order_id": o.order_id,
            "crop_name": o.crop.crop_name if o.crop else f"Crop #{o.crop_id}",
            "status": o.status,
            "consumer_name": o.consumer.full_name if o.consumer else "Consumer",
            "consumer_phone": o.consumer.phone if o.consumer else "N/A",
            "quantity": o.quantity,
            "total_amount": round(o.total_amount, 2),
        })

    from app.models.logs import WhatsAppLog
    clean_phone = "".join(ch for ch in str(current_user.phone or "") if ch.isdigit())
    logs = []
    if clean_phone:
        last10 = clean_phone[-10:]
        logs = db.query(WhatsAppLog).filter(
            (WhatsAppLog.recipient_phone.like(f"%{last10}")) | (WhatsAppLog.recipient_role == "Farmer")
        ).order_by(desc(WhatsAppLog.log_id)).limit(20).all()
    else:
        logs = db.query(WhatsAppLog).filter(WhatsAppLog.recipient_role == "Farmer").order_by(desc(WhatsAppLog.log_id)).limit(20).all()

    notifications = []
    for l in logs:
        notifications.append({
            "title": l.message_type or "WhatsApp Notification",
            "status": "Delivered" if l.status in ("Sent", "Delivered") else ("Failed" if l.status == "Failed" else "Pending"),
            "message": l.message_body,
            "phone": l.recipient_phone,
            "created_at": format_ist_datetime(l.created_at)
        })

    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name
    }

    return templates.TemplateResponse(
        "farmer/inbox.html",
        {
            "request": request,
            "inbox_orders": inbox_orders,
            "notifications": notifications,
            "session": session_data,
            "ai_status": "connected"
        }
    )
