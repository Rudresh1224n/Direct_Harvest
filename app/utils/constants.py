# User Roles
ROLE_ADMIN = "admin"
ROLE_FARMER = "farmer"
ROLE_CONSUMER = "consumer"
ROLE_DELIVERY = "delivery"

ALL_ROLES = [ROLE_ADMIN, ROLE_FARMER, ROLE_CONSUMER, ROLE_DELIVERY]

# Order Statuses
STATUS_PENDING = "Pending"
STATUS_ACCEPTED = "Accepted"
STATUS_ASSIGNED = "Assigned"
STATUS_REACHED_HUB = "Reached Godown"
STATUS_PICKED_UP = "Picked Up"
STATUS_IN_TRANSIT = "In Transit"
STATUS_DELIVERED = "Delivered"
STATUS_CANCELLED = "Cancelled"

ORDER_STATUSES = [
    STATUS_PENDING,
    STATUS_ACCEPTED,
    STATUS_ASSIGNED,
    STATUS_REACHED_HUB,
    STATUS_PICKED_UP,
    STATUS_IN_TRANSIT,
    STATUS_DELIVERED,
    STATUS_CANCELLED,
]

# Delivery Rider Step Progression
STEP_ACCEPTED = "rider_accepted"           # 1. Rider accepted the order
STEP_HEADING_TO_FARMER = "heading_to_farmer"# 2. Rider is on the way to reach the farmer
STEP_PACKING = "order_packing"              # 3. Your order is getting packed
STEP_PACKAGE_PICKED = "package_picked"      # 4. Package photo sent to Head Office & verified
STEP_OUT_FOR_DELIVERY = "out_for_delivery"  # 5. Rider is coming to deliver the order at your home
STEP_ABOUT_TO_ARRIVE = "about_to_arrive"    # 6. Rider about to arrive
STEP_ARRIVED = "rider_arrived"              # 7. Rider arrived / Your order is arrived
STEP_DELIVERED = "delivered"                # 8. Delivered

DELIVERY_STEPS_FLOW = [
    STEP_ACCEPTED,
    STEP_HEADING_TO_FARMER,
    STEP_PACKING,
    STEP_PACKAGE_PICKED,
    STEP_OUT_FOR_DELIVERY,
    STEP_ABOUT_TO_ARRIVE,
    STEP_ARRIVED,
    STEP_DELIVERED,
]

DELIVERY_STEP_DESCRIPTIONS = {
    STEP_ACCEPTED: "Rider accepted the order",
    STEP_HEADING_TO_FARMER: "Rider is on the way to reach the farmer",
    STEP_PACKING: "Your order is getting packed",
    STEP_PACKAGE_PICKED: "Package picked up from farm & verified by Head Office",
    STEP_OUT_FOR_DELIVERY: "Rider is coming to deliver the order at your home",
    STEP_ABOUT_TO_ARRIVE: "Rider about to arrive",
    STEP_ARRIVED: "Rider arrived / Your order is arrived",
    STEP_DELIVERED: "Order successfully delivered",
}

# Payment Statuses
PAYMENT_PENDING = "Pending"
PAYMENT_PAID = "Paid"
PAYMENT_REFUNDED = "Refunded"

# Categories
CATEGORIES = [
    "Vegetables",
    "Fruits",
    "Grains",
    "Pulses",
    "Spices",
    "Dairy",
    "Organic"
]
