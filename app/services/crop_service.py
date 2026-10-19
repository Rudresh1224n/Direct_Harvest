
from typing import List, Optional

from sqlalchemy import or_, desc
from sqlalchemy.orm import Session

from app.models.crop import Crop
from app.models.order import Order, CartItem
from app.schemas.crop import CropCreate, CropUpdate


class CropService:

    @staticmethod
    def get_all_crops(
        db: Session,
        category: Optional[str] = None,
        search: Optional[str] = None,
        grade: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        location: Optional[str] = None,
        status: str = "available",
        limit: int = 100,
        offset: int = 0,
    ) -> List[Crop]:
        query = db.query(Crop)

        if status:
            query = query.filter(Crop.status == status)

        if category and category.lower() != "all":
            query = query.filter(Crop.category.ilike(f"%{category.strip()}%"))

        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    Crop.crop_name.ilike(term),
                    Crop.description.ilike(term),
                    Crop.location.ilike(term),
                )
            )

        if grade and grade.lower() != "all":
            query = query.filter(Crop.quality_grade == grade)

        if min_price is not None:
            query = query.filter(Crop.farmer_price >= min_price)

        if max_price is not None:
            query = query.filter(Crop.farmer_price <= max_price)

        if location and location.strip():
            query = query.filter(
                Crop.location.ilike(f"%{location.strip()}%")
            )

        return (
            query.order_by(desc(Crop.created_at))
            .offset(max(0, offset))
            .limit(max(1, min(limit, 500)))
            .all()
        )

    @staticmethod
    def get_crop_by_id(
        db: Session, crop_id: int
    ) -> Optional[Crop]:
        return (
            db.query(Crop)
            .filter(Crop.crop_id == crop_id)
            .first()
        )

    @staticmethod
    def get_crops_by_farmer(
        db: Session, farmer_id: int
    ) -> List[Crop]:
        return (
            db.query(Crop)
            .filter(Crop.farmer_id == farmer_id)
            .order_by(desc(Crop.created_at))
            .all()
        )

    @staticmethod
    def create_crop(
        db: Session,
        farmer_id: int,
        crop_data: CropCreate,
        crop_image: Optional[str] = None,
        quality_grade: str = "A",
        freshness_score: float = 90.0,
        demand_score: float = 80.0,
        demand_level: str = "Medium",
        ai_suggested_price: Optional[float] = None,
        market_suitability: str = "Good",
    ) -> Crop:
        quantity = crop_data.quantity_available
        price = crop_data.farmer_price

        if quantity < 0:
            raise ValueError("Quantity cannot be negative.")

        if price < 0:
            raise ValueError("Price cannot be negative.")

        if not crop_data.crop_name.strip():
            raise ValueError("Crop name is required.")

        if not crop_data.category.strip():
            raise ValueError("Crop category is required.")

        crop = Crop(
            farmer_id=farmer_id,
            crop_name=crop_data.crop_name.strip(),
            category=crop_data.category.strip(),
            quantity_available=quantity,
            unit=(crop_data.unit or "KG").strip().upper(),
            farmer_price=price,
            ai_suggested_price=(
                ai_suggested_price
                if ai_suggested_price is not None
                else price
            ),
            description=(
                crop_data.description.strip()
                if crop_data.description
                else None
            ),
            crop_image=crop_image,
            quality_grade=quality_grade,
            freshness_score=freshness_score,
            demand_score=demand_score,
            demand_level=demand_level,
            market_suitability=market_suitability,
            location=(
                crop_data.location.strip()
                if crop_data.location
                else None
            ),
            status="available" if quantity > 0 else "out_of_stock",
        )

        try:
            db.add(crop)
            db.commit()
            db.refresh(crop)
            return crop
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def update_crop(
        db: Session,
        crop_id: int,
        farmer_id: int,
        update_data: CropUpdate,
        crop_image: Optional[str] = None,
    ) -> Crop:
        crop = (
            db.query(Crop)
            .filter(Crop.crop_id == crop_id)
            .first()
        )

        if not crop:
            raise ValueError("Crop listing not found.")

        if crop.farmer_id != farmer_id:
            raise PermissionError(
                "You do not have permission to modify this listing."
            )

        quantity = update_data.quantity_available
        price = update_data.farmer_price

        if quantity is not None and quantity < 0:
            raise ValueError("Quantity cannot be negative.")

        if price is not None and price < 0:
            raise ValueError("Price cannot be negative.")

        if update_data.crop_name is not None:
            if not update_data.crop_name.strip():
                raise ValueError("Crop name cannot be empty.")
            crop.crop_name = update_data.crop_name.strip()

        if update_data.category is not None:
            if not update_data.category.strip():
                raise ValueError("Category cannot be empty.")
            crop.category = update_data.category.strip()

        if quantity is not None:
            crop.quantity_available = quantity
            if quantity == 0:
                crop.status = "out_of_stock"
            elif crop.status == "out_of_stock":
                crop.status = "available"

        if update_data.unit is not None:
            crop.unit = update_data.unit.strip().upper()

        if price is not None:
            crop.farmer_price = price

        if update_data.description is not None:
            crop.description = update_data.description.strip()

        if update_data.location is not None:
            crop.location = update_data.location.strip()

        if update_data.status is not None:
            if update_data.status == "available" and crop.quantity_available <= 0:
                raise ValueError(
                    "A crop with zero stock cannot be marked available."
                )
            crop.status = update_data.status

        if crop_image:
            crop.crop_image = crop_image

        try:
            db.commit()
            db.refresh(crop)
            return crop
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def delete_crop(
        db: Session, crop_id: int, farmer_id: int
    ) -> bool:
        crop = (
            db.query(Crop)
            .filter(Crop.crop_id == crop_id)
            .first()
        )

        if not crop:
            return False

        if crop.farmer_id != farmer_id:
            raise PermissionError(
                "You do not have permission to delete this listing."
            )

        # Preserve order history; remove the listing from sale instead.
        has_orders = (
            db.query(Order.order_id)
            .filter(Order.crop_id == crop_id)
            .first()
        )

        if has_orders:
            crop.status = "inactive"
            crop.quantity_available = 0
        else:
            db.query(CartItem).filter(
                CartItem.crop_id == crop_id
            ).delete(synchronize_session=False)
            db.delete(crop)

        try:
            db.commit()
            return True
        except Exception:
            db.rollback()
            raise
