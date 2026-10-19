import os
import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, Depends, Form, HTTPException, status, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.templates_config import templates
from app.models.user import User, DeliveryPartnerProfile
from app.models.order import Order
from app.models.logs import WhatsAppLog, Notification
from app.services.order_service import OrderService
from app.services.delivery_tracking_service import DeliveryTrackingService
from app.services.geocoding_service import GeocodingService
from app.dependencies.auth import require_role
from app.utils.constants import (
    ROLE_DELIVERY,
    STATUS_PENDING,
    STATUS_ACCEPTED,
    STATUS_ASSIGNED,
    STATUS_PICKED_UP,
    STATUS_IN_TRANSIT,
    STATUS_DELIVERED,
    STEP_ACCEPTED,
    STEP_HEADING_TO_FARMER,
    STEP_PACKING,
    STEP_PACKAGE_PICKED,
    STEP_OUT_FOR_DELIVERY,
    STEP_ABOUT_TO_ARRIVE,
    STEP_ARRIVED,
    STEP_DELIVERED,
    DELIVERY_STEPS_FLOW,
    DELIVERY_STEP_DESCRIPTIONS,
)
from app.utils.ist_time import format_ist_datetime, get_ist_now

router = APIRouter(prefix="/delivery", tags=["Delivery Partner"])


# ---------------- SWIGGY/ZOMATO/BLINKIT STYLE RIDER DASHBOARD ----------------
@router.get("/dashboard", response_class=HTMLResponse)
async def delivery_dashboard(
    request: Request,
    current_user: User = Depends(require_role([ROLE_DELIVERY])),
    db: Session = Depends(get_db)
):
    profile = current_user.delivery_profile
    is_online = bool(profile.is_online) if profile and profile.is_online is not None else True

    # Count statistics
    assigned_orders_count = db.query(Order).filter(
        Order.delivery_partner_id == current_user.id,
        Order.status.in_([STATUS_ASSIGNED, STATUS_ACCEPTED, STATUS_PICKED_UP, STATUS_IN_TRANSIT, "Out For Delivery"])
    ).count()

    completed_orders_count = db.query(Order).filter(
        Order.delivery_partner_id == current_user.id,
        Order.status == STATUS_DELIVERED
    ).count()

    earnings = completed_orders_count * 50.0  # ₹50 per delivery base earning
    rating = profile.rating if profile else 5.0
    vehicle_type = profile.vehicle_type if profile and profile.vehicle_type else "Electric Scooter / Bike"
    license_number = profile.license_number if profile and profile.license_number else "DL-MP09-2024-8842"

    # Find the single most relevant active delivery for the live workspace
    active_order_obj = db.query(Order).filter(
        Order.delivery_partner_id == current_user.id,
        Order.status.in_([STATUS_ASSIGNED, STATUS_ACCEPTED, STATUS_PICKED_UP, STATUS_IN_TRANSIT, "Out For Delivery"])
    ).order_by(desc(Order.order_id)).first()

    active_job_telemetry = None
    if active_order_obj:
        active_job_telemetry = DeliveryTrackingService.get_live_tracking_data(db, active_order_obj.order_id)

    # All active deliveries list
    raw_active = db.query(Order).filter(
        Order.delivery_partner_id == current_user.id,
        Order.status.in_([STATUS_ASSIGNED, STATUS_ACCEPTED, STATUS_PICKED_UP, STATUS_IN_TRANSIT, "Out For Delivery"])
    ).all()

    active_deliveries = []
    for o in raw_active:
        active_deliveries.append({
            "order_id": o.order_id,
            "crop_name": o.crop.crop_name if o.crop else "Produce",
            "quantity": o.quantity,
            "unit": o.crop.unit if o.crop else "KG",
            "farmer_name": o.farmer.full_name if o.farmer else "Farmer",
            "consumer_name": o.consumer.full_name if o.consumer else "Consumer",
            "consumer_address": o.delivery_address,
            "total_amount": o.total_amount,
            "status": o.status,
            "delivery_step": o.delivery_step or "rider_accepted",
            "package_photo": o.package_photo,
        })

    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name
    }

    return templates.TemplateResponse(
        "delivery/delivery_dashboard.html",
        {
            "request": request,
            "delivery_name": current_user.full_name,
            "rider_phone": current_user.phone or "N/A",
            "vehicle_type": vehicle_type,
            "license_number": license_number,
            "is_online": is_online,
            "assigned_orders": assigned_orders_count,
            "completed_orders": completed_orders_count,
            "earnings": earnings,
            "rating": rating,
            "active_job": active_job_telemetry,
            "active_deliveries": active_deliveries,
            "steps_flow": DELIVERY_STEPS_FLOW,
            "step_descriptions": DELIVERY_STEP_DESCRIPTIONS,
            "google_maps_api_key": os.getenv("GOOGLE_MAPS_API_KEY", "").strip(),
            "session": session_data,
            "ai_status": "connected"
        }
    )


