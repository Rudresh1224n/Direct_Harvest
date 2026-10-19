
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies.auth import (
    get_current_user,
    get_current_user_optional,
    require_role,
)
from app.models.user import User
from app.schemas.user import UserRegister
from app.services.auth_service import AuthService
from app.templates_config import templates
from app.utils.constants import (
    ROLE_ADMIN,
    ROLE_CONSUMER,
    ROLE_DELIVERY,
    ROLE_FARMER,
)

router = APIRouter(tags=["Authentication"])


def get_session_data(user: Optional[User] = None) -> dict:
    """Build the user information used by existing templates."""
    return {
        "user_id": user.id if user else None,
        "role": user.role if user else None,
        "user_name": user.full_name if user else None,
    }


def set_auth_cookie(response, token: str) -> None:
    """Set the authentication cookie with environment-appropriate security."""
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.APP_ENV == "production",
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )


def redirect_for_role(role: str) -> str:
    """Return the dashboard appropriate for the user's role."""
    destinations = {
        ROLE_ADMIN: "/admin/dashboard",
        ROLE_FARMER: "/farmer/dashboard",
        ROLE_DELIVERY: "/delivery/dashboard",
        ROLE_CONSUMER: "/marketplace",
    }
    return destinations.get(role, "/")


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    message: Optional[str] = None,
    error: Optional[str] = None,
    alert: Optional[str] = None,
    registered: Optional[str] = None,
    next: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    if current_user:
        return RedirectResponse(
            next or redirect_for_role(current_user.role),
            status_code=303,
        )

    if registered:
        message = "Registration successful! Please log in."

    display_alert = alert or request.query_params.get("alert") or message or error

    return templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "message": message or error,
            "alert": display_alert,
            "next": next or "",
            "session": {},
            "ai_status": "connected",
        },
    )


