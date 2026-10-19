from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.templates_config import templates
from app.models.user import User
from app.models.crop import Crop
from app.models.order import Order, CartItem
from app.models.review import Review
from app.services.order_service import OrderService
from app.services.crop_service import CropService
from app.services.review_service import ReviewService
from app.services.insights_service import InsightsService
from app.services.wallet_service import WalletService
from app.dependencies.auth import get_current_user
from app.utils.ist_time import format_ist_datetime
from app.config import settings

router = APIRouter(tags=["Consumer"])

from typing import Optional, List, Dict, Any, Tuple

def format_cart_items(items: List[CartItem]) -> Tuple[List[Dict[str, Any]], float, float, float]:
    formatted = []
    subtotal = 0.0
    for it in items:
        crop = it.crop
        if not crop:
            continue
        line_total = round(it.quantity * crop.farmer_price, 2)
        subtotal += line_total
        img = crop.crop_image or ""
        if img and not img.startswith("http"):
            img = f"/static/uploads/crop_images/{img}"
        elif not img:
            img = "https://images.unsplash.com/photo-1546470427-e5ac89cd0b3b"

        formatted.append({
            "cart_id": it.cart_id,
            "crop_id": crop.crop_id,
            "crop_name": crop.crop_name,
            "crop_image": img,
            "farmer_name": crop.farmer.full_name if crop.farmer else "Farmer",
            "price_per_kg": crop.farmer_price,
            "quantity": it.quantity,
            "unit": crop.unit or "KG",
            "total_price": line_total
        })

    subtotal = round(subtotal, 2)
    delivery_charge = settings.DEFAULT_DELIVERY_CHARGE if subtotal > 0 else 0.0
    grand_total = round(subtotal + delivery_charge, 2)
    return formatted, subtotal, delivery_charge, grand_total

