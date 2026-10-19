import io
import pytest
from app.models.user import User
from app.models.crop import Crop
from app.models.order import Order
from app.services.order_service import OrderService
from app.services.delivery_tracking_service import DeliveryTrackingService
from app.utils.constants import (
    ROLE_DELIVERY,
    STATUS_ASSIGNED,
    STATUS_DELIVERED,
    STEP_ACCEPTED,
    STEP_HEADING_TO_FARMER,
    STEP_PACKING,
    STEP_PACKAGE_PICKED,
    STEP_OUT_FOR_DELIVERY,
    STEP_ABOUT_TO_ARRIVE,
    STEP_DELIVERED,
)


def test_delivery_rider_and_fleet_lifecycle(client, db, admin_headers, delivery_headers, consumer_headers, test_setup):
    farmer_id = test_setup["farmer"]
    consumer_id = test_setup["consumer"]
    delivery_id = test_setup["delivery"]

    # 1. Place an order to test broadcast and acceptance
    crop = db.query(Crop).filter(Crop.farmer_id == farmer_id, Crop.quantity_available >= 5.0).first()
    assert crop is not None

    consumer = db.query(User).filter(User.id == consumer_id).first()
    assert consumer is not None

    OrderService.clear_cart(db, consumer.id)
    OrderService.add_to_cart(db, consumer.id, crop.crop_id, 2.0)
    orders = OrderService.checkout(
        db,
        consumer=consumer,
        delivery_address="Vijay Nagar, Indore, Madhya Pradesh",
        payment_method="Cash on Delivery",
    )
    assert len(orders) >= 1
    order = orders[0]
    assert order is not None
    order_id = order.order_id

    # 2. Check available orders broadcast for delivery riders
    broadcast = DeliveryTrackingService.get_available_orders_for_broadcast(db)
    found_in_broadcast = any(item["order_id"] == order_id for item in broadcast)
    assert found_in_broadcast is True

    # 3. Rider accepts order via API
    r_accept = client.post(f"/delivery/api/accept/{order_id}", headers=delivery_headers)
    assert r_accept.status_code == 200
    res_json = r_accept.json()
    assert res_json["success"] is True

    db.rollback()
    order = db.query(Order).filter(Order.order_id == order_id).first()
    assert order.delivery_partner_id == delivery_id
    assert order.status == STATUS_ASSIGNED
    assert order.delivery_step == STEP_ACCEPTED

    # 4. Advance Step 2: Rider heading to farmer
    success, msg = DeliveryTrackingService.advance_step(db, order_id, delivery_id, STEP_HEADING_TO_FARMER)
    assert success is True
    db.refresh(order)
    assert order.delivery_step == STEP_HEADING_TO_FARMER

    # 5. Advance Step 3: Order packing
    success, msg = DeliveryTrackingService.advance_step(db, order_id, delivery_id, STEP_PACKING)
    assert success is True
    db.refresh(order)
    assert order.delivery_step == STEP_PACKING

    # 6. CRUCIAL TEST: Trying to advance to Step 5 (Out for Delivery) without uploading package photo MUST FAIL!
    success, msg = DeliveryTrackingService.advance_step(db, order_id, delivery_id, STEP_OUT_FOR_DELIVERY)
    assert success is False
    assert "Photo of package has to be sent to the head office" in msg
    db.refresh(order)
    assert order.delivery_step != STEP_OUT_FOR_DELIVERY

    # 7. Upload Package Photo to Head Office (Admin)
    fake_photo_bytes = b"fake-jpg-content-for-package-verification"
    success, photo_msg, photo_url = DeliveryTrackingService.upload_package_photo(
        db=db,
        order_id=order_id,
        rider_id=delivery_id,
        file_content=fake_photo_bytes,
        filename="test_package_dispatch.jpg"
    )
    assert success is True
    assert photo_url is not None
    assert "/uploads/packages/" in photo_url

    db.refresh(order)
    assert order.package_photo == photo_url
    assert order.delivery_step == STEP_PACKAGE_PICKED

    # 8. Now advancing to Step 5 (Out for Delivery) MUST SUCCEED because photo was uploaded!
    success, msg = DeliveryTrackingService.advance_step(db, order_id, delivery_id, STEP_OUT_FOR_DELIVERY)
    assert success is True
    db.refresh(order)
    assert order.delivery_step == STEP_OUT_FOR_DELIVERY

    # 9. Advance Step 6: Rider about to arrive
    success, msg = DeliveryTrackingService.advance_step(db, order_id, delivery_id, STEP_ABOUT_TO_ARRIVE)
    assert success is True
    db.refresh(order)
    assert order.delivery_step == STEP_ABOUT_TO_ARRIVE

    # 10. Advance Step 7: Delivery Complete with OTP verification
    valid_otp = order.delivery_otp
    assert valid_otp is not None

    # Invalid OTP fails
    success, msg = DeliveryTrackingService.advance_step(db, order_id, delivery_id, STEP_DELIVERED, entered_otp="999999")
    assert success is False

    # Valid OTP succeeds
    success, msg = DeliveryTrackingService.advance_step(db, order_id, delivery_id, STEP_DELIVERED, entered_otp=valid_otp)
    assert success is True
    db.refresh(order)
    assert order.delivery_step == STEP_DELIVERED
    assert order.status == STATUS_DELIVERED

    # 11. Test Live Telemetry API Endpoint
    r_telem = client.get(f"/api/delivery/order/{order_id}/live-tracking")
    assert r_telem.status_code == 200
    telem_data = r_telem.json()
    assert telem_data["success"] is True
    assert telem_data["telemetry"]["package_photo"] == photo_url
    assert "rider" in telem_data["telemetry"]
    assert "farmer" in telem_data["telemetry"]
    assert "consumer" in telem_data["telemetry"]

    # 12. Test GPS Location Update API
    r_gps = client.post(
        "/api/delivery/update-location",
        json={"order_id": order_id, "latitude": 22.7196, "longitude": 75.8577},
        headers=delivery_headers
    )
    assert r_gps.status_code == 200
    assert r_gps.json()["success"] is True

    # 13. Test Admin Fleet Monitoring Page & API
    r_admin_fleet_page = client.get("/admin/delivery-tracking", headers=admin_headers)
    assert r_admin_fleet_page.status_code == 200
    assert "Delivery Fleet & Live Spectator Cockpit" in r_admin_fleet_page.text

    r_admin_fleet_api = client.get("/admin/api/fleet-status", headers=admin_headers)
    assert r_admin_fleet_api.status_code == 200
    assert r_admin_fleet_api.json()["success"] is True

    # 14. Test Rider Dashboard Page
    r_rider_dash = client.get("/delivery/dashboard", headers=delivery_headers)
    assert r_rider_dash.status_code == 200
    assert "Rider Partner Dashboard" in r_rider_dash.text or "Active Delivery Cockpit" in r_rider_dash.text