# ---------------- REAL-TIME INCOMING BROADCAST FOR MODAL ALERT ----------------
@router.get("/api/available-broadcast")
async def get_available_broadcast(
    current_user: User = Depends(require_role([ROLE_DELIVERY])),
    db: Session = Depends(get_db)
):
    """
    Polled by the rider dashboard every 2.5 seconds.
    If rider is online and there are unassigned orders, returns order data for popup alert.
    """
    profile = current_user.delivery_profile
    if profile and profile.is_online is False:
        return {"orders": [], "is_online": False}

    orders = DeliveryTrackingService.get_available_orders_for_broadcast(db, current_user.id)
    return {"orders": orders, "is_online": True}


# ---------------- ACCEPT / DECLINE BROADCAST ORDER ----------------
@router.post("/api/accept/{order_id}")
async def api_accept_delivery_order(
    order_id: int,
    current_user: User = Depends(require_role([ROLE_DELIVERY])),
    db: Session = Depends(get_db)
):
    success, msg, order = DeliveryTrackingService.accept_order(db, order_id, current_user.id)
    if not success:
        return JSONResponse(status_code=400, content={"success": False, "message": msg})
    return JSONResponse(content={
        "success": True,
        "message": msg,
        "order_id": order_id,
        "redirect_url": f"/delivery/dashboard"
    })


@router.post("/api/decline/{order_id}")
async def api_decline_delivery_order(
    order_id: int,
    current_user: User = Depends(require_role([ROLE_DELIVERY])),
    db: Session = Depends(get_db)
):
    # Order remains unassigned for other riders
    return JSONResponse(content={"success": True, "message": f"Order #{order_id} dismissed."})


# ---------------- STEP PROGRESSION & ACTIONS ----------------
@router.post("/api/advance-step")
async def api_advance_delivery_step(
    order_id: int = Form(...),
    next_step: str = Form(...),
    otp: Optional[str] = Form(None),
    current_user: User = Depends(require_role([ROLE_DELIVERY])),
    db: Session = Depends(get_db)
):
    """
    Advances delivery step milestone.
    Blocks 'out_for_delivery' unless a package photo has been uploaded!
    """
    success, msg = DeliveryTrackingService.advance_step(db, order_id, current_user.id, next_step, entered_otp=otp)
    if not success:
        return JSONResponse(status_code=400, content={"success": False, "message": msg})
    return JSONResponse(content={"success": True, "message": msg, "current_step": next_step})


# ---------------- PACKAGE PHOTO UPLOAD (SENT TO HEAD OFFICE) ----------------
@router.post("/api/upload-package-photo")
async def api_upload_package_photo(
    order_id: int = Form(...),
    package_image: UploadFile = File(...),
    current_user: User = Depends(require_role([ROLE_DELIVERY])),
    db: Session = Depends(get_db)
):
    """
    Rider uploads package photo at the farm.
    Saves to /uploads/packages/, notifies Head Office (Admin), and unlocks 'Delivering to Customer' button.
    """
    content = await package_image.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty image file provided.")

    success, msg, photo_url = DeliveryTrackingService.upload_package_photo(
        db, order_id, current_user.id, content, package_image.filename
    )

    if not success:
        return JSONResponse(status_code=400, content={"success": False, "message": msg})

    return JSONResponse(content={
        "success": True,
        "message": msg,
        "photo_url": photo_url,
        "unlocked_step": STEP_OUT_FOR_DELIVERY
    })


# ---------------- LIVE GPS UPDATE FROM RIDER ----------------
@router.post("/api/update-gps")
async def api_update_rider_gps(
    latitude: float = Form(...),
    longitude: float = Form(...),
    order_id: Optional[int] = Form(None),
    speed: Optional[float] = Form(0.0),
    current_user: User = Depends(require_role([ROLE_DELIVERY])),
    db: Session = Depends(get_db)
):
    updated = DeliveryTrackingService.update_rider_gps(
        db, current_user.id, order_id, latitude, longitude, speed or 0.0
    )
    return JSONResponse(content={"success": updated})


