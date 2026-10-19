from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime

class ReviewCreate(BaseModel):
    order_id: int
    rating: int = Field(..., ge=1, le=5)
    review_text: Optional[str] = None

class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_id: int
    order_id: int
    farmer_id: int
    consumer_id: int
    crop_id: Optional[int] = None
    rating: int
    review_text: Optional[str] = None
    created_at: datetime