@router.post("/login")
async def login_action(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        from app.services.excel_credential_service import ExcelCredentialService
        ExcelCredentialService.check_and_sync_if_modified(db)
    except Exception:
        pass

    user = AuthService.authenticate_user(db, email, password)

    if not user:
        return templates.TemplateResponse(
            "auth/login.html",
            {
                "request": request,
                "message": "Invalid email or password.",
                "session": {},
                "ai_status": "connected",
            },
            status_code=401,
        )

    token = AuthService.generate_token_for_user(user)

    response = RedirectResponse(
        redirect_for_role(user.role),
        status_code=303,
    )
    set_auth_cookie(response, token)
    return response


@router.get("/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    error: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    if current_user:
        return RedirectResponse(
            redirect_for_role(current_user.role),
            status_code=303,
        )

    return templates.TemplateResponse(
        "auth/register.html",
        {
            "request": request,
            "message": error,
            "session": {},
            "ai_status": "connected",
        },
    )


import time
import random

OTP_STORE = {}
OTP_EXPIRY_SECONDS = 300
MAX_VERIFY_ATTEMPTS = 5


def _clean_phone_last10(phone: Optional[str]) -> str:
    if not phone:
        return ""
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


@router.post("/register")
async def register_action(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: Optional[str] = Form(None),
    role: str = Form(ROLE_CONSUMER),
    phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    city: Optional[str] = Form(None),
    state: Optional[str] = Form(None),
    pincode: Optional[str] = Form(None),
    vehicle_type: Optional[str] = Form(None),
    license_number: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    try:
        final_address = (address or "").strip()
        extra_parts = [p.strip() for p in [city, state, pincode] if p and p.strip() and p.strip().lower() not in final_address.lower()]
        if extra_parts:
            final_address = f"{final_address}, {', '.join(extra_parts)}" if final_address else ", ".join(extra_parts)

        user_data = UserRegister(
            full_name=full_name,
            email=email,
            password=password,
            confirm_password=confirm_password,
            role=role,
            phone=phone,
            address=final_address or None,
            vehicle_type=vehicle_type,
            license_number=license_number,
        )

        AuthService.register_user(db, user_data)

        return RedirectResponse(
            "/login?registered=1",
            status_code=303,
        )

    except ValueError as exc:
        return templates.TemplateResponse(
            "auth/register.html",
            {
                "request": request,
                "message": str(exc),
                "session": {},
                "ai_status": "connected",
            },
            status_code=400,
        )

    except Exception:
        import logging

        logging.getLogger("directharvest").exception(
            "Registration failed."
        )

        return templates.TemplateResponse(
            "auth/register.html",
            {
                "request": request,
                "message": (
                    "Registration could not be completed. "
                    "Please try again."
                ),
                "session": {},
                "ai_status": "connected",
            },
            status_code=500,
        )


@router.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    if current_user:
        return RedirectResponse(redirect_for_role(current_user.role), status_code=303)

    return templates.TemplateResponse(
        "auth/forgot_password.html",
        {
            "request": request,
            "session": {},
            "ai_status": "connected",
        },
    )


def find_user_by_phone_or_email(db: Session, identifier: str) -> Optional[User]:
    """
    Bulletproof lookup of a user by phone or email.
    Strips formatting, spaces, dashes, +91, country codes, or matches email directly.
    """
    if not identifier:
        return None
    raw = str(identifier).strip()

    # 1. Match by email
    if "@" in raw:
        user = db.query(User).filter(User.email.ilike(raw)).first()
        if user:
            return user

    # 2. Extract digits only
    digits = "".join(ch for ch in raw if ch.isdigit())
    last10 = digits[-10:] if len(digits) >= 10 else digits

    # 3. Direct SQL search on last10 digits (prioritize non-admin accounts so admin password is never accidentally targeted)
    if last10 and len(last10) == 10:
        user = db.query(User).filter(User.phone.like(f"%{last10}"), User.role != "admin").first()
        if user:
            return user
        user = db.query(User).filter(User.phone.like(f"%{last10}%"), User.role != "admin").first()
        if user:
            return user
        user = db.query(User).filter(User.phone.like(f"%{last10}")).first()
        if user:
            return user

    # 4. Check all active users by comparing stripped digits (immune to spaces, dashes, +91)
    if digits:
        all_users = db.query(User).filter(User.phone.isnot(None)).all()
        # Non-admin users first
        sorted_users = sorted(all_users, key=lambda x: (x.role == "admin", x.id))
        for u in sorted_users:
            u_digits = "".join(ch for ch in str(u.phone or "") if ch.isdigit())
            if not u_digits:
                continue
            if last10 and len(last10) == 10 and (u_digits[-10:] == last10):
                return u
            if u_digits == digits:
                return u

    # 5. Direct exact match
    user = db.query(User).filter((User.phone == raw) | (User.email.ilike(raw))).first()
    return user


@router.post("/api/send-otp")
async def send_otp_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        body = await request.json()
    except Exception:
        body = {}

    raw_input = str(body.get("phone", "")).strip()
    if not raw_input:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Please enter your registered mobile number or email."},
        )

    user = find_user_by_phone_or_email(db, raw_input)

    if not user:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "message": "No registered account found with this mobile number. Please check the number or register.",
            },
        )

    # Determine receiver's phone number
    receiver_phone = _clean_phone_last10(user.phone)
    if not receiver_phone or len(receiver_phone) < 10:
        digits_raw = "".join(ch for ch in raw_input if ch.isdigit())
        if len(digits_raw) >= 10:
            receiver_phone = digits_raw[-10:]
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "This registered account has no valid mobile number on file. Please contact administrator.",
                },
            )

    # Generate 6-digit OTP
    otp_code = f"{random.randint(100000, 999999)}"
    entry_payload = {
        "otp": otp_code,
        "expires_at": time.time() + OTP_EXPIRY_SECONDS,
        "attempts": 0,
        "verified": False,
        "user_id": user.id,
        "receiver_phone": receiver_phone,
    }

    # Store under multiple keys for resilient lookup
    OTP_STORE[receiver_phone] = entry_payload
    digits_input = "".join(ch for ch in raw_input if ch.isdigit())
    if digits_input:
        OTP_STORE[digits_input[-10:]] = entry_payload
        OTP_STORE[digits_input] = entry_payload
    if raw_input:
        OTP_STORE[raw_input] = entry_payload
    if user.email:
        OTP_STORE[user.email.lower()] = entry_payload

    # Dispatch via WhatsAppService
    from app.services.whatsapp_service import WhatsAppService
    wa_res = WhatsAppService.send_otp_notification(
        db=db,
        recipient_phone=receiver_phone,
        otp=otp_code,
        purpose="Password Reset",
    )

    # Alert admin via WhatsApp
    WhatsAppService.send_admin_alert(
        db=db,
        message_body=(
            f"🔐 *Admin Security Notice*\n"
            f"Password reset OTP generated for {user.full_name}.\n"
            f"Sender: {settings.ADMIN_PHONE}\n"
            f"Receiver: {receiver_phone}\n"
            f"Dispatched via WhatsApp. Status: OTP Active."
        ),
    )

    return JSONResponse(
        content={
            "success": True,
            "message": f"Verification code dispatched from Admin ({settings.ADMIN_PHONE}) to {receiver_phone} via WhatsApp.",
            "sender_phone": settings.ADMIN_PHONE,
            "receiver_phone": receiver_phone,
            "wa_link": wa_res.get("wa_link", ""),
            "otp_preview": otp_code if (settings.DEBUG or settings.APP_ENV != "production") else None,
        }
    )