# ---------------- CART ROUTES ----------------
@router.get("/cart", response_class=HTMLResponse)
@router.get("/consumer/cart", response_class=HTMLResponse)
async def view_cart(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    items = OrderService.get_cart_items(db, current_user.id)
    cart_items, subtotal, delivery_charge, grand_total = format_cart_items(items)

    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name,
        "cart": cart_items
    }

    return templates.TemplateResponse(
        "consumer/cart.html",
        {
            "request": request,
            "cart_items": cart_items,
            "subtotal": subtotal,
            "delivery_charge": delivery_charge,
            "grand_total": grand_total,
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.post("/add-to-cart")
@router.post("/consumer/cart/add")
async def add_to_cart_action(
    request: Request,
    crop_id: int = Form(...),
    quantity: float = Form(1.0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        OrderService.add_to_cart(db, current_user.id, crop_id, quantity)
        return RedirectResponse(url="/cart", status_code=302)
    except Exception as e:
        referer = request.headers.get("referer", "/marketplace")
        sep = "&" if "?" in referer else "?"
        return RedirectResponse(url=f"{referer}{sep}error={str(e)}", status_code=302)

@router.get("/update-cart/{crop_id}/{action}")
async def update_cart_quantity(
    crop_id: int,
    action: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    item = db.query(CartItem).filter(CartItem.consumer_id == current_user.id, CartItem.crop_id == crop_id).first()
    if item:
        if action == "increase":
            new_qty = item.quantity + 1.0
            OrderService.update_cart_item(db, item.cart_id, current_user.id, new_qty)
        elif action == "decrease":
            new_qty = item.quantity - 1.0
            OrderService.update_cart_item(db, item.cart_id, current_user.id, new_qty)
    return RedirectResponse(url="/cart", status_code=302)

@router.get("/remove-cart/{crop_id}")
async def remove_cart_action(
    crop_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    item = db.query(CartItem).filter(CartItem.consumer_id == current_user.id, CartItem.crop_id == crop_id).first()
    if item:
        OrderService.remove_cart_item(db, item.cart_id, current_user.id)
    return RedirectResponse(url="/cart", status_code=302)

# ---------------- CHECKOUT & ORDERS ----------------
@router.get("/checkout", response_class=HTMLResponse)
@router.get("/consumer/checkout", response_class=HTMLResponse)
async def checkout_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    items = OrderService.get_cart_items(db, current_user.id)
    if not items:
        return RedirectResponse("/cart", status_code=302)

    cart_items, subtotal, delivery_charge, grand_total = format_cart_items(items)

    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name,
        "cart": cart_items
    }

    return templates.TemplateResponse(
        "consumer/checkout.html",
        {
            "request": request,
            "cart_items": cart_items,
            "subtotal": subtotal,
            "delivery_charge": delivery_charge,
            "grand_total": grand_total,
            "user": current_user,
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.post("/place-order")
@router.post("/consumer/place-order")
async def place_order_action(
    request: Request,
    name: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    address: str = Form(...),
    city: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
    pincode: Optional[str] = Form(None),
    payment_method: str = Form("Cash on Delivery"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    full_address = address.strip()
    extra_parts = [p.strip() for p in [city, state, pincode] if p and p.strip() and p.strip().lower() not in full_address.lower()]
    if extra_parts:
        full_address = f"{full_address}, {', '.join(extra_parts)}"

    # Save/update customer phone entered at the time of placing order
    checkout_phone = (phone or "").strip()
    if checkout_phone:
        digits = "".join(c for c in checkout_phone if c.isdigit())
        clean_10 = digits[-10:] if len(digits) >= 10 else checkout_phone
        if current_user.phone != clean_10:
            current_user.phone = clean_10
            db.commit()

    if name and name.strip() and (not current_user.full_name or current_user.full_name == "Registered User"):
        current_user.full_name = name.strip()
        db.commit()

    if not current_user.address:
        current_user.address = full_address
        db.commit()

    created_orders = OrderService.checkout(
        db=db,
        consumer=current_user,
        delivery_address=full_address,
        payment_method=payment_method
    )

    first_order_id = created_orders[0].order_id if created_orders else 1
    import urllib.parse
    phone_param = urllib.parse.quote_plus(checkout_phone or current_user.phone or "")
    return RedirectResponse(url=f"/order-success/{first_order_id}?phone={phone_param}", status_code=302)

@router.get("/order-success/{order_id}", response_class=HTMLResponse)
async def order_success_page(
    order_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order or order.consumer_id != current_user.id:
        return RedirectResponse("/order-history", status_code=302)

    crop = order.crop
    crop_name = crop.crop_name if crop else "Farm Produce"
    farmer = order.farmer
    farmer_name = farmer.full_name if farmer else "Farmer"
    farmer_phone = farmer.phone if farmer else ""
    total_amount = float(order.total_amount or 0.0)
    quantity = float(order.quantity or 0.0)
    order_date_str = format_ist_datetime(order.order_date)

    from urllib.parse import quote
    from app.services.whatsapp_service import WhatsAppService

    # 1. Customer phone (entered during checkout or profile phone)
    raw_customer_phone = request.query_params.get("phone") or current_user.phone or ""
    clean_customer_phone = WhatsAppService.clean_phone_number(raw_customer_phone)

    # Generate customer order confirmation receipt message
    customer_message = (
        f"🌾 *DirectHarvest AI — Order Confirmation*\n\n"
        f"Hello {current_user.full_name}, your order has been placed successfully!\n\n"
        f"📦 *ORDER DETAILS*\n"
        f"Order ID: #{order.order_id}\n"
        f"Date: {order_date_str} IST\n"
        f"Product: {crop_name}\n"
        f"Quantity: {quantity} KG\n"
        f"Total Amount: ₹{total_amount:,.2f}\n"
        f"Payment Method: {order.payment_method}\n"
        f"Delivery Address: {order.delivery_address}\n\n"
        f"👨‍🌾 *FARMER DETAILS*\n"
        f"Farmer Name: {farmer_name}\n"
        f"Farmer Contact: {farmer_phone or 'Available on platform'}\n\n"
        f"Your fresh harvest is being prepared by the farmer. Thank you for choosing DirectHarvest AI! 🌱"
    )

    # Customer WhatsApp link (sent to the customer who ordered)
    if clean_customer_phone:
        customer_wa_url = f"https://api.whatsapp.com/send?phone={clean_customer_phone}&text={quote(customer_message)}"
    else:
        customer_wa_url = f"https://api.whatsapp.com/send?text={quote(customer_message)}"

    # 2. Farmer WhatsApp link (sent directly to the engaged farmer)
    clean_farmer_phone = WhatsAppService.clean_phone_number(farmer_phone) if farmer_phone else ""
    farmer_message = (
        f"🌾 *DirectHarvest AI — New Order Received*\n\n"
        f"Namaste {farmer_name}, you have a new customer order!\n\n"
        f"📦 *ORDER DETAILS*\n"
        f"Order ID: #{order.order_id}\n"
        f"Date: {order_date_str} IST\n"
        f"Crop: {crop_name}\n"
        f"Quantity: {quantity} KG\n"
        f"Total Amount: ₹{total_amount:,.2f}\n\n"
        f"👤 *CUSTOMER DETAILS*\n"
        f"Customer Name: {current_user.full_name}\n"
        f"Customer Phone: {raw_customer_phone or 'N/A'}\n"
        f"Delivery Address: {order.delivery_address}\n\n"
        f"Please prepare the produce for pickup. Thank you! 🌱"
    )

    if clean_farmer_phone:
        farmer_wa_url = f"https://api.whatsapp.com/send?phone={clean_farmer_phone}&text={quote(farmer_message)}"
    else:
        farmer_wa_url = None

    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name
    }

    return templates.TemplateResponse(
        "consumer/order_success.html",
        {
            "request": request,
            "order_id": order.order_id,
            "crop_name": crop_name,
            "quantity": quantity,
            "total_amount": total_amount,
            "order": order,
            "farmer_name": farmer_name,
            "farmer_phone": farmer_phone,
            "customer_phone": raw_customer_phone or current_user.phone or "",
            "order_date_str": order_date_str,
            "whatsapp_url": customer_wa_url,
            "customer_wa_url": customer_wa_url,
            "farmer_wa_url": farmer_wa_url,
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.get("/order-history", response_class=HTMLResponse)
@router.get("/consumer/orders", response_class=HTMLResponse)
@router.get("/consumer/dashboard", response_class=HTMLResponse)
async def order_history_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    raw_orders = db.query(Order).filter(Order.consumer_id == current_user.id).order_by(desc(Order.order_id)).all()
    orders_list = []
    for o in raw_orders:
        orders_list.append({
            "order_id": o.order_id,
            "crop_name": o.crop.crop_name if o.crop else f"Crop #{o.crop_id}",
            "quantity": o.quantity,
            "price_per_kg": o.price_per_kg,
            "total_amount": o.total_amount,
            "status": o.status,
            "payment_method": o.payment_method,
            "payment_status": o.payment_status,
            "order_date": format_ist_datetime(o.order_date),
            "farmer_name": o.farmer.full_name if o.farmer else "Farmer",
            "delivery_partner": o.delivery_partner.full_name if o.delivery_partner else "Pending Assignment",
            "delivery_address": o.delivery_address
        })

    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name
    }

    return templates.TemplateResponse(
        "consumer/order_history.html",
        {
            "request": request,
            "orders": orders_list,
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.get("/track-order/{order_id}", response_class=HTMLResponse)
@router.get("/consumer/orders/{order_id}/tracking", response_class=HTMLResponse)
async def track_order_page(
    order_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name
    }

    return templates.TemplateResponse(
        "consumer/tracking.html",
        {
            "request": request,
            "order": order,
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.post("/review")
@router.post("/consumer/reviews/add")
async def add_review_action(
    request: Request,
    order_id: int = Form(...),
    rating: int = Form(5),
    review: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        ReviewService.add_review(
            db=db,
            consumer_id=current_user.id,
            order_id=order_id,
            rating=rating,
            review_text=review
        )
        return RedirectResponse(url="/order-history?message=Review+submitted+successfully!", status_code=302)
    except Exception as e:
        return RedirectResponse(url=f"/order-history?error={str(e)}", status_code=302)

@router.get("/cancel-order/{order_id}")
async def cancel_order_action(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        return RedirectResponse(url="/order-history?error=Order+not+found", status_code=302)
    if order.consumer_id != current_user.id and current_user.role not in ("admin", "farmer"):
        return RedirectResponse(url="/order-history?error=Unauthorized+action", status_code=302)

    from app.utils.constants import STATUS_CANCELLED
    try:
        OrderService.update_order_status(db, order_id, STATUS_CANCELLED)
        return RedirectResponse(url="/order-history?message=Order+cancelled+successfully.+Stock+has+been+restored.", status_code=302)
    except Exception as e:
        return RedirectResponse(url=f"/order-history?error={str(e)}", status_code=302)

@router.get("/reorder/{order_id}")
async def reorder_action(
    order_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if order and order.crop:
        try:
            OrderService.add_to_cart(db, current_user.id, order.crop_id, order.quantity)
        except Exception:
            pass
    return RedirectResponse(url="/cart", status_code=302)

@router.get("/consumer/recommendations", response_class=HTMLResponse)
async def recommendations_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    recommendations = InsightsService.get_recommendations_for_consumer(db, current_user.id, limit=6)
    from app.routes.public_routes import format_crop_for_template
    formatted = [format_crop_for_template(c) for c in recommendations]

    session_data = {
        "user_id": current_user.id,
        "role": current_user.role,
        "user_name": current_user.full_name
    }

    return templates.TemplateResponse(
        "consumer/marketplace.html",
        {
            "request": request,
            "crops": formatted,
            "categories": [],
            "grades": [],
            "selected_category": "all",
            "selected_grade": "all",
            "selected_trust": "all",
            "search_query": "Recommended for You",
            "session": session_data,
            "ai_status": "connected"
        }
    )
