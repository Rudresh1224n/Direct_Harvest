from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from app.database import Base
from app.utils.ist_time import get_ist_now

class Review(Base):
    __tablename__ = "reviews"

    review_id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.order_id", ondelete="CASCADE"), unique=True, nullable=False)
    farmer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    consumer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    crop_id = Column(Integer, ForeignKey("crops.crop_id", ondelete="SET NULL"), nullable=True)

    rating = Column(Integer, nullable=False)
    review_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_ist_now, nullable=False)

    __table_args__ = (
        CheckConstraint("rating >= 1 AND rating <= 5", name="chk_review_rating_1_to_5"),
    )

    order = relationship("Order", back_populates="review")
    farmer = relationship("User", foreign_keys=[farmer_id], back_populates="reviews_received")
    consumer = relationship("User", foreign_keys=[consumer_id], back_populates="reviews_written")
    crop = relationship("Crop", back_populates="reviews")
