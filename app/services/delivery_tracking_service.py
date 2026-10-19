import os
import time
import logging
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.config import settings
from app.models.user import User, DeliveryPartnerProfile
from app.models.order import Order
from app.models.logs import Notification
from app.services.geocoding_service import GeocodingService
from app.utils.constants import (
    ROLE_DELIVERY,
    STATUS_PENDING,
    STATUS_ACCEPTED,
    STATUS_ASSIGNED,
    STATUS_PICKED_UP,
    STATUS_IN_TRANSIT,
    STATUS_DELIVERED,
    PAYMENT_PAID,
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
from app.utils.ist_time import get_ist_now, format_ist_datetime

logger = logging.getLogger("delivery_tracking_service")


class DeliveryTrackingService:
    @staticmethod
    def get_available_orders_for_broadcast(db: Session, rider_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Fetches orders that are waiting for a delivery rider to accept.
        Returns full address, payment, customer, and farmer details for the incoming alert pop-up.
        """
        unassigned = db.query(Order).filter(
            Order.delivery_partner_id.is_(None),
            Order.status.in_([STATUS_ACCEPTED, STATUS_PENDING, "Placed"])
        ).order_by(desc(Order.order_id)).limit(10).all()

        results = []
        for o in unassigned:
            farmer_addr = o.farmer.address if o.farmer and o.farmer.address else (o.crop.location if o.crop else "Farm Hub, MP")
            consumer_addr = o.delivery_address or "Customer Address, MP"
            farmer_coords = GeocodingService.get_coordinates_for_address(farmer_addr)
            consumer_coords = GeocodingService.get_coordinates_for_address(consumer_addr, fallback_offset=1.5)
            trip_km = GeocodingService.calculate_haversine_distance_km(farmer_coords, consumer_coords)

            results.append({
                "order_id": o.order_id,
                "crop_name": o.crop.crop_name if o.crop else f"Crop #{o.crop_id}",
                "quantity": o.quantity,
                "unit": o.crop.unit if o.crop else "KG",
                "subtotal": o.subtotal,
                "delivery_charge": o.delivery_charge or 30.0,
                "total_amount": o.total_amount,
                "payment_method": o.payment_method or "Cash on Delivery",
                "payment_status": o.payment_status or "Pending",
                "farmer_name": o.farmer.full_name if o.farmer else "Local Farmer",
                "farmer_phone": o.farmer.phone if o.farmer else "N/A",
                "farmer_address": farmer_addr,
                "consumer_name": o.consumer.full_name if o.consumer else "Customer",
                "consumer_phone": o.consumer.phone if o.consumer else "N/A",
                "consumer_address": consumer_addr,
                "estimated_distance_km": trip_km,
                "estimated_minutes": GeocodingService.estimate_eta_minutes(trip_km),
                "created_at": format_ist_datetime(o.order_date),
            })
        return results

    @staticmethod
    def accept_order(db: Session, order_id: int, rider_id: int) -> Tuple[bool, str, Optional[Order]]:
        """
        Delivery rider accepts an incoming broadcast order.
        Assigns the rider, initializes progression to 'rider_accepted', and sends notifications.
        """
        order = db.query(Order).filter(Order.order_id == order_id).first()
        if not order:
            return False, "Order not found.", None

        if order.delivery_partner_id is not None and order.delivery_partner_id != rider_id:
            return False, "This order has already been accepted by another delivery partner.", None

        rider = db.query(User).filter(User.id == rider_id).first()
        if not rider:
            return False, "Delivery rider not found.", None

        # Assign rider
        order.delivery_partner_id = rider_id
        order.status = STATUS_ASSIGNED
        order.delivery_step = STEP_ACCEPTED
        order.updated_at = get_ist_now()

        # Seed initial rider coordinates
        prof = rider.delivery_profile
        if prof and prof.current_latitude and prof.current_longitude:
            order.rider_latitude = prof.current_latitude
            order.rider_longitude = prof.current_longitude
        else:
            # Place rider nearby farmer
            farmer_addr = order.farmer.address if order.farmer and order.farmer.address else "Indore"
            f_lat, f_lng = GeocodingService.get_coordinates_for_address(farmer_addr)
            order.rider_latitude = round(f_lat - 0.015, 5)
            order.rider_longitude = round(f_lng - 0.015, 5)
        order.rider_last_loc_update = get_ist_now()

        # Generate 4-digit delivery completion OTP if empty
        if not order.delivery_otp:
            import random
            order.delivery_otp = str(random.randint(1000, 9999))

        # In-app notification to consumer
        db.add(Notification(
            user_id=order.consumer_id,
            title="Rider Assigned to Your Order",
            message=f"Rider {rider.full_name} has accepted your order #{order.order_id} ({order.crop.crop_name if order.crop else 'Harvest'}) and is assigned!"
        ))

        # In-app notification to Head Office (Admin ID 1)
        db.add(Notification(
            user_id=1,
            title="Order Accepted by Delivery Partner",
            message=f"Order #{order.order_id} accepted by {rider.full_name} ({rider.phone or 'N/A'})."
        ))

        db.commit()
        db.refresh(order)
        logger.info("Order %d accepted by rider %s (ID %d).", order_id, rider.full_name, rider_id)
        return True, f"Order #{order_id} accepted successfully!", order

    @staticmethod
    def advance_step(db: Session, order_id: int, rider_id: int, next_step: str, entered_otp: Optional[str] = None) -> Tuple[bool, str]:
        """
        Advances the order to the next sequential milestone.
        Enforces that 'out_for_delivery' requires a verified package photo.
        Optionally verifies consumer delivery OTP for final delivery handover.
        """
        order = db.query(Order).filter(Order.order_id == order_id).first()
        if not order:
            return False, "Order not found."

        if order.delivery_partner_id != rider_id:
            return False, "You are not the assigned delivery partner for this order."

        rider = db.query(User).filter(User.id == rider_id).first()
        rider_name = rider.full_name if rider else "Delivery Partner"

        # Check required photo verification before delivering
        if next_step in (STEP_OUT_FOR_DELIVERY, "out_for_delivery"):
            if not order.package_photo:
                return False, "Photo of package has to be sent to the head office before delivering the order to the customer address!"

        # Check optional OTP verification for delivered step
        if next_step in (STEP_DELIVERED, "delivered") and entered_otp:
            if order.delivery_otp and entered_otp.strip() != order.delivery_otp.strip():
                return False, "Invalid Consumer Delivery OTP. Please verify with customer."

        # Validate valid transition
        order.delivery_step = next_step
        order.updated_at = get_ist_now()

        # Synchronize order.status with delivery_step
        if next_step in (STEP_ACCEPTED, STEP_HEADING_TO_FARMER, STEP_PACKING):
            order.status = STATUS_ASSIGNED
        elif next_step == STEP_PACKAGE_PICKED:
            order.status = STATUS_PICKED_UP
        elif next_step in (STEP_OUT_FOR_DELIVERY, STEP_ABOUT_TO_ARRIVE, STEP_ARRIVED):
            order.status = STATUS_IN_TRANSIT
        elif next_step == STEP_DELIVERED:
            order.status = STATUS_DELIVERED
            order.payment_status = PAYMENT_PAID
            # Increment completed deliveries count
            if rider and rider.delivery_profile:
                rider.delivery_profile.completed_deliveries = (rider.delivery_profile.completed_deliveries or 0) + 1

        # Deliver in-app notification to consumer matching exact user requested labels
        step_desc = DELIVERY_STEP_DESCRIPTIONS.get(next_step, next_step)
        consumer_msg_map = {
            STEP_ACCEPTED: f"Rider {rider_name} accepted your order.",
            STEP_HEADING_TO_FARMER: "Rider is on the way to reach the farmer.",
            STEP_PACKING: "Your order is getting packed at the farm.",
            STEP_PACKAGE_PICKED: "Package picked up from farm & verified by Head Office.",
            STEP_OUT_FOR_DELIVERY: "Rider is coming to deliver the order at your home.",
            STEP_ABOUT_TO_ARRIVE: "Rider is about to arrive at your address!",
            STEP_ARRIVED: "Rider arrived / Your order has arrived at your doorstep!",
            STEP_DELIVERED: f"Order #{order.order_id} delivered successfully! Thank you for ordering fresh farm harvest.",
        }

        notif_msg = consumer_msg_map.get(next_step, f"Order #{order.order_id}: {step_desc}")
        db.add(Notification(
            user_id=order.consumer_id,
            title=f"Delivery Update: {step_desc}",
            message=notif_msg
        ))

        # Also log to admin
        db.add(Notification(
            user_id=1,
            title=f"Order #{order.order_id} Status: {step_desc}",
            message=f"Rider {rider_name} updated order #{order.order_id} to '{step_desc}'."
        ))

        db.commit()
        logger.info("Order %d advanced to step '%s' by rider %s.", order_id, next_step, rider_name)
        return True, f"Milestone updated: {step_desc}"

    @staticmethod
    def upload_package_photo(db: Session, order_id: int, rider_id: int, file_content: bytes, filename: str) -> Tuple[bool, str, str]:
        """
        Saves package verification photo and notifies Head Office (Admin).
        Unlocks the 'Delivering order to address' button.
        """
        order = db.query(Order).filter(Order.order_id == order_id).first()
        if not order:
            return False, "Order not found.", ""

        if order.delivery_partner_id != rider_id:
            return False, "Unauthorized: You are not assigned to this delivery.", ""

        # Ensure directory exists
        pkg_dir = settings.UPLOAD_DIR / "packages"
        pkg_dir.mkdir(parents=True, exist_ok=True)

        ext = os.path.splitext(filename)[1].lower() or ".jpg"
        clean_ext = ext if ext in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"
        save_name = f"package_order_{order_id}_{int(time.time())}{clean_ext}"
        target_path = pkg_dir / save_name

        try:
            with open(target_path, "wb") as f:
                f.write(file_content)
        except Exception as e:
            logger.exception("Failed to write package photo: %s", e)
            return False, f"Failed to save photo: {str(e)}", ""

        photo_url = f"/uploads/packages/{save_name}"
        order.package_photo = photo_url
        order.package_photo_at = get_ist_now()
        order.delivery_step = STEP_PACKAGE_PICKED
        order.status = STATUS_PICKED_UP
        order.updated_at = get_ist_now()

        rider = db.query(User).filter(User.id == rider_id).first()
        rider_name = rider.full_name if rider else "Delivery Partner"

        # Notify Head Office (Admin)
        db.add(Notification(
            user_id=1,
            title="Package Photo Received (Head Office)",
            message=f"Order #{order_id} package photo uploaded by rider {rider_name} from the farm. Verification complete."
        ))

        # Notify Consumer
        db.add(Notification(
            user_id=order.consumer_id,
            title="Package Picked Up from Farm",
            message=f"Rider {rider_name} has verified and picked up your package from the farmer."
        ))

        db.commit()
        logger.info("Package photo saved for Order %d at %s", order_id, photo_url)
        return True, "Package photo sent to Head Office successfully! You can now proceed to deliver the order.", photo_url

    @staticmethod
    def update_rider_gps(
        db: Session,
        rider_id: int,
        order_id: Optional[int],
        latitude: float,
        longitude: float,
        speed: float = 0.0
    ) -> bool:
        """Updates live GPS coordinates for rider profile and active order."""
        try:
            now = get_ist_now()
            # Update delivery partner profile
            prof = db.query(DeliveryPartnerProfile).filter(DeliveryPartnerProfile.delivery_id == rider_id).first()
            if prof:
                prof.current_latitude = round(latitude, 5)
                prof.current_longitude = round(longitude, 5)
                prof.last_active_at = now

            # If associated with an active order, update order coordinates
            if order_id:
                order = db.query(Order).filter(Order.order_id == order_id).first()
                if order and order.delivery_partner_id == rider_id:
                    order.rider_latitude = round(latitude, 5)
                    order.rider_longitude = round(longitude, 5)
                    order.rider_last_loc_update = now

            db.commit()
            return True
        except Exception:
            logger.exception("Failed to update rider GPS coordinates.")
            return False

    @staticmethod
    def get_live_tracking_data(db: Session, order_id: int) -> Dict[str, Any]:
        """
        Compiles the complete real-time tracking payload for Consumer, Admin, and Rider views.
        Includes coordinates, routing waypoints, package photo, step index, and Google Maps links.
        """
        order = db.query(Order).filter(Order.order_id == order_id).first()
        if not order:
            return {"success": False, "error": "Order not found"}

        farmer_addr = order.farmer.address if order.farmer and order.farmer.address else (order.crop.location if order.crop else "Indore, MP")
        consumer_addr = order.delivery_address or "Indore, MP"

        farmer_lat, farmer_lng = GeocodingService.get_coordinates_for_address(farmer_addr)
        consumer_lat, consumer_lng = GeocodingService.get_coordinates_for_address(consumer_addr, fallback_offset=1.5)

        # Rider current location: use live GPS if updated, else extrapolate based on current step
        step = order.delivery_step or STEP_ACCEPTED
        if order.rider_latitude and order.rider_longitude:
            rider_lat = order.rider_latitude
            rider_lng = order.rider_longitude
        else:
            if step in (STEP_ACCEPTED, STEP_HEADING_TO_FARMER):
                rider_lat = round(farmer_lat - 0.012, 5)
                rider_lng = round(farmer_lng - 0.012, 5)
            elif step in (STEP_PACKING, STEP_PACKAGE_PICKED):
                rider_lat = farmer_lat
                rider_lng = farmer_lng
            elif step == STEP_OUT_FOR_DELIVERY:
                rider_lat = round((farmer_lat + consumer_lat) / 2.0, 5)
                rider_lng = round((farmer_lng + consumer_lng) / 2.0, 5)
            elif step == STEP_ABOUT_TO_ARRIVE:
                rider_lat = round(consumer_lat - 0.003, 5)
                rider_lng = round(consumer_lng - 0.003, 5)
            else:
                rider_lat = consumer_lat
                rider_lng = consumer_lng

        # Route waypoints: Rider -> Farmer -> Consumer
        route_to_farm = GeocodingService.interpolate_route((rider_lat, rider_lng), (farmer_lat, farmer_lng), num_points=8)
        route_to_consumer = GeocodingService.interpolate_route((farmer_lat, farmer_lng), (consumer_lat, consumer_lng), num_points=12)
        full_route = route_to_farm + route_to_consumer[1:]

        # Distance & ETA calculations
        if step in (STEP_ACCEPTED, STEP_HEADING_TO_FARMER, STEP_PACKING):
            dist_km = GeocodingService.calculate_haversine_distance_km((rider_lat, rider_lng), (farmer_lat, farmer_lng))
            target_destination = "Farm Pickup"
        else:
            dist_km = GeocodingService.calculate_haversine_distance_km((rider_lat, rider_lng), (consumer_lat, consumer_lng))
            target_destination = "Customer Address"

        eta_min = GeocodingService.estimate_eta_minutes(dist_km)

        # Step index for progress bar
        step_index = 1
        if step in DELIVERY_STEPS_FLOW:
            step_index = DELIVERY_STEPS_FLOW.index(step) + 1

        rider_user = order.delivery_partner
        rider_prof = rider_user.delivery_profile if rider_user else None

        # Google Maps navigation external URL for mobile riders
        next_target_lat = farmer_lat if step in (STEP_ACCEPTED, STEP_HEADING_TO_FARMER, STEP_PACKING) else consumer_lat
        next_target_lng = farmer_lng if step in (STEP_ACCEPTED, STEP_HEADING_TO_FARMER, STEP_PACKING) else consumer_lng
        gmaps_nav_url = (
            f"https://www.google.com/maps/dir/?api=1&origin={rider_lat},{rider_lng}"
            f"&destination={next_target_lat},{next_target_lng}&travelmode=driving"
        )

        return {
            "success": True,
            "order_id": order.order_id,
            "crop_name": order.crop.crop_name if order.crop else f"Crop #{order.crop_id}",
            "quantity": order.quantity,
            "unit": order.crop.unit if order.crop else "KG",
            "total_amount": order.total_amount,
            "payment_method": order.payment_method,
            "payment_status": order.payment_status,
            "status": order.status,
            "delivery_step": step,
            "step_index": step_index,
            "step_description": DELIVERY_STEP_DESCRIPTIONS.get(step, step),
            "distance_km": dist_km,
            "eta_minutes": eta_min,
            "target_destination": target_destination,
            "package_photo": order.package_photo,
            "package_photo_at": format_ist_datetime(order.package_photo_at) if order.package_photo_at else None,
            "has_package_photo": bool(order.package_photo),
            "delivery_otp": order.delivery_otp,
            "rider": {
                "id": rider_user.id if rider_user else None,
                "name": rider_user.full_name if rider_user else "Unassigned",
                "phone": rider_user.phone if rider_user else "N/A",
                "vehicle": (rider_prof.vehicle_type if rider_prof and rider_prof.vehicle_type else "Bike") if rider_prof else "Bike",
                "license": (rider_prof.license_number if rider_prof else "") or "N/A",
                "rating": rider_prof.rating if rider_prof else 5.0,
                "lat": rider_lat,
                "lng": rider_lng,
            },
            "farmer": {
                "name": order.farmer.full_name if order.farmer else "Farmer",
                "phone": order.farmer.phone if order.farmer else "N/A",
                "address": farmer_addr,
                "lat": farmer_lat,
                "lng": farmer_lng,
            },
            "consumer": {
                "name": order.consumer.full_name if order.consumer else "Customer",
                "phone": order.consumer.phone if order.consumer else "N/A",
                "address": consumer_addr,
                "lat": consumer_lat,
                "lng": consumer_lng,
            },
            "route_waypoints": full_route,
            "gmaps_nav_url": gmaps_nav_url,
            "google_maps_api_key": os.getenv("GOOGLE_MAPS_API_KEY", "").strip(),
            "updated_at": format_ist_datetime(order.updated_at),
        }
