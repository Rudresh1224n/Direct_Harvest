from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from app.database import Base
from app.utils.ist_time import get_ist_now
from app.utils.constants import STATUS_PENDING, PAYMENT_PENDING

class Order(Base):
    __tablename__ = "orders"

    order_id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    consumer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    farmer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    crop_id = Column(Integer, ForeignKey("crops.crop_id"), nullable=False, index=True)
    delivery_partner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    quantity = Column(Float, nullable=False)
    price_per_kg = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)
    delivery_charge = Column(Float, default=30.0, nullable=False)
    discount = Column(Float, default=0.0, nullable=False)
    total_amount = Column(Float, nullable=False)

    delivery_address = Column(Text, nullable=False)
    payment_method = Column(String(50), default="Cash on Delivery", nullable=False)
    payment_status = Column(String(30), default=PAYMENT_PENDING, nullable=False)
    status = Column(String(30), default=STATUS_PENDING, nullable=False, index=True)

    order_date = Column(DateTime, default=get_ist_now, nullable=False)
    updated_at = Column(DateTime, default=get_ist_now, onupdate=get_ist_now, nullable=False)

    # Delivery Rider Progression & Live Tracking fields
    delivery_step = Column(String(50), default="assigned", nullable=True)
    package_photo = Column(String(255), nullable=True)
    package_photo_at = Column(DateTime, nullable=True)
    rider_latitude = Column(Float, nullable=True)
    rider_longitude = Column(Float, nullable=True)
    rider_last_loc_update = Column(DateTime, nullable=True)
    delivery_otp = Column(String(10), nullable=True)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_order_quantity_positive"),
        CheckConstraint("total_amount >= 0", name="chk_order_total_positive"),
    )

    # Relationships
    consumer = relationship("User", foreign_keys=[consumer_id], back_populates="orders_as_consumer")
    farmer = relationship("User", foreign_keys=[farmer_id], back_populates="orders_as_farmer")
    crop = relationship("Crop", back_populates="orders")
    delivery_partner = relationship("User", foreign_keys=[delivery_partner_id], back_populates="orders_as_delivery")
    review = relationship("Review", back_populates="order", uselist=False, cascade="all, delete-orphan")


class CartItem(Base):
    __tablename__ = "cart"

    cart_id = Column(Integer, primary_key=True, autoincrement=True)
    consumer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    crop_id = Column(Integer, ForeignKey("crops.crop_id", ondelete="CASCADE"), nullable=False)
    quantity = Column(Float, nullable=False, default=1.0)
    added_at = Column(DateTime, default=get_ist_now, nullable=False)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_cart_quantity_positive"),
    )

    consumer = relationship("User", back_populates="cart_items")
    crop = relationship("Crop", back_populates="cart_items")
