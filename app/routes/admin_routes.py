from typing import Optional, List, Dict, Any, Tuple
from fastapi import APIRouter, Request, Depends, Form, HTTPException, status, Response, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from app.database import get_db
from app.templates_config import templates
from app.models.user import User, FarmerProfile, ConsumerProfile, DeliveryPartnerProfile
from app.models.crop import Crop, CropAssessment
from app.models.order import Order, CartItem
from app.models.review import Review
from app.models.wallet import Wallet, WalletTransaction
from app.models.logs import WhatsAppLog, AdminActivityLog, PlatformSetting, Notification
from app.services.excel_service import ExcelService
from app.services.order_service import OrderService
from app.services.ai_service import AIService
from app.dependencies.auth import require_role
from app.utils.constants import (
    ROLE_ADMIN,
    STATUS_DELIVERED,
    STATUS_PENDING,
    STATUS_CANCELLED,
    STATUS_ASSIGNED,
    STATUS_ACCEPTED,
    STATUS_PICKED_UP,
    STATUS_IN_TRANSIT,
)
from app.utils.ist_time import format_ist_datetime

router = APIRouter(prefix="/admin", tags=["Administrator"])

# ---------------- DASHBOARD ----------------
@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        from app.services.excel_credential_service import ExcelCredentialService
        ExcelCredentialService.check_and_sync_if_modified(db)
    except Exception:
        pass

    total_farmers = db.query(User).filter(User.role == "farmer").count()
    total_consumers = db.query(User).filter(User.role == "consumer").count()
    total_delivery = db.query(User).filter(User.role == "delivery").count()
    total_users = db.query(User).count()

    total_crops = db.query(Crop).count()
    total_orders = db.query(Order).count()

    delivered_orders = db.query(Order).filter(Order.status == STATUS_DELIVERED).count()
    pending_orders = db.query(Order).filter(Order.status == STATUS_PENDING).count()
    cancelled_orders = db.query(Order).filter(Order.status == STATUS_CANCELLED).count()

    revenue = db.query(func.sum(Order.total_amount)).filter(Order.status == STATUS_DELIVERED).scalar() or 0.0
    revenue = round(float(revenue), 2)

    # Commission settings
    comm_setting = db.query(PlatformSetting).filter(PlatformSetting.key == "commission_rate").first()
    comm_rate = float(comm_setting.value) if comm_setting else 0.05
    comm_earned = round(revenue * comm_rate, 2)
    farmer_earnings = round(revenue - comm_earned, 2)

    recent_orders = db.query(Order).order_by(desc(Order.order_id)).limit(10).all()
    recent_activity = []
    for o in recent_orders:
        recent_activity.append({
            "order_id": o.order_id,
            "crop_name": o.crop.crop_name if o.crop else f"Crop #{o.crop_id}",
            "customer_name": o.consumer.full_name if o.consumer else "Consumer",
            "farmer_name": o.farmer.full_name if o.farmer else "Farmer",
            "amount": o.total_amount,
            "status": o.status,
            "date": format_ist_datetime(o.order_date)
        })

    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name
    }

    return templates.TemplateResponse(
        "admin/admin_dashboard.html",
        {
            "request": request,
            "total_farmers": total_farmers,
            "total_consumers": total_consumers,
            "total_delivery": total_delivery,
            "total_users": total_users,
            "total_crops": total_crops,
            "total_orders": total_orders,
            "delivered_orders": delivered_orders,
            "pending_orders": pending_orders,
            "cancelled_orders": cancelled_orders,
            "revenue": revenue,
            "commission_rate": comm_rate,
            "comm_earned": comm_earned,
            "farmer_earnings": farmer_earnings,
            "recent_orders": recent_activity,
            "chart_labels": ["Jun", "Jul", "Aug", "Sep", "Oct"],
            "chart_orders": [0, 0, 0, 0, total_orders],
            "chart_revenue": [0, 0, 0, 0, revenue],
            "months": ["Jun", "Jul", "Aug", "Sep", "Oct"],
            "orders": [0, 0, 0, 0, total_orders],
            "revenues": [0, 0, 0, 0, revenue],
            "ai_enabled": True,
            "session": session_data,
            "ai_status": "connected"
        }
    )