# ---------------- TOGGLE ONLINE / OFFLINE STATUS ----------------
@router.post("/api/toggle-online")
async def api_toggle_online(
    current_user: User = Depends(require_role([ROLE_DELIVERY])),
    db: Session = Depends(get_db)
):
    prof = current_user.delivery_profile
    if not prof:
        prof = DeliveryPartnerProfile(delivery_id=current_user.id, is_online=True)
        db.add(prof)
    else:
        prof.is_online = not bool(prof.is_online)

    db.commit()
    return JSONResponse(content={"success": True, "is_online": bool(prof.is_online)})


# ---------------- LIVE RIDER NAVIGATION VIEW ----------------
@router.get("/tracking/{order_id}", response_class=HTMLResponse)
@router.get("/orders/{order_id}/navigate", response_class=HTMLResponse)
async def delivery_navigation_view(
    order_id: int,
    request: Request,
    current_user: User = Depends(require_role([ROLE_DELIVERY])),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    telemetry = DeliveryTrackingService.get_live_tracking_data(db, order_id)
    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name
    }

    return templates.TemplateResponse(
        "delivery/tracking.html",
        {
            "request": request,
            "order": order,
            "telemetry": telemetry,
            "google_maps_api_key": os.getenv("GOOGLE_MAPS_API_KEY", "").strip(),
            "session": session_data,
            "ai_status": "connected"
        }
    )


# ---------------- LEGACY COMPATIBILITY ROUTES ----------------
@router.get("/assigned-orders", response_class=HTMLResponse)
@router.get("/orders", response_class=HTMLResponse)
async def assigned_orders_page(
    request: Request,
    current_user: User = Depends(require_role([ROLE_DELIVERY])),
    db: Session = Depends(get_db)
):
    raw_orders = db.query(Order).filter(
        Order.delivery_partner_id == current_user.id,
        Order.status.in_([STATUS_ASSIGNED, STATUS_ACCEPTED, STATUS_PICKED_UP, STATUS_IN_TRANSIT, "Out For Delivery"])
    ).order_by(desc(Order.order_id)).all()

    orders_list = []
    for o in raw_orders:
        orders_list.append({
            "order_id": o.order_id,
            "crop_name": o.crop.crop_name if o.crop else f"Crop #{o.crop_id}",
            "quantity": o.quantity,
            "total_amount": o.total_amount,
            "status": o.status,
            "delivery_step": o.delivery_step or "rider_accepted",
            "package_photo": o.package_photo,
            "farmer_name": o.farmer.full_name if o.farmer else "Farmer",
            "farmer_phone": o.farmer.phone if o.farmer else "",
            "farmer_address": o.farmer.address if o.farmer else (o.crop.location if o.crop else "Madhya Pradesh"),
            "consumer_name": o.consumer.full_name if o.consumer else "Customer",
            "consumer_phone": o.consumer.phone if o.consumer else "",
            "consumer_address": o.delivery_address,
            "payment_method": o.payment_method
        })

    session_data = {"user_id": current_user.id, "role": current_user.role, "user_name": current_user.full_name}

    return templates.TemplateResponse(
        "delivery/assigned_orders.html",
        {
            "request": request,
            "orders": orders_list,
            "session": session_data,
            "ai_status": "connected"
        }
    )


@router.get("/available-orders", response_class=HTMLResponse)
async def available_orders_page(
    request: Request,
    current_user: User = Depends(require_role([ROLE_DELIVERY])),
    db: Session = Depends(get_db)
):
    unassigned = DeliveryTrackingService.get_available_orders_for_broadcast(db, current_user.id)
    session_data = {"user_id": current_user.id, "role": current_user.role, "user_name": current_user.full_name}

    return templates.TemplateResponse(
        "delivery/available_orders.html",
        {
            "request": request,
            "orders": unassigned,
            "session": session_data,
            "ai_status": "connected"
        }
    )


@router.get("/accept/{order_id}")
async def accept_delivery_order_legacy(
    order_id: int,
    current_user: User = Depends(require_role([ROLE_DELIVERY])),
    db: Session = Depends(get_db)
):
    DeliveryTrackingService.accept_order(db, order_id, current_user.id)
    return RedirectResponse(url="/delivery/dashboard", status_code=302)


