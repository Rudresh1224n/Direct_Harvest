from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.templates_config import templates
from app.models.crop import Crop
from app.models.user import User, FarmerProfile, ConsumerProfile
from app.models.order import Order
from app.models.review import Review
from app.services.crop_service import CropService
from app.services.insights_service import InsightsService
from app.dependencies.auth import get_current_user_optional
from app.utils.constants import CATEGORIES

router = APIRouter(tags=["Public"])

def format_crop_for_template(crop: Crop) -> Dict[str, Any]:
    """Helper to convert Crop ORM object into a dictionary with UI convenience fields."""
    farmer_name = crop.farmer.full_name if crop.farmer else "Farmer"
    farmer_phone = crop.farmer.phone if crop.farmer else ""
    farmer_address = crop.farmer.address if crop.farmer else (crop.location or "Madhya Pradesh, India")
    trust_score = crop.farmer.farmer_profile.trust_score if (crop.farmer and crop.farmer.farmer_profile) else 5.0

    # Profit indicator based on AI suggested price vs farmer price
    profit_diff = (crop.farmer_price - (crop.ai_suggested_price or crop.farmer_price))
    if profit_diff <= 0:
        profit_status = "Fair Deal"
        profit_class = "success"
    elif profit_diff < 5:
        profit_status = "Market Rate"
        profit_class = "info"
    else:
        profit_status = "Premium Grade"
        profit_class = "warning"

    img_src = crop.crop_image or ""
    if not img_src:
        if crop.category.lower() in ("grain", "grains"):
            img_src = "https://images.unsplash.com/photo-1582515073490-dc6c39f8b5d8"
        elif crop.category.lower() in ("fruit", "fruits"):
            img_src = "https://images.unsplash.com/photo-1519996529931-28324d5a630e"
        else:
            img_src = "https://images.unsplash.com/photo-1546470427-e5ac89cd0b3b"
    elif not img_src.startswith("http"):
        img_src = f"/static/uploads/crop_images/{img_src}"

    return {
        "crop_id": crop.crop_id,
        "farmer_id": crop.farmer_id,
        "crop_name": crop.crop_name,
        "category": crop.category,
        "quantity_available": crop.quantity_available,
        "unit": crop.unit or "KG",
        "farmer_price": crop.farmer_price,
        "ai_suggested_price": crop.ai_suggested_price or crop.farmer_price,
        "description": crop.description or "Fresh farm harvest.",
        "crop_image": img_src,
        "quality_grade": crop.quality_grade or "A",
        "freshness_score": crop.freshness_score or 90.0,
        "demand_score": crop.demand_score or 80.0,
        "demand_level": crop.demand_level or "Medium",
        "market_suitability": crop.market_suitability or "Good",
        "location": crop.location or "Madhya Pradesh",
        "status": crop.status,
        "farmer_name": farmer_name,
        "farmer_phone": farmer_phone,
        "farmer_address": farmer_address,
        "trust_score": round(trust_score, 1),
        "profit_status": profit_status,
        "profit_class": profit_class
    }