# ---------------- MANAGE USERS ----------------
# ---------------- MANAGE USERS ----------------
def safely_delete_crop(db: Session, crop_id: int) -> bool:
    crop = db.query(Crop).filter(Crop.crop_id == crop_id).first()
    if not crop:
        return False

    # 1. Delete associated AI analysis
    db.query(CropAssessment).filter(CropAssessment.crop_id == crop_id).delete(synchronize_session=False)

    # 2. Delete cart items referencing this crop
    db.query(CartItem).filter(CartItem.crop_id == crop_id).delete(synchronize_session=False)

    # 3. Handle reviews on this crop
    db.query(Review).filter(Review.crop_id == crop_id).delete(synchronize_session=False)

    # 4. Handle orders referencing this crop
    orders = db.query(Order).filter(Order.crop_id == crop_id).all()
    order_ids = [o.order_id for o in orders]
    if order_ids:
        # Delete reviews for these orders
        db.query(Review).filter(Review.order_id.in_(order_ids)).delete(synchronize_session=False)
        # Unlink order_id from wallet transactions
        db.query(WalletTransaction).filter(WalletTransaction.order_id.in_(order_ids)).update(
            {"order_id": None}, synchronize_session=False
        )
        # Delete the orders
        db.query(Order).filter(Order.order_id.in_(order_ids)).delete(synchronize_session=False)

    # 5. Delete the crop itself
    db.delete(crop)
    db.commit()
    return True


def safely_delete_user(db: Session, user_id: int, current_admin_id: int) -> Tuple[bool, str]:
    if user_id == current_admin_id:
        return False, "You cannot delete your own administrator account."

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return False, "User not found."

    user_name = user.full_name
    try:
        # 1. Clean notifications
        db.query(Notification).filter(Notification.user_id == user_id).delete(synchronize_session=False)

        # 2. Clean cart items
        db.query(CartItem).filter(CartItem.consumer_id == user_id).delete(synchronize_session=False)

        # 3. Clean reviews written or received
        db.query(Review).filter(
            (Review.consumer_id == user_id) | (Review.farmer_id == user_id)
        ).delete(synchronize_session=False)

        # 4. Handle orders where user is consumer, farmer, or delivery partner
        orders = db.query(Order).filter(
            (Order.consumer_id == user_id) | (Order.farmer_id == user_id) | (Order.delivery_partner_id == user_id)
        ).all()
        order_ids = [o.order_id for o in orders]
        if order_ids:
            db.query(Review).filter(Review.order_id.in_(order_ids)).delete(synchronize_session=False)
            db.query(WalletTransaction).filter(WalletTransaction.order_id.in_(order_ids)).update(
                {"order_id": None}, synchronize_session=False
            )
            db.query(Order).filter(Order.order_id.in_(order_ids)).delete(synchronize_session=False)

        # 5. Handle crops if user is a farmer
        crops = db.query(Crop).filter(Crop.farmer_id == user_id).all()
        for c in crops:
            safely_delete_crop(db, c.crop_id)

        # 6. Wallet & Wallet transactions
        user_wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()
        if user_wallet:
            db.query(WalletTransaction).filter(WalletTransaction.wallet_id == user_wallet.wallet_id).delete(synchronize_session=False)
            db.delete(user_wallet)

        # 7. Role Profiles
        db.query(FarmerProfile).filter(FarmerProfile.farmer_id == user_id).delete(synchronize_session=False)
        db.query(ConsumerProfile).filter(ConsumerProfile.consumer_id == user_id).delete(synchronize_session=False)
        db.query(DeliveryPartnerProfile).filter(DeliveryPartnerProfile.delivery_id == user_id).delete(synchronize_session=False)

        # 8. Activity logs
        db.query(AdminActivityLog).filter(AdminActivityLog.admin_id == user_id).delete(synchronize_session=False)

        # 9. Delete user record
        db.delete(user)
        db.commit()
        return True, f"User '{user_name}' and all associated records deleted successfully."

    except Exception as e:
        db.rollback()
        return False, f"Failed to delete user: {str(e)}"


