
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session, joinedload

from app.models.crop import Crop
from app.models.order import Order
from app.services.ai_service import MANDI_REFERENCE_PRICES
from app.utils.constants import STATUS_DELIVERED


class InsightsService:

    @staticmethod
    def get_price_analytics_for_crop(
        db: Session, crop_name: str
    ) -> Dict[str, Any]:
        """Calculate listing prices and compare them with a mandi benchmark."""

        clean_name = crop_name.strip().lower()
        benchmark_price = MANDI_REFERENCE_PRICES.get(
            clean_name, 35.0
        )

        crops = (
            db.query(Crop)
            .filter(
                Crop.crop_name.ilike(f"%{crop_name.strip()}%"),
                Crop.status == "available",
                Crop.quantity_available > 0,
            )
            .all()
        )

        if not crops:
            return {
                "crop_name": crop_name,
                "total_listings": 0,
                "min_price": benchmark_price,
                "max_price": benchmark_price,
                "avg_price": benchmark_price,
                "median_price": benchmark_price,
                "benchmark_mandi_price": benchmark_price,
                "sample_count": 0,
            }

        prices = pd.to_numeric(
            pd.Series([crop.farmer_price for crop in crops]),
            errors="coerce",
        ).dropna()

        prices = prices[prices >= 0]

        if prices.empty:
            prices = pd.Series([benchmark_price])

        return {
            "crop_name": crop_name,
            "total_listings": len(crops),
            "min_price": round(float(prices.min()), 2),
            "max_price": round(float(prices.max()), 2),
            "avg_price": round(float(prices.mean()), 2),
            "median_price": round(float(prices.median()), 2),
            "benchmark_mandi_price": benchmark_price,
            "sample_count": int(len(prices)),
        }

    @staticmethod
    def get_market_demand_summary(
        db: Session,
    ) -> Dict[str, Any]:
        """Summarize completed sales rather than counting unfulfilled orders."""

        orders = (
            db.query(Order)
            .options(joinedload(Order.crop))
            .filter(Order.status == STATUS_DELIVERED)
            .all()
        )

        if not orders:
            return {
                "popular_crops": [],
                "total_volume_sold_kg": 0.0,
                "total_orders_count": 0,
                "top_demanded_category": "Vegetables",
            }

        records = []

        for order in orders:
            crop = order.crop

            records.append({
                "crop_name": (
                    crop.crop_name if crop else f"Crop #{order.crop_id}"
                ),
                "category": crop.category if crop else "General",
                "quantity": float(order.quantity or 0),
                "amount": float(order.total_amount or 0),
            })

        df = pd.DataFrame(records)

        grouped = (
            df.groupby("crop_name", as_index=False)
            .agg(
                total_sold_qty=("quantity", "sum"),
                total_revenue=("amount", "sum"),
            )
            .sort_values(
                by=["total_sold_qty", "crop_name"],
                ascending=[False, True],
            )
        )

        popular_crops = grouped.head(5).to_dict(orient="records")

        top_category = (
            df["category"].mode().iloc[0]
            if not df.empty
            else "Vegetables"
        )

        return {
            "popular_crops": [
                {
                    "crop_name": item["crop_name"],
                    "total_sold_qty": round(
                        float(item["total_sold_qty"]), 2
                    ),
                    "total_revenue": round(
                        float(item["total_revenue"]), 2
                    ),
                }
                for item in popular_crops
            ],
            "total_volume_sold_kg": round(
                float(df["quantity"].sum()), 2
            ),
            "total_orders_count": len(orders),
            "top_demanded_category": top_category,
        }

    @staticmethod
    def get_recommendations_for_consumer(
        db: Session,
        consumer_id: Optional[int] = None,
        limit: int = 4,
    ) -> List[Crop]:
        """Recommend available crops using past purchases and freshness."""

        limit = max(1, min(limit, 20))
        preferred_category = None

        if consumer_id is not None:
            past_orders = (
                db.query(Order)
                .options(joinedload(Order.crop))
                .filter(
                    Order.consumer_id == consumer_id,
                    Order.status == STATUS_DELIVERED,
                )
                .all()
            )

            categories = [
                order.crop.category
                for order in past_orders
                if order.crop is not None
            ]

            if categories:
                preferred_category = max(
                    set(categories),
                    key=categories.count,
                )

        query = db.query(Crop).filter(
            Crop.status == "available",
            Crop.quantity_available > 0,
        )

        if preferred_category:
            preferred_crops = (
                query.filter(Crop.category == preferred_category)
                .order_by(
                    desc(Crop.freshness_score),
                    Crop.farmer_price,
                )
                .limit(limit)
                .all()
            )

            if len(preferred_crops) >= limit:
                return preferred_crops

            selected_ids = {
                crop.crop_id for crop in preferred_crops
            }

            remaining = (
                query.filter(
                    ~Crop.crop_id.in_(selected_ids)
                )
                .order_by(
                    desc(Crop.freshness_score),
                    Crop.farmer_price,
                )
                .limit(limit - len(preferred_crops))
                .all()
            )

            return preferred_crops + remaining

        return (
            query.order_by(
                desc(Crop.freshness_score),
                Crop.farmer_price,
            )
            .limit(limit)
            .all()
        )
