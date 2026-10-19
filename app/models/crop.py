from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from app.database import Base
from app.utils.ist_time import get_ist_now

class Crop(Base):
    __tablename__ = "crops"

    crop_id = Column(Integer, primary_key=True, autoincrement=True, index=True)
    farmer_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    crop_name = Column(String(100), nullable=False, index=True)
    category = Column(String(50), nullable=False, index=True)
    quantity_available = Column(Float, nullable=False, default=0.0)
    unit = Column(String(20), default="KG", nullable=False)
    farmer_price = Column(Float, nullable=False)
    ai_suggested_price = Column(Float, nullable=True)
    description = Column(Text, nullable=True)
    crop_image = Column(String(255), nullable=True)
    quality_grade = Column(String(10), default="A")
    freshness_score = Column(Float, default=90.0)
    demand_score = Column(Float, default=80.0)
    demand_level = Column(String(20), default="Medium")
    market_suitability = Column(String(50), default="Good")
    location = Column(String(150), nullable=True)
    status = Column(String(20), default="available", nullable=False)  # available, out_of_stock, inactive
    created_at = Column(DateTime, default=get_ist_now, nullable=False)

    __table_args__ = (
        CheckConstraint("quantity_available >= 0", name="chk_crop_positive_quantity"),
        CheckConstraint("farmer_price >= 0", name="chk_crop_positive_price"),
    )

    # Relationships
    farmer = relationship("User", back_populates="crops")
    assessments = relationship("CropAssessment", back_populates="crop", cascade="all, delete-orphan")
    orders = relationship("Order", back_populates="crop")
    cart_items = relationship("CartItem", back_populates="crop", cascade="all, delete-orphan")
    reviews = relationship("Review", back_populates="crop")


class CropAssessment(Base):
    __tablename__ = "ai_analysis"

    analysis_id = Column(Integer, primary_key=True, autoincrement=True)
    crop_id = Column(Integer, ForeignKey("crops.crop_id", ondelete="CASCADE"), nullable=True)
    image_path = Column(String(255), nullable=True)
    quality_grade = Column(String(10), default="A")
    freshness_score = Column(Float, default=90.0)
    uniformity_score = Column(Float, default=90.0)
    color_distribution = Column(Text, nullable=True)  # JSON formatted HSV and RGB statistics
    defect_percentage = Column(Float, default=0.0)
    suggested_price = Column(Float, nullable=True)
    market_suitability = Column(String(50), default="Good")
    assessment_method = Column(String(50), default="OpenCV-ComputerVision")
    analysis_date = Column(DateTime, default=get_ist_now, nullable=False)

    crop = relationship("Crop", back_populates="assessments")