@router.post("/update-status")
async def update_delivery_status_legacy(
    request: Request,
    order_id: int = Form(...),
    status: str = Form(...),
    current_user: User = Depends(require_role([ROLE_DELIVERY])),
    db: Session = Depends(get_db)
):
    clean_status = status.strip()
    if clean_status == "Out For Delivery":
        clean_status = STATUS_IN_TRANSIT
    OrderService.update_order_status(db, order_id, clean_status)
    return RedirectResponse(url="/delivery/dashboard", status_code=302)


@router.get("/history", response_class=HTMLResponse)
async def delivery_history_page(
    request: Request,
    current_user: User = Depends(require_role([ROLE_DELIVERY])),
    db: Session = Depends(get_db)
):
    completed = db.query(Order).filter(
        Order.delivery_partner_id == current_user.id,
        Order.status == STATUS_DELIVERED
    ).order_by(desc(Order.order_id)).all()

    orders_list = []
    total_earnings = len(completed) * 50.0
    for o in completed:
        orders_list.append({
            "order_id": o.order_id,
            "crop_name": o.crop.crop_name if o.crop else f"Crop #{o.crop_id}",
            "quantity": o.quantity,
            "total_amount": o.total_amount,
            "delivered_date": format_ist_datetime(o.updated_at),
            "consumer_address": o.delivery_address,
            "package_photo": o.package_photo,
            "fee": 50.0
        })

    session_data = {"user_id": current_user.id, "role": current_user.role, "user_name": current_user.full_name}

    return templates.TemplateResponse(
        "delivery/history.html",
        {
            "request": request,
            "orders": orders_list,
            "total_earnings": total_earnings,
            "session": session_data,
            "ai_status": "connected"
        }
    )


@router.get("/inbox", response_class=HTMLResponse)
async def delivery_inbox_page(
    request: Request,
    current_user: User = Depends(require_role([ROLE_DELIVERY])),
    db: Session = Depends(get_db)
):
    assigned = db.query(Order).filter(
        Order.delivery_partner_id == current_user.id
    ).order_by(desc(Order.order_id)).limit(20).all()

    assigned_jobs = []
    for o in assigned:
        assigned_jobs.append({
            "order_id": o.order_id,
            "crop_name": o.crop.crop_name if o.crop else f"Crop #{o.crop_id}",
            "status": o.status,
            "delivery_step": o.delivery_step or "assigned",
            "farmer_name": o.farmer.full_name if o.farmer else "Farmer",
            "farmer_phone": o.farmer.phone if o.farmer else "N/A",
            "farmer_address": o.farmer.address if o.farmer else (o.crop.location if o.crop else "Madhya Pradesh"),
            "consumer_name": o.consumer.full_name if o.consumer else "Customer",
            "consumer_phone": o.consumer.phone if o.consumer else "N/A",
            "consumer_address": o.delivery_address or "Delivery Address",
        })

    clean_phone = "".join(ch for ch in str(current_user.phone or "") if ch.isdigit())
    logs = []
    if clean_phone:
        last10 = clean_phone[-10:]
        logs = db.query(WhatsAppLog).filter(
            (WhatsAppLog.recipient_phone.like(f"%{last10}")) | (WhatsAppLog.recipient_role == "Delivery")
        ).order_by(desc(WhatsAppLog.log_id)).limit(20).all()
    else:
        logs = db.query(WhatsAppLog).filter(WhatsAppLog.recipient_role == "Delivery").order_by(desc(WhatsAppLog.log_id)).limit(20).all()

    notifications = []
    for l in logs:
        notifications.append({
            "title": l.message_type or "Delivery Notification",
            "status": "Delivered" if l.status in ("Sent", "Delivered") else ("Failed" if l.status == "Failed" else "Pending"),
            "message": l.message_body,
            "phone": l.recipient_phone,
            "created_at": format_ist_datetime(l.created_at)
        })

    session_data = {"user_id": current_user.id, "role": current_user.role, "user_name": current_user.full_name}

    return templates.TemplateResponse(
        "delivery/inbox.html",
        {
            "request": request,
            "assigned_jobs": assigned_jobs,
            "notifications": notifications,
            "session": session_data,
            "ai_status": "connected"
        }
    )