@router.get("/", response_class=HTMLResponse)
async def home_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    raw_crops = db.query(Crop).filter(Crop.status == "available").limit(6).all()
    formatted_crops = [format_crop_for_template(c) for c in raw_crops]

    # Calculate live figures for home counter bar - updates automatically upon registration
    active_farmers_count = db.query(User).filter(User.role == "farmer", User.status == "Active").count()
    active_consumers_count = db.query(User).filter(User.role == "consumer", User.status == "Active").count()
    total_crops = db.query(Crop).filter(Crop.status == "available").count()
    orders_count = db.query(Order).count()
    delivered_count = db.query(Order).filter(Order.status == "Delivered").count()
    satisfaction = 100 if orders_count == 0 else round((delivered_count / orders_count) * 100)

    session_data = {
        "user_id": current_user.id if current_user else None,
        "role": current_user.role if current_user else None,
        "user_name": current_user.full_name if current_user else None,
        "name": current_user.full_name if current_user else None
    }

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "crops": formatted_crops,
            "farmers_count": active_farmers_count,
            "consumers_count": active_consumers_count,
            "orders_count": orders_count,
            "satisfaction": satisfaction,
            "total_farmers": active_farmers_count,
            "total_crops": total_crops,
            "total_orders": orders_count,
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.get("/marketplace", response_class=HTMLResponse)
async def marketplace_page(
    request: Request,
    category: Optional[str] = "all",
    grade: Optional[str] = "all",
    trust: Optional[str] = "all",
    search: Optional[str] = "",
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    # Require login to access inside marketplace
    if not current_user:
        return RedirectResponse(
            url="/login?next=/marketplace&alert=Please+log+in+first+to+access+the+marketplace+and+browse+live+farm+produce!",
            status_code=302
        )

    raw_crops = CropService.get_all_crops(
        db=db,
        category=category,
        search=search,
        grade=grade,
        min_price=min_price,
        max_price=max_price
    )
    formatted = [format_crop_for_template(c) for c in raw_crops]

    # Filter trust score if selected
    if trust and trust != "all":
        try:
            min_trust_val = float(trust)
            if min_trust_val > 5:
                min_trust_val = min_trust_val / 20.0
            formatted = [c for c in formatted if c["trust_score"] >= min_trust_val]
        except ValueError:
            pass

    session_data = {
        "user_id": current_user.id if current_user else None,
        "role": current_user.role if current_user else None,
        "user_name": current_user.full_name if current_user else None,
        "name": current_user.full_name if current_user else None
    }

    return templates.TemplateResponse(
        "consumer/marketplace.html",
        {
            "request": request,
            "crops": formatted,
            "categories": CATEGORIES,
            "grades": ["A+", "A", "B", "C"],
            "selected_category": category or "all",
            "selected_grade": grade or "all",
            "selected_trust": trust or "all",
            "search_query": search or "",
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.get("/product/{crop_id}", response_class=HTMLResponse)
@router.get("/crops/{crop_id}", response_class=HTMLResponse)
async def product_details_page(
    crop_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    # Require login to view detailed crop page
    if not current_user:
        return RedirectResponse(
            url=f"/login?next=/product/{crop_id}&alert=Please+log+in+first+to+view+product+details+and+order!",
            status_code=302
        )

    crop_obj = CropService.get_crop_by_id(db, crop_id)
    if not crop_obj:
        raise HTTPException(status_code=404, detail="Crop product not found")

    crop_dict = format_crop_for_template(crop_obj)

    # Fetch reviews for this crop
    reviews = db.query(Review).filter(Review.crop_id == crop_id).all()

    # Price comparison analytics
    price_stats = InsightsService.get_price_analytics_for_crop(db, crop_obj.crop_name)

    session_data = {
        "user_id": current_user.id if current_user else None,
        "role": current_user.role if current_user else None,
        "user_name": current_user.full_name if current_user else None,
        "name": current_user.full_name if current_user else None
    }

    return templates.TemplateResponse(
        "consumer/product_details.html",
        {
            "request": request,
            "crop": crop_dict,
            "reviews": reviews,
            "price_stats": price_stats,
            "ai_enabled": True,
            "session": session_data,
            "ai_status": "connected"
        }
    )

@router.get("/farmers", response_class=HTMLResponse)
async def farmers_directory_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    # Require login to view farmers directory
    if not current_user:
        return RedirectResponse(
            url="/login?next=/farmers&alert=Please+log+in+first+to+access+the+farmers+directory!",
            status_code=302
        )

    farmers = db.query(User).filter(User.role == "farmer", User.status == "Active").all()
    farmer_list = []
    for idx, f in enumerate(farmers, 1):
        prof = f.farmer_profile
        farmer_crops = db.query(Crop).filter(Crop.farmer_id == f.id, Crop.status == "available").all()
        farmer_list.append({
            "id": f.id,
            "farmer_id": f.id,
            "farmer_name": f.full_name,
            "farmer_phone": f.phone or "N/A",
            "farmer_address": f.address or "Madhya Pradesh, India",
            "trust_score": int(prof.trust_score * 20) if prof else 95,
            "ranking": prof.ranking if (prof and prof.ranking) else idx,
            "total_orders": prof.total_orders if prof else 0,
            "total_sales": prof.total_sales if prof else 0.0,
            "active_crops_count": len(farmer_crops),
            "crops": farmer_crops
        })

    session_data = {
        "user_id": current_user.id if current_user else None,
        "role": current_user.role if current_user else None,
        "user_name": current_user.full_name if current_user else None,
        "name": current_user.full_name if current_user else None
    }

    return templates.TemplateResponse(
        "consumer/farmers_directory.html",
        {
            "request": request,
            "farmers": farmer_list,
            "session": session_data,
            "ai_status": "connected"
        }
    )
