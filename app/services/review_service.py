
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.review import Review
from app.models.order import Order
from app.services.trust_score_service import TrustScoreService
from app.utils.constants import STATUS_DELIVERED


class ReviewService:

    @staticmethod
    def add_review(
        db: Session,
        consumer_id: int,
        order_id: int,
        rating: int,
        review_text: Optional[str] = None,
    ) -> Review:
        if not isinstance(rating, int) or isinstance(rating, bool):
            raise ValueError("Rating must be an integer from 1 to 5.")

        if rating < 1 or rating > 5:
            raise ValueError("Rating must be between 1 and 5 stars.")

        text = review_text.strip() if review_text else None

        if text and len(text) > 5000:
            raise ValueError("Review text cannot exceed 5000 characters.")

        try:
            order = (
                db.query(Order)
                .filter(Order.order_id == order_id)
                .with_for_update()
                .first()
            )

            if not order:
                raise ValueError("Order not found.")

            if order.consumer_id != consumer_id:
                raise PermissionError(
                    "You can only review orders placed by your account."
                )

            if order.status != STATUS_DELIVERED:
                raise ValueError(
                    "Reviews can only be submitted for delivered orders."
                )

            existing = (
                db.query(Review)
                .filter(Review.order_id == order_id)
                .first()
            )

            if existing:
                raise ValueError(
                    "You have already submitted a review for this order."
                )

            review = Review(
                order_id=order.order_id,
                farmer_id=order.farmer_id,
                consumer_id=consumer_id,
                crop_id=order.crop_id,
                rating=rating,
                review_text=text,
            )

            db.add(review)
            db.flush()

            # Recalculate the score in the same database transaction.
            TrustScoreService.calculate_farmer_trust_score(
                db, order.farmer_id
            )

            db.commit()
            db.refresh(review)
            return review

        except Exception:
            db.rollback()
            raise

    @staticmethod
    def get_reviews_for_farmer(
        db: Session, farmer_id: int
    ) -> List[Review]:
        return (
            db.query(Review)
            .filter(Review.farmer_id == farmer_id)
            .order_by(Review.created_at.desc())
            .all()
        )