@router.get("/users", response_class=HTMLResponse)
async def admin_users_page(
    request: Request,
    success: Optional[str] = None,
    error: Optional[str] = None,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        from app.services.excel_credential_service import ExcelCredentialService
        ExcelCredentialService.check_and_sync_if_modified(db)
    except Exception:
        pass

    users = db.query(User).order_by(User.id).all()
    session_data = {"user_id": current_user.id, "role": current_user.role, "user_name": current_user.full_name}

    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "users": users,
            "success": success,
            "error": error,
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.get("/user/{user_id}", response_class=HTMLResponse)
@router.get("/users/{user_id}", response_class=HTMLResponse)
async def admin_view_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url="/admin/users", status_code=302)

    prof = None
    if user.role == "farmer":
        prof = user.farmer_profile
    elif user.role == "delivery":
        prof = user.delivery_profile
    elif user.role == "consumer":
        prof = user.consumer_profile

    user_dict = {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "phone": user.phone,
        "role": user.role,
        "address": user.address,
        "status": user.status,
        "created_at_ist": format_ist_datetime(user.created_at)
    }
    session_data = {"user_id": current_user.id, "role": current_user.role, "user_name": current_user.full_name}

    return templates.TemplateResponse(
        "admin/user_detail.html",
        {
            "request": request,
            "user": user_dict,
            "profile": prof,
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.get("/toggle-user/{user_id}")
@router.get("/users/{user_id}/toggle-status")
async def toggle_user_status(
    user_id: int,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if user and user.id != current_user.id:
        user.status = "Inactive" if user.status == "Active" else "Active"
        db.commit()
        return RedirectResponse(url="/admin/users?success=User+status+updated+successfully!", status_code=302)
    return RedirectResponse(url="/admin/users", status_code=302)

@router.get("/delete-user/{user_id}")
@router.get("/users/{user_id}/delete")
async def admin_delete_user(
    user_id: int,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    import urllib.parse
    success, msg = safely_delete_user(db, user_id, current_user.id)
    encoded = urllib.parse.quote_plus(msg)
    param = f"success={encoded}" if success else f"error={encoded}"
    return RedirectResponse(url=f"/admin/users?{param}", status_code=302)

# ---------------- MANAGE CROPS ----------------
@router.get("/crops", response_class=HTMLResponse)
@router.get("/products", response_class=HTMLResponse)
async def admin_crops_page(
    request: Request,
    success: Optional[str] = None,
    error: Optional[str] = None,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    crops = db.query(Crop).order_by(desc(Crop.crop_id)).all()
    formatted = []
    for c in crops:
        img = c.crop_image or ""
        if img and not img.startswith("http"):
            img = f"/static/uploads/crop_images/{img}"
        formatted.append({
            "crop_id": c.crop_id,
            "crop_name": c.crop_name,
            "category": c.category,
            "crop_image": img or "https://images.unsplash.com/photo-1546470427-e5ac89cd0b3b",
            "quantity_available": c.quantity_available,
            "farmer_price": c.farmer_price,
            "farmer_name": c.farmer.full_name if c.farmer else "Farmer",
            "farmer_phone": c.farmer.phone if c.farmer else "N/A",
            "farmer_address": c.farmer.address if c.farmer else "N/A",
            "quality_grade": c.quality_grade,
            "freshness_score": c.freshness_score,
            "demand_level": c.demand_level,
            "status": c.status
        })

    session_data = {"user_id": current_user.id, "role": current_user.role, "user_name": current_user.full_name}
    return templates.TemplateResponse(
        "admin/crops.html",
        {
            "request": request,
            "crops": formatted,
            "success": success,
            "error": error,
            "session": session_data,
            "ai_enabled": True,
            "ai_status": "connected"
        }
    )

@router.get("/approve-crop/{crop_id}")
@router.get("/crops/{crop_id}/approve")
async def admin_approve_crop(
    crop_id: int,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    crop = db.query(Crop).filter(Crop.crop_id == crop_id).first()
    if crop:
        crop.status = "available"
        db.add(Notification(
            user_id=crop.farmer_id,
            title="Crop Listing Approved",
            message=f"Your crop listing '{crop.crop_name}' has been approved by admin and is now live on the marketplace."
        ))
        db.commit()
        return RedirectResponse(url="/admin/crops?success=Crop+approved+successfully!", status_code=302)
    return RedirectResponse(url="/admin/crops?error=Crop+not+found", status_code=302)

@router.get("/reject-crop/{crop_id}")
@router.get("/crops/{crop_id}/reject")
async def admin_reject_crop(
    crop_id: int,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    crop = db.query(Crop).filter(Crop.crop_id == crop_id).first()
    if crop:
        crop.status = "rejected"
        db.add(Notification(
            user_id=crop.farmer_id,
            title="Crop Listing Rejected",
            message=f"Your crop listing '{crop.crop_name}' was reviewed and rejected by admin."
        ))
        db.commit()
        return RedirectResponse(url="/admin/crops?success=Crop+rejected+successfully!", status_code=302)
    return RedirectResponse(url="/admin/crops?error=Crop+not+found", status_code=302)

@router.get("/delete-crop/{crop_id}")
@router.get("/crops/{crop_id}/delete")
async def admin_delete_crop(
    crop_id: int,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    success = safely_delete_crop(db, crop_id)
    if success:
        return RedirectResponse(url="/admin/crops?success=Crop+deleted+successfully!", status_code=302)
    return RedirectResponse(url="/admin/crops?error=Crop+not+found+or+could+not+be+deleted", status_code=302)


# ---------------- MANAGE ORDERS ----------------
@router.get("/orders", response_class=HTMLResponse)
async def admin_orders_page(
    request: Request,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    raw_orders = db.query(Order).order_by(desc(Order.order_id)).all()
    delivery_partners = db.query(User).filter(User.role == "delivery", User.status == "Active").all()

    orders_list = []
    for o in raw_orders:
        orders_list.append({
            "order_id": o.order_id,
            "crop_name": o.crop.crop_name if o.crop else f"Crop #{o.crop_id}",
            "quantity": o.quantity,
            "total_amount": o.total_amount,
            "status": o.status,
            "order_date": format_ist_datetime(o.order_date),
            "consumer_name": o.consumer.full_name if o.consumer else "Customer",
            "consumer_phone": o.consumer.phone if o.consumer else "N/A",
            "farmer_name": o.farmer.full_name if o.farmer else "Farmer",
            "farmer_phone": o.farmer.phone if o.farmer else "N/A",
            "delivery_partner_id": o.delivery_partner_id,
            "delivery_partner": o.delivery_partner.full_name if o.delivery_partner else "Pending Assignment",
            "delivery_address": o.delivery_address,
            "payment_method": o.payment_method
        })

    session_data = {"user_id": current_user.id, "role": current_user.role, "user_name": current_user.full_name}
    return templates.TemplateResponse(
        "admin/orders.html",
        {
            "request": request,
            "orders": orders_list,
            "delivery_partners": delivery_partners,
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.post("/orders/assign")
async def admin_assign_delivery(
    request: Request,
    order_id: int = Form(...),
    delivery_partner_id: int = Form(...),
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    OrderService.update_order_status(db, order_id, "Assigned", delivery_partner_id=delivery_partner_id)
    return RedirectResponse(url="/admin/orders", status_code=302)

# ---------------- REPORTS & EXCEL EXPORTS ----------------
@router.get("/reports", response_class=HTMLResponse)
async def admin_reports_page(
    request: Request,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    total_orders = db.query(Order).count()
    total_crops = db.query(Crop).count()
    revenue = db.query(func.sum(Order.total_amount)).filter(Order.status == STATUS_DELIVERED).scalar() or 0.0

    farmers = db.query(User).filter(User.role == "farmer").all()
    top_farmers = []
    for idx, f in enumerate(farmers, 1):
        prof = f.farmer_profile
        top_farmers.append({
            "ranking": idx,
            "farmer_name": f.full_name,
            "farmer_phone": f.phone,
            "farmer_address": f.address,
            "trust_score": round(prof.trust_score, 1) if prof else 5.0,
            "total_orders": prof.total_orders if prof else 0,
            "total_sales": round(prof.total_sales, 2) if prof else 0.0
        })
    top_farmers.sort(key=lambda x: x["total_sales"], reverse=True)

    session_data = {"user_id": current_user.id, "role": current_user.role, "user_name": current_user.full_name}
    return templates.TemplateResponse(
        "admin/reports.html",
        {
            "request": request,
            "total_orders": total_orders,
            "total_crops": total_crops,
            "revenue": round(float(revenue), 2),
            "top_farmers": top_farmers,
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.get("/reports/export/users")
@router.get("/export/users")
async def export_users_excel(
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    stream = ExcelService.export_users(db)
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=users.xlsx"}
    )

@router.get("/reports/export/crops")
@router.get("/export/crops")
async def export_crops_excel(
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    stream = ExcelService.export_crops(db)
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=farmer_crops.xlsx"}
    )

@router.get("/reports/export/orders")
@router.get("/export/orders")
async def export_orders_excel(
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    stream = ExcelService.export_orders(db)
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=orders.xlsx"}
    )

# ---------------- EXCEL REGISTRATION CREDENTIALS CONTROL ----------------
@router.get("/excel/credentials/download")
async def download_credentials_excel(
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    from fastapi.responses import FileResponse
    from app.services.excel_credential_service import ExcelCredentialService, PRIMARY_EXCEL_PATH
    if not PRIMARY_EXCEL_PATH.exists():
        ExcelCredentialService.initialize_or_export_all(db)
    return FileResponse(
        path=str(PRIMARY_EXCEL_PATH),
        filename="users_credentials.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@router.get("/excel/credentials/sync")
@router.post("/excel/credentials/sync")
async def sync_credentials_excel(
    request: Request,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    from app.services.excel_credential_service import ExcelCredentialService
    result = ExcelCredentialService.sync_excel_to_db(db, force=True)
    msg = f"Excel Sync Complete: {result.get('updated', 0)} updated, {result.get('created', 0)} created, {result.get('deleted', 0)} deleted."
    if result.get("errors"):
        msg += f" (Note: {', '.join(result['errors'][:2])})"
    import urllib.parse
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse(content={"success": True, "message": msg, "details": result})
    return RedirectResponse(url=f"/admin/users?success={urllib.parse.quote_plus(msg)}", status_code=303)

@router.post("/excel/credentials/upload")
async def upload_credentials_excel(
    request: Request,
    excel_file: UploadFile = File(...),
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    from app.services.excel_credential_service import ExcelCredentialService, PRIMARY_EXCEL_PATH
    import urllib.parse
    content = await excel_file.read()

    # 1. Sync directly from uploaded content in-memory so database updates even if file on disk is locked!
    result = ExcelCredentialService.sync_bytes_to_db(content, db)

    # 2. Try to write to disk if possible, but never crash if Excel has it open
    try:
        with open(PRIMARY_EXCEL_PATH, "wb") as f:
            f.write(content)
    except PermissionError:
        pass

    msg = f"Excel credentials synced: {result.get('updated', 0)} user(s) updated, {result.get('created', 0)} added, {result.get('deleted', 0)} deleted."
    return RedirectResponse(url=f"/admin/users?success={urllib.parse.quote_plus(msg)}", status_code=303)


# ---------------- WHATSAPP LOGS & NOTIFICATIONS ----------------
@router.get("/notifications", response_class=HTMLResponse)
async def admin_notifications_page(
    request: Request,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    logs = db.query(WhatsAppLog).order_by(desc(WhatsAppLog.log_id)).limit(100).all()
    formatted = []
    for l in logs:
        formatted.append({
            "log_id": l.log_id,
            "order_id": l.order_id,
            "recipient_role": l.recipient_role.capitalize(),
            "recipient_phone": l.recipient_phone,
            "message_type": l.message_type.replace("_", " ").title(),
            "message_body": l.message_body,
            "send_mode": l.send_mode,
            "status": l.status,
            "provider_response": l.provider_response,
            "created_at": format_ist_datetime(l.created_at)
        })

    session_data = {"user_id": current_user.id, "role": current_user.role, "user_name": current_user.full_name}

    # Render clean notifications log page using admin layout
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>WhatsApp Notifications Log | DirectHarvest AI</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <link rel="stylesheet" href="/static/css/admin.css">
    </head>
    <body>
    <div class="container-fluid p-4">
        <div class="admin-header d-flex justify-content-between align-items-center mb-4">
            <h2>💬 WhatsApp Notification Telemetry Logs</h2>
            <div>
                <a href="/admin/dashboard" class="btn btn-outline-light me-2">Dashboard</a>
                <a href="/logout" class="btn btn-danger">Logout</a>
            </div>
        </div>
        <div class="card p-3 mb-4 shadow-sm border-0">
            <h5>Notification Delivery Mode Status: <span class="badge bg-success">Active & Protected</span></h5>
            <p class="text-muted small mb-0">Records every role-specific notification triggered for Consumers, Farmers, and Delivery Partners. If Meta credentials are not configured, entries are securely recorded in high-fidelity Simulated Mode with full message preview and payload details.</p>
        </div>
        <div class="card shadow-sm border-0">
            <div class="card-body">
                <div class="table-responsive">
                    <table class="table table-hover table-striped">
                        <thead class="table-dark">
                            <tr>
                                <th>Log #</th>
                                <th>Order #</th>
                                <th>Role</th>
                                <th>Phone</th>
                                <th>Notification Type</th>
                                <th>Delivery Mode</th>
                                <th>Status</th>
                                <th>Timestamp (IST)</th>
                                <th>Message Preview</th>
                            </tr>
                        </thead>
                        <tbody>
                            {"".join([f'''<tr>
                                <td>{l["log_id"]}</td>
                                <td>{"#" + str(l["order_id"]) if l["order_id"] else "N/A"}</td>
                                <td><span class="badge bg-secondary">{l["recipient_role"]}</span></td>
                                <td>{l["recipient_phone"]}</td>
                                <td>{l["message_type"]}</td>
                                <td><span class="badge bg-info text-dark">{l["send_mode"]}</span></td>
                                <td><span class="badge bg-{"success" if l["status"] in ("Sent", "Simulated") else "danger"}">{l["status"]}</span></td>
                                <td>{l["created_at"]}</td>
                                <td><button class="btn btn-sm btn-outline-secondary" onclick="alert(`{l['message_body'].replace('`', '')}`)">View Body</button></td>
                            </tr>''' for l in formatted]) if formatted else '<tr><td colspan="9" class="text-center py-4 text-muted">No WhatsApp notifications logged yet. Place an order to generate entries!</td></tr>'}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# ---------------- SETTINGS ----------------
@router.post("/update-commission")
async def update_commission_action(
    commission_rate: float = Form(...),
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    setting = db.query(PlatformSetting).filter(PlatformSetting.key == "commission_rate").first()
    if setting:
        setting.value = str(commission_rate)
    else:
        db.add(PlatformSetting(key="commission_rate", value=str(commission_rate)))
    db.commit()
    from app.services.platform_settings_service import PlatformSettingsService
    PlatformSettingsService.bump_version("commission_rate_updated")
    return RedirectResponse(url="/admin/dashboard", status_code=302)

# ---------------- AI CONTROLS (ADMIN ONLY) ----------------
@router.get("/ai-settings", response_class=HTMLResponse)
async def admin_ai_settings_page(
    request: Request,
    success: Optional[str] = None,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    api_url_setting = db.query(PlatformSetting).filter(PlatformSetting.key == "ai_api_url").first()
    api_key_setting = db.query(PlatformSetting).filter(PlatformSetting.key == "ai_api_key").first()
    model_setting = db.query(PlatformSetting).filter(PlatformSetting.key == "ai_model").first()
    enabled_setting = db.query(PlatformSetting).filter(PlatformSetting.key == "ai_enabled").first()

    base_url = api_url_setting.value if api_url_setting else "https://api.openai.com/v1"
    raw_key = api_key_setting.value if api_key_setting else ""
    masked_key = (raw_key[:4] + "••••••••" + raw_key[-4:]) if len(raw_key) > 8 else ("••••••••" if raw_key else "")

    selected_model = model_setting.value if model_setting else "OpenCV-ComputerVision-Engine"
    is_enabled = (enabled_setting.value.lower() in ["true", "1"]) if enabled_setting else True

    available_models = [
        "OpenCV-ComputerVision-Engine",
        "DirectHarvest-ColorHeuristic-v2",
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-3.5-turbo"
    ]
    if selected_model not in available_models:
        available_models.append(selected_model)

    settings_dict = {
        "base_url": base_url,
        "masked_key": masked_key,
        "model": selected_model,
        "ai_enabled": is_enabled,
        "available_models": available_models,
        "has_real_key": bool(raw_key)
    }
    session_data = {"user_id": current_user.id, "role": current_user.role, "user_name": current_user.full_name}

    return templates.TemplateResponse(
        "admin/ai_settings.html",
        {
            "request": request,
            "settings": settings_dict,
            "success": success,
            "session": session_data,
            "ai_status": "connected" if is_enabled else "disconnected"
        }
    )

@router.post("/ai-settings")
async def admin_save_ai_settings(
    request: Request,
    base_url: str = Form(...),
    api_key: Optional[str] = Form(None),
    model: Optional[str] = Form(None),
    ai_enabled: Optional[str] = Form("true"),
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    normalized_url = AIService.normalize_ai_url(base_url)

    url_setting = db.query(PlatformSetting).filter(PlatformSetting.key == "ai_api_url").first()
    if url_setting:
        url_setting.value = normalized_url
    else:
        db.add(PlatformSetting(key="ai_api_url", value=normalized_url))

    if api_key and not api_key.startswith("•") and "••••" not in api_key:
        key_setting = db.query(PlatformSetting).filter(PlatformSetting.key == "ai_api_key").first()
        if key_setting:
            key_setting.value = api_key.strip()
        else:
            db.add(PlatformSetting(key="ai_api_key", value=api_key.strip()))

    if model:
        model_setting = db.query(PlatformSetting).filter(PlatformSetting.key == "ai_model").first()
        if model_setting:
            model_setting.value = model.strip()
        else:
            db.add(PlatformSetting(key="ai_model", value=model.strip()))

    enabled_val = "True" if str(ai_enabled).lower() in ["true", "1", "on"] else "False"
    enabled_setting = db.query(PlatformSetting).filter(PlatformSetting.key == "ai_enabled").first()
    if enabled_setting:
        enabled_setting.value = enabled_val
    else:
        db.add(PlatformSetting(key="ai_enabled", value=enabled_val))

    db.commit()
    from app.services.platform_settings_service import PlatformSettingsService
    PlatformSettingsService.bump_version("ai_settings_saved")
    return RedirectResponse(url="/admin/ai-settings?success=AI+Engine+Configuration+Saved+Successfully!", status_code=302)

@router.post("/ai-settings/test-connection")
async def admin_test_ai_connection(
    request: Request,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    try:
        body = await request.json()
    except Exception:
        body = {}

    base_url = body.get("base_url") or "https://api.openai.com/v1"
    api_key = body.get("api_key") or ""

    result = await AIService.test_api_connection(base_url=base_url, api_key=api_key, db=db)
    return JSONResponse(content=result)


@router.get("/ai-dashboard", response_class=HTMLResponse)
async def admin_ai_dashboard_page(
    request: Request,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    from app.models.crop import CropAssessment
    total_requests = db.query(CropAssessment).count()
    if total_requests == 0:
        total_requests = db.query(Crop).count()

    avg_conf = db.query(func.avg(Crop.freshness_score)).scalar() or 92.5
    avg_confidence = round(float(avg_conf), 1)

    demanded_crops = db.query(Crop).order_by(desc(Crop.demand_score)).limit(6).all()
    crops_list = db.query(Crop).order_by(desc(Crop.crop_id)).limit(6).all()

    session_data = {"user_id": current_user.id, "role": current_user.role, "user_name": current_user.full_name}

    return templates.TemplateResponse(
        "admin/ai_dashboard.html",
        {
            "request": request,
            "total_requests": max(total_requests, 1),
            "success_rate": 100.0,
            "avg_confidence": avg_confidence,
            "demanded_crops": demanded_crops,
            "crops": crops_list,
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.get("/ai-testing-lab", response_class=HTMLResponse)
async def admin_ai_testing_lab_get(
    request: Request,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    session_data = {"user_id": current_user.id, "role": current_user.role, "user_name": current_user.full_name}
    return templates.TemplateResponse(
        "admin/ai_testing_lab.html",
        {
            "request": request,
            "analysis_result": None,
            "input_data": None,
            "json_payload": None,
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.post("/ai-testing-lab", response_class=HTMLResponse)
async def admin_ai_testing_lab_post(
    request: Request,
    crop_name: str = Form(...),
    category: str = Form("Fruits"),
    quantity: float = Form(100.0),
    farmer_price: float = Form(80.0),
    description: Optional[str] = Form(None),
    crop_image: Optional[UploadFile] = None,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    import json
    import os
    import shutil
    from app.services.ai_service import AIService
    from app.config import settings

    image_path = ""
    if crop_image and crop_image.filename:
        upload_folder = settings.UPLOAD_DIR / "crop_images"
        upload_folder.mkdir(parents=True, exist_ok=True)
        saved_filename = f"lab_{crop_image.filename}"
        full_dest = upload_folder / saved_filename
        with open(full_dest, "wb") as buf:
            shutil.copyfileobj(crop_image.file, buf)
        image_path = str(full_dest)

    analysis = AIService.analyze_crop_image(
        image_path=image_path,
        crop_name=crop_name,
        farmer_price=farmer_price
    )

    input_data = {
        "crop_name": crop_name,
        "category": category,
        "quantity": quantity,
        "farmer_price": farmer_price,
        "description": description or "Test produce"
    }

    session_data = {"user_id": current_user.id, "role": current_user.role, "user_name": current_user.full_name}

    return templates.TemplateResponse(
        "admin/ai_testing_lab.html",
        {
            "request": request,
            "analysis_result": analysis,
            "input_data": input_data,
            "json_payload": json.dumps(analysis, indent=2),
            "session": session_data,
            "ai_status": "connected"
        }
    )


# ---------------- DELIVERY FLEET MANAGEMENT & SPECTATOR COCKPIT ----------------
@router.get("/delivery-tracking", response_class=HTMLResponse)
async def admin_delivery_tracking_page(
    request: Request,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    import os
    from app.services.delivery_tracking_service import DeliveryTrackingService

    # Fetch all active orders that have a delivery partner assigned
    active_orders = db.query(Order).filter(
        Order.delivery_partner_id.isnot(None),
        Order.status.in_([STATUS_ASSIGNED, STATUS_ACCEPTED, STATUS_PICKED_UP, STATUS_IN_TRANSIT, "Out For Delivery"])
    ).order_by(desc(Order.order_id)).all()

    fleet_riders = []
    for o in active_orders:
        telemetry = DeliveryTrackingService.get_live_tracking_data(db, o.order_id)
        fleet_riders.append({
            "order_id": o.order_id,
            "rider_id": o.delivery_partner_id,
            "rider_name": o.delivery_partner.full_name if o.delivery_partner else "Rider",
            "rider_phone": o.delivery_partner.phone if o.delivery_partner else "N/A",
            "vehicle_type": (o.delivery_partner.delivery_profile.vehicle_type if o.delivery_partner and o.delivery_partner.delivery_profile else "Bike") or "Bike",
            "crop_name": o.crop.crop_name if o.crop else "Produce",
            "quantity": o.quantity,
            "unit": o.crop.unit if o.crop else "KG",
            "total_amount": o.total_amount,
            "status": o.status,
            "delivery_step": o.delivery_step or "assigned",
            "step_description": telemetry.get("step_description", o.status),
            "package_photo": o.package_photo,
            "package_photo_at": telemetry.get("package_photo_at"),
            "farmer_name": o.farmer.full_name if o.farmer else "Farmer",
            "farmer_address": o.farmer.address if o.farmer else "Farm Hub",
            "consumer_name": o.consumer.full_name if o.consumer else "Customer",
            "consumer_address": o.delivery_address,
            "distance_km": telemetry.get("distance_km", 0),
            "eta_minutes": telemetry.get("eta_minutes", 0),
            "rider_lat": telemetry.get("rider", {}).get("lat"),
            "rider_lng": telemetry.get("rider", {}).get("lng"),
            "telemetry": telemetry,
        })

    total_riders_count = db.query(User).filter(User.role == "delivery").count()
    completed_today_count = db.query(Order).filter(Order.status == STATUS_DELIVERED).count()

    session_data = {"user_id": current_user.id, "role": current_user.role, "user_name": current_user.full_name}

    return templates.TemplateResponse(
        "admin/delivery_tracking.html",
        {
            "request": request,
            "fleet_riders": fleet_riders,
            "active_deliveries_count": len(fleet_riders),
            "total_riders_count": total_riders_count,
            "completed_today_count": completed_today_count,
            "google_maps_api_key": os.getenv("GOOGLE_MAPS_API_KEY", "").strip(),
            "session": session_data,
            "ai_status": "connected"
        }
    )


@router.get("/api/fleet-status")
async def admin_api_fleet_status(
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    from app.services.delivery_tracking_service import DeliveryTrackingService

    active_orders = db.query(Order).filter(
        Order.delivery_partner_id.isnot(None),
        Order.status.in_([STATUS_ASSIGNED, STATUS_ACCEPTED, STATUS_PICKED_UP, STATUS_IN_TRANSIT, "Out For Delivery"])
    ).order_by(desc(Order.order_id)).all()

    fleet = []
    for o in active_orders:
        telemetry = DeliveryTrackingService.get_live_tracking_data(db, o.order_id)
        fleet.append({
            "order_id": o.order_id,
            "rider_id": o.delivery_partner_id,
            "rider_name": o.delivery_partner.full_name if o.delivery_partner else "Rider",
            "rider_phone": o.delivery_partner.phone if o.delivery_partner else "N/A",
            "crop_name": o.crop.crop_name if o.crop else "Produce",
            "status": o.status,
            "delivery_step": o.delivery_step or "assigned",
            "package_photo": o.package_photo,
            "telemetry": telemetry
        })

    return {"success": True, "fleet": fleet, "count": len(fleet)}

