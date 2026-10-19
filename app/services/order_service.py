
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.order import Order, CartItem
from app.models.crop import Crop
from app.models.user import User
from app.models.logs import Notification
from app.services.whatsapp_service import WhatsAppService
from app.services.wallet_service import WalletService
from app.utils.ist_time import get_ist_now, format_ist_datetime
from app.utils.constants import (
    STATUS_PENDING,
    STATUS_ACCEPTED,
    STATUS_ASSIGNED,
    STATUS_REACHED_HUB,
    STATUS_PICKED_UP,
    STATUS_IN_TRANSIT,
    STATUS_DELIVERED,
    STATUS_CANCELLED,
    PAYMENT_PENDING,
    PAYMENT_PAID,
)
from app.config import settings


class OrderService:
    # -------------------- CART --------------------

    @staticmethod
    def get_cart_items(db: Session, consumer_id: int) -> List[CartItem]:
        return (
            db.query(CartItem)
            .filter(CartItem.consumer_id == consumer_id)
            .all()
        )

    @staticmethod
    def add_to_cart(
        db: Session, consumer_id: int, crop_id: int, quantity: float
    ) -> CartItem:
        if quantity <= 0:
            raise ValueError("Quantity must be greater than zero.")

        crop = db.query(Crop).filter(Crop.crop_id == crop_id).first()

        if not crop or crop.status != "available":
            raise ValueError("Crop is not available for purchase.")

        existing = (
            db.query(CartItem)
            .filter(
                CartItem.consumer_id == consumer_id,
                CartItem.crop_id == crop_id,
            )
            .first()
        )

        new_quantity = quantity + (existing.quantity if existing else 0)

        if new_quantity > crop.quantity_available:
            raise ValueError(
                f"Insufficient stock. Available: "
                f"{crop.quantity_available} {crop.unit}."
            )

        if existing:
            existing.quantity = new_quantity
            item = existing
        else:
            item = CartItem(
                consumer_id=consumer_id,
                crop_id=crop_id,
                quantity=quantity,
            )
            db.add(item)

        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def update_cart_item(
        db: Session, cart_id: int, consumer_id: int, quantity: float
    ) -> Optional[CartItem]:
        item = (
            db.query(CartItem)
            .filter(
                CartItem.cart_id == cart_id,
                CartItem.consumer_id == consumer_id,
            )
            .first()
        )

        if not item:
            return None

        if quantity <= 0:
            db.delete(item)
            db.commit()
            return None

        crop = db.query(Crop).filter(Crop.crop_id == item.crop_id).first()

        if not crop or crop.status != "available":
            raise ValueError("This crop is no longer available.")

        if quantity > crop.quantity_available:
            raise ValueError(
                f"Insufficient stock. Available: "
                f"{crop.quantity_available} {crop.unit}."
            )

        item.quantity = quantity
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def remove_cart_item(
        db: Session, cart_id: int, consumer_id: int
    ) -> bool:
        item = (
            db.query(CartItem)
            .filter(
                CartItem.cart_id == cart_id,
                CartItem.consumer_id == consumer_id,
            )
            .first()
        )

        if not item:
            return False

        db.delete(item)
        db.commit()
        return True

    @staticmethod
    def clear_cart(db: Session, consumer_id: int) -> None:
        (
            db.query(CartItem)
            .filter(CartItem.consumer_id == consumer_id)
            .delete(synchronize_session=False)
        )
        db.commit()

    # -------------------- CHECKOUT --------------------

    @staticmethod
    def checkout(
        db: Session,
        consumer: User,
        delivery_address: str,
        payment_method: str = "Cash on Delivery",
    ) -> List[Order]:
        if not delivery_address or not delivery_address.strip():
            raise ValueError("Delivery address is required.")

        cart_items = (
            db.query(CartItem)
            .filter(CartItem.consumer_id == consumer.id)
            .all()
        )

        if not cart_items:
            raise ValueError("Your cart is empty.")

        created_orders = []

        try:
            # Validate every item before creating any order.
            for item in cart_items:
                crop = (
                    db.query(Crop)
                    .filter(Crop.crop_id == item.crop_id)
                    .with_for_update()
                    .first()
                )

                if not crop or crop.status != "available":
                    raise ValueError(
                        f"{crop.crop_name if crop else 'A crop'} "
                        "is no longer available."
                    )

                if item.quantity <= 0:
                    raise ValueError("Cart quantity must be greater than zero.")

                if crop.quantity_available < item.quantity:
                    raise ValueError(
                        f"Insufficient stock for {crop.crop_name}. "
                        f"Available: {crop.quantity_available} {crop.unit}."
                    )

            # Create orders and reserve stock.
            for item in cart_items:
                crop = (
                    db.query(Crop)
                    .filter(Crop.crop_id == item.crop_id)
                    .with_for_update()
                    .first()
                )

                crop.quantity_available -= item.quantity

                if crop.quantity_available <= 0:
                    crop.quantity_available = 0
                    crop.status = "out_of_stock"

                subtotal = round(item.quantity * crop.farmer_price, 2)
                delivery_charge = float(settings.DEFAULT_DELIVERY_CHARGE)
                discount = 0.0
                total_amount = round(
                    subtotal + delivery_charge - discount, 2
                )

                order = Order(
                    consumer_id=consumer.id,
                    farmer_id=crop.farmer_id,
                    crop_id=crop.crop_id,
                    quantity=item.quantity,
                    price_per_kg=crop.farmer_price,
                    subtotal=subtotal,
                    delivery_charge=delivery_charge,
                    discount=discount,
                    total_amount=total_amount,
                    delivery_address=delivery_address.strip(),
                    payment_method=payment_method,
                    payment_status=PAYMENT_PENDING,
                    status=STATUS_PENDING,
                )

                db.add(order)
                db.flush()

                # WalletService currently commits internally.
                WalletService.credit_pending(
                    db,
                    crop.farmer_id,
                    order.order_id,
                    subtotal,
                )

                db.add(
                    Notification(
                        user_id=crop.farmer_id,
                        title="New Order Placed!",
                        message=(
                            f"Order #{order.order_id}: {item.quantity} "
                            f"{crop.unit} of {crop.crop_name}."
                        ),
                    )
                )

                created_orders.append(order)

            db.query(CartItem).filter(
                CartItem.consumer_id == consumer.id
            ).delete(synchronize_session=False)

            db.commit()

        except Exception:
            db.rollback()
            raise

        # Send notifications after the order transaction succeeds.
        # Notification failures must not undo a placed order.
        for order in created_orders:
            try:
                db.refresh(order)

                farmer = order.farmer
                crop = order.crop
                order_date = format_ist_datetime(order.order_date)

                consumer_message = (
                    WhatsAppService.generate_consumer_order_message(
                        order_id=order.order_id,
                        consumer_name=consumer.full_name,
                        crop_name=crop.crop_name,
                        quantity=order.quantity,
                        unit=crop.unit,
                        price_per_kg=order.price_per_kg,
                        subtotal=order.subtotal,
                        delivery_charge=order.delivery_charge,
                        discount=order.discount,
                        total_amount=order.total_amount,
                        payment_method=order.payment_method,
                        payment_status=order.payment_status,
                        farmer_name=farmer.full_name if farmer else "Farmer",
                        farmer_phone=farmer.phone if farmer else "",
                        delivery_address=order.delivery_address,
                        order_date_ist=order_date,
                    )
                )

                WhatsAppService.send_notification(
                    db=db,
                    order_id=order.order_id,
                    recipient_role="consumer",
                    recipient_phone=consumer.phone or "",
                    message_type="order_confirmation",
                    message_body=consumer_message,
                )

                if farmer:
                    farmer_message = (
                        WhatsAppService.generate_farmer_order_message(
                            order_id=order.order_id,
                            farmer_name=farmer.full_name,
                            crop_name=crop.crop_name,
                            quantity=order.quantity,
                            unit=crop.unit,
                            price_per_kg=order.price_per_kg,
                            subtotal=order.subtotal,
                            consumer_name=consumer.full_name,
                            consumer_phone=consumer.phone or "",
                            delivery_address=order.delivery_address,
                            order_date_ist=order_date,
                        )
                    )

                    WhatsAppService.send_notification(
                        db=db,
                        order_id=order.order_id,
                        recipient_role="farmer",
                        recipient_phone=farmer.phone or "",
                        message_type="new_order_alert",
                        message_body=farmer_message,
                    )

            except Exception:
                # Preserve the successfully created order if messaging fails.
                continue

        return created_orders

    # -------------------- ORDER STATUS --------------------

    @staticmethod
    def update_order_status(
        db: Session,
        order_id: int,
        new_status: str,
        delivery_partner_id: Optional[int] = None,
        updated_by_user: Optional[User] = None,
    ) -> Order:
        allowed_statuses = {
            STATUS_PENDING,
            STATUS_ACCEPTED,
            STATUS_ASSIGNED,
            STATUS_REACHED_HUB,
            "Reached Godown",
            "Reached Farmer Hub",
            STATUS_PICKED_UP,
            "Picked Up",
            STATUS_IN_TRANSIT,
            "In Transit",
            "Out For Delivery",
            STATUS_DELIVERED,
            STATUS_CANCELLED,
        }

        if new_status not in allowed_statuses:
            raise ValueError(f"Invalid order status: {new_status}")

        order = (
            db.query(Order)
            .filter(Order.order_id == order_id)
            .with_for_update()
            .first()
        )

        if not order:
            raise ValueError("Order not found.")

        old_status = order.status

        if old_status == STATUS_DELIVERED:
            raise ValueError("A delivered order cannot be changed.")

        if old_status == STATUS_CANCELLED:
            raise ValueError("A cancelled order cannot be changed.")

        if new_status == STATUS_CANCELLED:
            # Cancellation allowed ONLY before delivery partner reaches farmer's godown
            disallowed_for_cancel = {
                STATUS_REACHED_HUB,
                "Reached Godown",
                "Reached Farmer Hub",
                "Picked Up",
                STATUS_PICKED_UP,
                "In Transit",
                STATUS_IN_TRANSIT,
                "Out For Delivery",
                STATUS_DELIVERED,
            }
            if old_status in disallowed_for_cancel:
                raise ValueError(
                    "Order cannot be cancelled because the delivery partner has already reached the farmer's godown or the order is in transit."
                )

        if delivery_partner_id is not None:
            partner = (
                db.query(User)
                .filter(User.id == delivery_partner_id)
                .first()
            )

            if not partner or partner.role != "delivery":
                raise ValueError("Invalid delivery partner.")

            order.delivery_partner_id = delivery_partner_id

            if new_status in {STATUS_PENDING, STATUS_ACCEPTED}:
                new_status = STATUS_ASSIGNED

        order.status = new_status
        order.updated_at = get_ist_now()

        if new_status in {STATUS_REACHED_HUB, "Reached Godown", "Reached Farmer Hub"}:
            db.add(
                Notification(
                    user_id=order.consumer_id,
                    title="Delivery Partner Reached Farmer Godown",
                    message=(
                        f"Delivery partner has reached the farmer's godown to collect your order #{order.order_id} ({order.quantity} {order.crop.unit if order.crop else 'KG'} of {order.crop.crop_name if order.crop else 'Crop'})."
                    ),
                )
            )
            # Also notify admin (user_id=1)
            db.add(
                Notification(
                    user_id=1,
                    title="Driver Reached Farmer Godown",
                    message=f"Order #{order.order_id}: Delivery partner reached farmer godown.",
                )
            )

        elif new_status in {STATUS_PICKED_UP, "Picked Up"}:
            db.add(
                Notification(
                    user_id=order.consumer_id,
                    title="Order Collected from Farmer",
                    message=(
                        f"Your order #{order.order_id} has been picked up from the farm and is prepared for delivery."
                    ),
                )
            )
            db.add(
                Notification(
                    user_id=1,
                    title="Order Picked Up",
                    message=f"Order #{order.order_id} picked up by delivery partner.",
                )
            )

        elif new_status in {STATUS_IN_TRANSIT, "In Transit", "Out For Delivery"}:
            db.add(
                Notification(
                    user_id=order.consumer_id,
                    title="Order Out for Delivery",
                    message=(
                        f"Your order #{order.order_id} is on its way to your delivery address."
                    ),
                )
            )
            db.add(
                Notification(
                    user_id=1,
                    title="Order In Transit",
                    message=f"Order #{order.order_id} is on the way to the customer.",
                )
            )

        elif new_status == STATUS_DELIVERED:
            order.payment_status = PAYMENT_PAID

            WalletService.settle_delivered_order(
                db,
                order.farmer_id,
                order.order_id,
                order.subtotal,
            )

            db.add(
                Notification(
                    user_id=order.consumer_id,
                    title="Order Delivered & Payment Received!",
                    message=(
                        f"Order #{order.order_id} has been delivered and payment of ₹{order.total_amount} received. "
                        "Please share your rating and review."
                    ),
                )
            )
            db.add(
                Notification(
                    user_id=1,
                    title="Order Successfully Delivered",
                    message=f"Order #{order.order_id} delivered. Payment of ₹{order.total_amount} marked Paid.",
                )
            )

        elif new_status == STATUS_CANCELLED:
            crop = order.crop

            if crop:
                crop.quantity_available += order.quantity
                if crop.status == "out_of_stock":
                    crop.status = "available"

            WalletService.cancel_order_pending(
                db,
                order.farmer_id,
                order.order_id,
                order.subtotal,
            )

            db.add(
                Notification(
                    user_id=order.consumer_id,
                    title="Order Cancelled",
                    message=f"Order #{order.order_id} was cancelled. Stock has been returned to the farmer.",
                )
            )
            db.add(
                Notification(
                    user_id=order.farmer_id,
                    title="Order Cancelled",
                    message=f"Order #{order.order_id} was cancelled. {order.quantity} {crop.unit if crop else 'KG'} returned to your available stock.",
                )
            )

        db.commit()
        db.refresh(order)

        # Notify the assigned delivery partner after saving the order.
        if delivery_partner_id is not None:
            try:
                partner = order.delivery_partner

                if partner:
                    message = (
                        WhatsAppService.generate_delivery_assignment_message(
                            order_id=order.order_id,
                            delivery_partner_name=partner.full_name,
                            crop_name=order.crop.crop_name if order.crop else "Produce",
                            quantity=order.quantity,
                            unit=order.crop.unit if order.crop else "KG",
                            farmer_name=order.farmer.full_name if order.farmer else "Farmer",
                            farmer_phone=order.farmer.phone if order.farmer else "",
                            farmer_address=order.farmer.address if order.farmer else "",
                            consumer_name=order.consumer.full_name if order.consumer else "Customer",
                            consumer_phone=order.consumer.phone if order.consumer else "",
                            consumer_address=order.delivery_address,
                            payment_method=order.payment_method,
                            total_amount=order.total_amount,
                            assignment_date_ist=format_ist_datetime(
                                get_ist_now()
                            ),
                        )
                    )

                    WhatsAppService.send_notification(
                        db=db,
                        order_id=order.order_id,
                        recipient_role="delivery",
                        recipient_phone=partner.phone or "",
                        message_type="delivery_assignment",
                        message_body=message,
                    )
            except Exception:
                pass

        return order

