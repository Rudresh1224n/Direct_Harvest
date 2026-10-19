
import json
import logging
from typing import Optional
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.models.logs import WhatsAppLog
from app.utils.ist_time import get_ist_now

logger = logging.getLogger("whatsapp_service")


class WhatsAppService:
    """WhatsApp notifications for DirectHarvest orders and deliveries."""

    @staticmethod
    def clean_phone_number(phone: Optional[str]) -> str:
        """Normalize an Indian phone number for WhatsApp."""
        if not phone:
            return ""

        digits = "".join(ch for ch in str(phone) if ch.isdigit())

        if len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]

        if len(digits) == 10:
            return "91" + digits

        return digits

    @staticmethod
    def _money(value) -> str:
        return f"₹{float(value or 0):,.2f}"

    @staticmethod
    def _value(value, fallback="Not available") -> str:
        return str(value).strip() if value else fallback

    @staticmethod
    def _url(path: str) -> str:
        return f"{settings.BASE_URL.rstrip('/')}{path}"

    @staticmethod
    def generate_consumer_order_message(
        order_id: int,
        consumer_name: str,
        crop_name: str,
        quantity: float,
        unit: str,
        price_per_kg: float,
        subtotal: float,
        delivery_charge: float,
        discount: float,
        total_amount: float,
        payment_method: str,
        payment_status: str,
        farmer_name: str,
        farmer_phone: str,
        delivery_address: str,
        order_date_ist: str,
        delivery_partner_info: str = "Pending assignment",
        expected_delivery: Optional[str] = None,
    ) -> str:
        """Create a detailed order confirmation for the consumer."""
        delivery_estimate = (
            expected_delivery
            if expected_delivery
            else "To be confirmed by the delivery team"
        )

        return (
            "🌾 *DirectHarvest AI — Order Confirmation*\n\n"
            f"Hello {consumer_name}, your order has been recorded successfully!\n\n"
            "📦 *ORDER DETAILS*\n"
            f"Order ID: #{order_id}\n"
            f"Order date and time: {order_date_ist} IST\n"
            "Order status: Placed\n\n"
            "🛒 *ITEM DETAILS*\n"
            f"Product: {crop_name}\n"
            f"Quantity: {quantity} {unit}\n"
            f"Price per {unit}: {WhatsAppService._money(price_per_kg)}\n"
            f"Product subtotal: {WhatsAppService._money(subtotal)}\n"
            f"Delivery charge: {WhatsAppService._money(delivery_charge)}\n"
            f"Discount: {WhatsAppService._money(discount)}\n"
            f"*TOTAL: {WhatsAppService._money(total_amount)}*\n\n"
            "💳 *PAYMENT DETAILS*\n"
            f"Method: {payment_method}\n"
            f"Status: {payment_status}\n\n"
            "👨‍🌾 *FARMER DETAILS*\n"
            f"Name: {farmer_name}\n"
            f"Contact: {WhatsAppService._value(farmer_phone, 'Available through the platform')}\n\n"
            "📍 *DELIVERY DETAILS*\n"
            f"Address: {delivery_address}\n"
            f"Delivery partner: {delivery_partner_info}\n"
            f"Expected delivery: {delivery_estimate}\n\n"
            f"Track your order: {WhatsAppService._url('/consumer/orders')}\n\n"
            "Thank you for supporting local farmers! 🌱"
        )

    @staticmethod
    def generate_farmer_order_message(
        order_id: int,
        farmer_name: str,
        crop_name: str,
        quantity: float,
        unit: str,
        price_per_kg: float,
        subtotal: float,
        consumer_name: str,
        consumer_phone: str,
        delivery_address: str,
        order_date_ist: str,
        delivery_partner_info: str = "Pending assignment",
    ) -> str:
        """Create a new-order alert for the relevant farmer."""
        return (
            "🌾 *DirectHarvest AI — New Order Received*\n\n"
            f"Namaste {farmer_name}, a customer ordered your produce.\n\n"
            "📦 *ORDER DETAILS*\n"
            f"Order ID: #{order_id}\n"
            f"Order date and time: {order_date_ist} IST\n"
            "Order status: Placed\n\n"
            "🛒 *YOUR PRODUCT*\n"
            f"Crop: {crop_name}\n"
            f"Quantity: {quantity} {unit}\n"
            f"Listed price per {unit}: {WhatsAppService._money(price_per_kg)}\n"
            f"Product subtotal: {WhatsAppService._money(subtotal)}\n\n"
            "👤 *CONSUMER DETAILS*\n"
            f"Name: {consumer_name}\n"
            f"Contact: {WhatsAppService._value(consumer_phone)}\n"
            f"Delivery address: {delivery_address}\n\n"
            "🚚 *FULFILMENT*\n"
            f"Delivery partner: {delivery_partner_info}\n"
            "Pickup time: To be confirmed\n\n"
            f"Manage this order: {WhatsAppService._url('/farmer/orders')}\n\n"
            "Please review the order and prepare the produce. 🌱"
        )

    @staticmethod
    def generate_delivery_assignment_message(
        order_id: int,
        delivery_partner_name: str,
        crop_name: str,
        quantity: float,
        unit: str,
        farmer_name: str,
        farmer_phone: str,
        farmer_address: str,
        consumer_name: str,
        consumer_phone: str,
        consumer_address: str,
        payment_method: str,
        total_amount: float,
        assignment_date_ist: str,
    ) -> str:
        """Create a delivery assignment alert."""
        is_cash = "cash" in (payment_method or "").lower()
        cash_note = (
            f"{WhatsAppService._money(total_amount)} — collect only "
            "if the order is confirmed as cash-on-delivery."
            if is_cash
            else "₹0.00 — no cash collection indicated."
        )

        return (
            "🚚 *DirectHarvest AI — Delivery Assigned*\n\n"
            f"Hello {delivery_partner_name}, a delivery has been assigned to you.\n\n"
            "📦 *ORDER DETAILS*\n"
            f"Order ID: #{order_id}\n"
            f"Original order time: See order details in your dashboard\n"
            f"Assignment date and time: {assignment_date_ist} IST\n"
            "Delivery status: Assigned\n\n"
            "🛒 *PACKAGE*\n"
            f"Product: {crop_name}\n"
            f"Quantity: {quantity} {unit}\n\n"
            "🏡 *PICKUP — FARMER*\n"
            f"Name: {farmer_name}\n"
            f"Contact: {WhatsAppService._value(farmer_phone)}\n"
            f"Address: {WhatsAppService._value(farmer_address, 'See order dashboard')}\n\n"
            "📍 *DROP-OFF — CONSUMER*\n"
            f"Name: {consumer_name}\n"
            f"Contact: {WhatsAppService._value(consumer_phone)}\n"
            f"Address: {consumer_address}\n\n"
            "💳 *PAYMENT / COLLECTION*\n"
            f"Payment method: {payment_method}\n"
            f"Cash collection instruction: {cash_note}\n\n"
            f"Manage delivery: {WhatsAppService._url('/delivery/dashboard')}\n\n"
            "Update the delivery status in your dashboard after each step."
        )

    @staticmethod
    def generate_otp_message(otp: str, purpose: str = "Password Reset", recipient_phone: str = "") -> str:
        """Create a secure OTP message."""
        receiver_line = f"Receiver Mobile: {recipient_phone}\n" if recipient_phone else ""
        return (
            "🌾 *DirectHarvest AI — Verification OTP*\n\n"
            f"Sender (Admin/Developer): {settings.ADMIN_PHONE}\n"
            f"{receiver_line}"
            f"Your one-time password (OTP) for *{purpose}* is:\n\n"
            f"🔐 *{otp}*\n\n"
            "This OTP is valid for 5 minutes. Please do not share this code with anyone.\n\n"
            f"Admin Helpline / WhatsApp: {settings.ADMIN_PHONE}\n"
            "Thank you for using DirectHarvest AI! 🌱"
        )

    @classmethod
    def send_otp_notification(
        cls,
        db: Session,
        recipient_phone: str,
        otp: str,
        purpose: str = "Password Reset",
    ) -> dict:
        """Send an OTP notification via WhatsApp."""
        body = cls.generate_otp_message(otp, purpose, recipient_phone)
        return cls.send_notification(
            db=db,
            order_id=None,
            recipient_role="User",
            recipient_phone=recipient_phone,
            message_type="OTP_VERIFICATION",
            message_body=body,
        )

    @classmethod
    def send_admin_alert(
        cls,
        db: Session,
        message_body: str,
    ) -> dict:
        """Send an operational WhatsApp notification to the platform administrator."""
        return cls.send_notification(
            db=db,
            order_id=None,
            recipient_role="Admin",
            recipient_phone=settings.ADMIN_PHONE,
            message_type="ADMIN_ALERT",
            message_body=message_body,
        )

    @classmethod
    def send_notification(
        cls,
        db: Session,
        order_id: Optional[int],
        recipient_role: str,
        recipient_phone: str,
        message_type: str,
        message_body: str,
    ) -> dict:
        """
        Send through Meta Cloud API when configured.
        Otherwise record an explicitly simulated notification.
        """
        phone = cls.clean_phone_number(recipient_phone)
        send_mode = "simulated"
        status = "Simulated"
        provider_response = ""

        if not phone:
            status = "Failed"
            provider_response = "Recipient phone number is missing."

        elif (
            settings.WHATSAPP_ACCESS_TOKEN
            and settings.WHATSAPP_PHONE_NUMBER_ID
        ):
            send_mode = "live_cloud_api"

            # This basic text-message integration may need approved
            # templates for business-initiated conversations.
            url = (
                "https://graph.facebook.com/"
                f"{settings.WHATSAPP_API_VERSION}/"
                f"{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
            )

            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": phone,
                "type": "text",
                "text": {
                    "preview_url": False,
                    "body": message_body,
                },
            }

            try:
                response = httpx.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": (
                            f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"
                        ),
                        "Content-Type": "application/json",
                    },
                    timeout=15.0,
                )

                provider_response = response.text[:4000]

                if response.is_success:
                    status = "Sent"
                else:
                    status = "Failed"
                    logger.warning(
                        "WhatsApp provider returned HTTP %s",
                        response.status_code,
                    )

            except httpx.HTTPError:
                status = "Failed"
                provider_response = "WhatsApp provider request failed."
                logger.exception("WhatsApp request failed.")

        else:
            wa_link = (
                f"https://wa.me/{phone}?text={quote(message_body)}"
            )

            provider_response = json.dumps({
                "mode": "simulation",
                "reason": "WhatsApp credentials are not configured.",
                "wa_click_to_chat_url": wa_link,
                "timestamp_ist": get_ist_now().isoformat(),
            })

        try:
            log = WhatsAppLog(
                order_id=order_id,
                recipient_role=recipient_role,
                recipient_phone=recipient_phone or "N/A",
                message_type=message_type,
                message_body=message_body,
                send_mode=send_mode,
                status=status,
                provider_response=provider_response,
            )

            db.add(log)
            db.commit()

        except Exception:
            db.rollback()
            logger.exception("Could not save WhatsApp notification log.")

        return {
            "status": status,
            "send_mode": send_mode,
            "provider_response": provider_response,
            "wa_link": (
                f"https://wa.me/{phone}?text={quote(message_body)}"
                if phone
                else ""
            ),
        }
