
from typing import Any, Dict

from sqlalchemy.orm import Session

from app.models.review import Review
from app.models.order import Order
from app.models.user import FarmerProfile
from app.utils.constants import STATUS_DELIVERED, STATUS_CANCELLED


class TrustScoreService:

    @staticmethod
    def calculate_farmer_trust_score(
        db: Session,
        farmer_id: int,
        commit: bool = True,
    ) -> Dict[str, Any]:
        reviews = (
            db.query(Review)
            .filter(Review.farmer_id == farmer_id)
            .all()
        )

        total_reviews = len(reviews)
        average_rating = (
            sum(review.rating for review in reviews) / total_reviews
            if total_reviews
            else 5.0
        )

        orders = (
            db.query(Order)
            .filter(Order.farmer_id == farmer_id)
            .all()
        )

        total_orders = len(orders)
        delivered_orders = sum(
            order.status == STATUS_DELIVERED for order in orders
        )
        cancelled_orders = sum(
            order.status == STATUS_CANCELLED for order in orders
        )

        fulfillment_rate = (
            delivered_orders / total_orders if total_orders else 1.0
        )
        cancellation_rate = (
            cancelled_orders / total_orders if total_orders else 0.0
        )
        cancellation_health = max(0.0, 1.0 - cancellation_rate)

        rating_points = average_rating * 0.50
        fulfillment_points = fulfillment_rate * 5.0 * 0.35
        cancellation_points = cancellation_health * 5.0 * 0.15

        final_score = round(
            rating_points + fulfillment_points + cancellation_points, 1
        )
        final_score = max(1.0, min(5.0, final_score))

        profile = (
            db.query(FarmerProfile)
            .filter(FarmerProfile.farmer_id == farmer_id)
            .first()
        )

        if profile:
            profile.trust_score = final_score
            profile.total_orders = total_orders
            profile.total_sales = sum(
                order.total_amount
                for order in orders
                if order.status == STATUS_DELIVERED
            )

            if commit:
                db.commit()
            else:
                db.flush()

        return {
            "trust_score": final_score,
            "average_rating": round(average_rating, 1),
            "total_reviews": total_reviews,
            "total_orders": total_orders,
            "delivered_orders": delivered_orders,
            "cancelled_orders": cancelled_orders,
            "fulfillment_percentage": round(
                fulfillment_rate * 100.0, 1
            ),
            "cancellation_percentage": round(
                cancellation_rate * 100.0, 1
            ),
            "formula_breakdown": {
                "rating_contribution": round(rating_points, 2),
                "fulfillment_contribution": round(
                    fulfillment_points, 2
                ),
                "cancellation_contribution": round(
                    cancellation_points, 2
                ),
                "max_possible": 5.0,
            },
        }
