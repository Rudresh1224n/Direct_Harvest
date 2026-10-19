import pytest
from app.models.crop import Crop
from app.models.user import User
from app.models.order import Order
from app.services.order_service import OrderService
from app.utils.constants import (
    STATUS_PENDING,
    STATUS_ACCEPTED,
    STATUS_ASSIGNED,
    STATUS_DELIVERED,
    STATUS_CANCELLED,
    PAYMENT_PAID,
)


def test_cart_operations(client, db):
    consumer = db.query(User).filter(User.role == "consumer", User.status == "Active").first()
    assert consumer is not None
    consumer_id = consumer.id

    # Ensure a crop is available
    crop = db.query(Crop).filter(Crop.status == "available", Crop.quantity_available > 2.0).first()
    assert crop is not None

    # 1. Clear cart first
    OrderService.clear_cart(db, consumer_id)
    assert len(OrderService.get_cart_items(db, consumer_id)) == 0

    # 2. Add to cart
    item = OrderService.add_to_cart(db, consumer_id, crop.crop_id, 1.0)
    assert item.quantity == 1.0
    assert item.crop_id == crop.crop_id

    # 3. Update cart item
    updated_item = OrderService.update_cart_item(db, item.cart_id, consumer_id, 2.0)
    assert updated_item.quantity == 2.0

    # 4. Attempt to add more than available stock
    with pytest.raises(ValueError):
        OrderService.add_to_cart(db, consumer_id, crop.crop_id, crop.quantity_available + 100.0)

    # 5. Remove cart item
    assert OrderService.remove_cart_item(db, item.cart_id, consumer_id) is True
    assert len(OrderService.get_cart_items(db, consumer_id)) == 0


def test_atomic_checkout_and_delivery_lifecycle(client, db):
    consumer = db.query(User).filter(User.role == "consumer", User.status == "Active").first()
    crop = db.query(Crop).filter(Crop.quantity_available > 5.0).first()
    delivery = db.query(User).filter(User.role == "delivery", User.status == "Active").first()
    assert consumer is not None
    assert crop is not None
    assert delivery is not None

    initial_stock = crop.quantity_available
    purchase_qty = 1.0

    # Add to cart
    OrderService.clear_cart(db, consumer.id)
    OrderService.add_to_cart(db, consumer.id, crop.crop_id, purchase_qty)

    # Checkout
    orders = OrderService.checkout(
        db,
        consumer=consumer,
        delivery_address="42 Harvest St, Pune",
        payment_method="Cash on Delivery",
    )
    assert len(orders) == 1
    order = orders[0]

    # Verify stock deducted
    db.refresh(crop)
    assert crop.quantity_available == initial_stock - purchase_qty

    # Verify order fields
    assert order.status == STATUS_PENDING
    assert order.total_amount == round(order.subtotal + order.delivery_charge - order.discount, 2)

    # Progress through lifecycle: Pending -> Accepted -> Assigned -> Picked Up -> In Transit -> Delivered
    accepted = OrderService.update_order_status(db, order.order_id, STATUS_ACCEPTED)
    assert accepted.status == STATUS_ACCEPTED

    assigned = OrderService.update_order_status(db, order.order_id, STATUS_ASSIGNED, delivery_partner_id=delivery.id)
    assert assigned.status == STATUS_ASSIGNED
    assert assigned.delivery_partner_id == delivery.id

    picked = OrderService.update_order_status(db, order.order_id, "Picked Up")
    assert picked.status == "Picked Up"

    in_transit = OrderService.update_order_status(db, order.order_id, "In Transit")
    assert in_transit.status == "In Transit"

    delivered = OrderService.update_order_status(db, order.order_id, STATUS_DELIVERED)
    assert delivered.status == STATUS_DELIVERED
    assert delivered.payment_status == PAYMENT_PAID

    # Cannot alter delivered order
    with pytest.raises(ValueError):
        OrderService.update_order_status(db, order.order_id, STATUS_CANCELLED)


def test_order_cancellation_restores_stock(client, db):
    consumer = db.query(User).filter(User.role == "consumer", User.status == "Active").first()
    crop = db.query(Crop).filter(Crop.quantity_available > 5.0).first()
    assert consumer is not None
    assert crop is not None
    initial_stock = crop.quantity_available

    # Add to cart and checkout 1 unit
    OrderService.clear_cart(db, consumer.id)
    OrderService.add_to_cart(db, consumer.id, crop.crop_id, 1.0)
    orders = OrderService.checkout(
        db,
        consumer=consumer,
        delivery_address="Test Address, Pune",
    )
    order = orders[0]

    # Stock was decremented
    db.refresh(crop)
    assert crop.quantity_available == initial_stock - 1.0

    # Cancel order
    cancelled = OrderService.update_order_status(db, order.order_id, STATUS_CANCELLED)
    assert cancelled.status == STATUS_CANCELLED

    # Verify stock restored
    db.refresh(crop)
    assert crop.quantity_available == initial_stock


def test_cannot_cancel_after_reaching_godown(client, db):
    from app.utils.constants import STATUS_REACHED_HUB
    consumer = db.query(User).filter(User.role == "consumer", User.status == "Active").first()
    crop = db.query(Crop).filter(Crop.quantity_available > 5.0).first()
    delivery = db.query(User).filter(User.role == "delivery", User.status == "Active").first()
    assert consumer is not None
    assert crop is not None
    assert delivery is not None

    OrderService.clear_cart(db, consumer.id)
    OrderService.add_to_cart(db, consumer.id, crop.crop_id, 1.0)
    orders = OrderService.checkout(db, consumer=consumer, delivery_address="Test St")
    order = orders[0]

    # Delivery agent reaches godown
    OrderService.update_order_status(db, order.order_id, STATUS_REACHED_HUB, delivery_partner_id=delivery.id)

    # Attempting to cancel must fail
    with pytest.raises(ValueError) as excinfo:
        OrderService.update_order_status(db, order.order_id, STATUS_CANCELLED)
    assert "cannot be cancelled" in str(excinfo.value).lower()