@router.post("/api/resend-otp")
async def resend_otp_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        body = await request.json()
    except Exception:
        body = {}

    raw_input = str(body.get("phone", "")).strip()
    user = find_user_by_phone_or_email(db, raw_input)
    if not user:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "No registered account found with this mobile number."},
        )

    receiver_phone = _clean_phone_last10(user.phone) or "".join(ch for ch in raw_input if ch.isdigit())[-10:]

    otp_code = f"{random.randint(100000, 999999)}"
    entry_payload = {
        "otp": otp_code,
        "expires_at": time.time() + OTP_EXPIRY_SECONDS,
        "attempts": 0,
        "verified": False,
        "user_id": user.id,
        "receiver_phone": receiver_phone,
    }

    OTP_STORE[receiver_phone] = entry_payload
    digits_input = "".join(ch for ch in raw_input if ch.isdigit())
    if digits_input:
        OTP_STORE[digits_input[-10:]] = entry_payload
        OTP_STORE[digits_input] = entry_payload
    if raw_input:
        OTP_STORE[raw_input] = entry_payload
    if user.email:
        OTP_STORE[user.email.lower()] = entry_payload

    from app.services.whatsapp_service import WhatsAppService
    wa_res = WhatsAppService.send_otp_notification(
        db=db,
        recipient_phone=receiver_phone,
        otp=otp_code,
        purpose="Password Reset",
    )

    return JSONResponse(
        content={
            "success": True,
            "message": f"A new OTP has been dispatched to {receiver_phone}.",
            "sender_phone": settings.ADMIN_PHONE,
            "receiver_phone": receiver_phone,
            "wa_link": wa_res.get("wa_link", ""),
            "otp_preview": otp_code if (settings.DEBUG or settings.APP_ENV != "production") else None,
        }
    )


@router.post("/api/verify-otp")
async def verify_otp_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        body = await request.json()
    except Exception:
        body = {}

    raw_input = str(body.get("phone", "")).strip()
    otp_input = str(body.get("otp", "")).strip()
    last10 = _clean_phone_last10(raw_input)

    record = OTP_STORE.get(last10) or OTP_STORE.get(raw_input)
    if not record:
        user = find_user_by_phone_or_email(db, raw_input)
        if user:
            r_phone = _clean_phone_last10(user.phone)
            record = OTP_STORE.get(r_phone)

    if not record:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "No active OTP request found. Please request an OTP first."},
        )

    if time.time() > record["expires_at"]:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "OTP has expired. Please request a new OTP."},
        )

    if record["attempts"] >= MAX_VERIFY_ATTEMPTS:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Maximum verification attempts exceeded. Please request a new OTP."},
        )

    if record["otp"] != otp_input:
        record["attempts"] += 1
        rem = MAX_VERIFY_ATTEMPTS - record["attempts"]
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": f"Invalid OTP code. {rem} attempts remaining."},
        )

    record["verified"] = True
    return JSONResponse(
        content={"success": True, "message": "OTP verified successfully. Please enter your new password."}
    )


