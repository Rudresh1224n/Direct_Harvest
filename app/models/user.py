from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, CheckConstraint, Boolean
from sqlalchemy.orm import relationship
from app.database import Base
from app.utils.ist_time import get_ist_now

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(120), unique=True, nullable=False, index=True)
    phone = Column(String(25), nullable=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, index=True)  # admin, farmer, consumer, delivery
    address = Column(Text, nullable=True)
    status = Column(String(20), default="Active", nullable=False)  # Active, Inactive, Suspended
    created_at = Column(DateTime, default=get_ist_now, nullable=False)

    # Relationships
    farmer_profile = relationship("FarmerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    consumer_profile = relationship("ConsumerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    delivery_profile = relationship("DeliveryPartnerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    wallet = relationship("Wallet", back_populates="user", uselist=False, cascade="all, delete-orphan")

    crops = relationship("Crop", back_populates="farmer", cascade="all, delete-orphan")
    orders_as_consumer = relationship("Order", foreign_keys="Order.consumer_id", back_populates="consumer")
    orders_as_farmer = relationship("Order", foreign_keys="Order.farmer_id", back_populates="farmer")
    orders_as_delivery = relationship("Order", foreign_keys="Order.delivery_partner_id", back_populates="delivery_partner")

    cart_items = relationship("CartItem", back_populates="consumer", cascade="all, delete-orphan")
    reviews_written = relationship("Review", foreign_keys="Review.consumer_id", back_populates="consumer")
    reviews_received = relationship("Review", foreign_keys="Review.farmer_id", back_populates="farmer")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")


class FarmerProfile(Base):
    __tablename__ = "farmers"

    farmer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    farm_name = Column(String(120), nullable=True)
    trust_score = Column(Float, default=5.0)
    ranking = Column(Integer, default=0)
    total_sales = Column(Float, default=0.0)
    total_orders = Column(Integer, default=0)

    user = relationship("User", back_populates="farmer_profile")


class ConsumerProfile(Base):
    __tablename__ = "consumers"

    consumer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    total_orders = Column(Integer, default=0)
    preferred_categories = Column(String(255), nullable=True)

    user = relationship("User", back_populates="consumer_profile")


class DeliveryPartnerProfile(Base):
    __tablename__ = "delivery_partners"

    delivery_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    vehicle_type = Column(String(50), nullable=True)
    license_number = Column(String(50), nullable=True)
    rating = Column(Float, default=5.0)
    completed_deliveries = Column(Integer, default=0)
    is_available = Column(Integer, default=1)  # 1 = available, 0 = busy/offline
    is_online = Column(Boolean, default=True, nullable=True)
    current_latitude = Column(Float, nullable=True)
    current_longitude = Column(Float, nullable=True)
    last_active_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="delivery_profile")