@router.post("/api/reset-password")
async def reset_password_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        body = await request.json()
    except Exception:
        body = {}

    raw_input = str(body.get("phone", "")).strip()
    password = body.get("password") or body.get("new_password", "")
    confirm_password = body.get("confirm_password") or body.get("confirm", "")
    last10 = _clean_phone_last10(raw_input)

    if not password or len(password) < 6:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Password must be at least 6 characters long."},
        )

    if password != confirm_password:
        return JSONResponse(
            status_code=400,
            content={"success": False, "message": "Passwords do not match."},
        )

    # Find the verified OTP record
    record = OTP_STORE.get(last10) or OTP_STORE.get(raw_input)
    if not record:
        user_check = find_user_by_phone_or_email(db, raw_input)
        if user_check:
            r_phone = _clean_phone_last10(user_check.phone)
            record = OTP_STORE.get(r_phone)

    if not record or not record.get("verified"):
        for k, v in list(OTP_STORE.items()):
            if v.get("verified"):
                record = v
                break

    if not record or not record.get("verified"):
        return JSONResponse(
            status_code=403,
            content={"success": False, "message": "Mobile number is not verified. Please verify with OTP first."},
        )

    user = db.query(User).filter(User.id == record["user_id"]).first()
    if not user:
        return JSONResponse(
            status_code=404,
            content={"success": False, "message": "User account could not be found."},
        )

    from app.utils.security import hash_password
    user.password_hash = hash_password(password)
    db.commit()

    # Clear OTP entries for this user
    for k in list(OTP_STORE.keys()):
        if OTP_STORE[k].get("user_id") == user.id:
            del OTP_STORE[k]

    from app.services.whatsapp_service import WhatsAppService
    WhatsAppService.send_otp_notification(
        db=db,
        recipient_phone=user.phone or raw_input,
        otp="SUCCESS",
        purpose="Password Updated",
    )

    return JSONResponse(
        content={"success": True, "message": "Password has been reset successfully!"}
    )


@router.get("/logout")
async def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(
        "access_token",
        path="/",
        secure=settings.APP_ENV == "production",
        httponly=True,
        samesite="lax",
    )
    return response


# -------------------- Dedicated administrator login --------------------


@router.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(
    request: Request,
    error: Optional[str] = None,
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    if current_user and current_user.role == ROLE_ADMIN:
        return RedirectResponse("/admin/dashboard", status_code=303)

    return templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "message": error or "Administrative Access Only",
            "session": {},
            "ai_status": "connected",
            "is_admin_login": True,
        },
    )


@router.post("/admin/login")
async def admin_login_action(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        from app.services.excel_credential_service import ExcelCredentialService
        ExcelCredentialService.check_and_sync_if_modified(db)
    except Exception:
        pass

    user = AuthService.authenticate_user(db, email, password)

    if not user or user.role != ROLE_ADMIN:
        return templates.TemplateResponse(
            "auth/login.html",
            {
                "request": request,
                "message": "Invalid administrator credentials.",
                "session": {},
                "ai_status": "connected",
                "is_admin_login": True,
            },
            status_code=401,
        )

    response = RedirectResponse(
        "/admin/dashboard",
        status_code=303,
    )
    set_auth_cookie(
        response,
        AuthService.generate_token_for_user(user),
    )
    return response


# -------------------- Profile management --------------------


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    message: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        "auth/profile.html",
        {
            "request": request,
            "user": current_user,
            "session": get_session_data(current_user),
            "message": message,
            "ai_status": "connected",
        },
    )


@router.post("/profile")
async def update_profile(
    request: Request,
    full_name: str = Form(...),
    phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    full_name = full_name.strip()

    if len(full_name) < 2 or len(full_name) > 100:
        return RedirectResponse(
            "/profile?message=Please+enter+a+valid+name",
            status_code=303,
        )

    current_user.full_name = full_name
    current_user.phone = phone.strip() if phone else None
    current_user.address = address.strip() if address else None

    db.commit()

    return RedirectResponse(
        "/profile?message=Profile+updated+successfully",
        status_code=303,
    )


@router.get("/dismiss-banner")
async def dismiss_banner(request: Request):
    # Only redirect to a local path to avoid open-redirect vulnerabilities.
    referer = request.headers.get("referer", "/")
    path = "/"

    if referer:
        from urllib.parse import urlparse

        parsed = urlparse(referer)
        if parsed.netloc == request.url.netloc:
            path = parsed.path or "/"

    response = RedirectResponse(path, status_code=303)
    response.set_cookie(
        key="banner_dismissed",
        value="1",
        max_age=86400,
        httponly=True,
        samesite="lax",
        secure=settings.APP_ENV == "production",
    )
    return response


# -------------------- AI settings: administrator only --------------------


@router.get("/ai-settings")
async def ai_settings_page_redirect():
    return RedirectResponse(url="/admin/ai-settings", status_code=302)


@router.post("/ai-settings/test-connection")
async def ai_settings_test_connection_alias(
    request: Request,
    current_user: User = Depends(require_role([ROLE_ADMIN])),
    db: Session = Depends(get_db)
):
    from app.services.ai_service import AIService
    try:
        body = await request.json()
    except Exception:
        body = {}
    base_url = body.get("base_url") or "https://api.openai.com/v1"
    api_key = body.get("api_key") or ""
    result = await AIService.test_api_connection(base_url=base_url, api_key=api_key, db=db)
    return JSONResponse(content=result)

