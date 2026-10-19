from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, Any
from datetime import datetime

class CropCreate(BaseModel):
    crop_name: str = Field(..., min_length=2, max_length=100)
    category: str = Field(..., min_length=2, max_length=50)
    quantity_available: float = Field(..., ge=0)
    unit: str = Field("KG", max_length=20)
    farmer_price: float = Field(..., gt=0)
    description: Optional[str] = None
    location: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def populate_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "price" in data and "farmer_price" not in data:
                data["farmer_price"] = data["price"]
            if "quantity" in data and "quantity_available" not in data:
                data["quantity_available"] = data["quantity"]
        return data

class CropUpdate(BaseModel):
    crop_name: Optional[str] = None
    category: Optional[str] = None
    quantity_available: Optional[float] = Field(None, ge=0)
    unit: Optional[str] = None
    farmer_price: Optional[float] = Field(None, gt=0)
    description: Optional[str] = None
    location: Optional[str] = None
    status: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def populate_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "price" in data and "farmer_price" not in data:
                data["farmer_price"] = data["price"]
            if "quantity" in data and "quantity_available" not in data:
                data["quantity_available"] = data["quantity"]
        return data

class CropOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    crop_id: int
    farmer_id: int
    crop_name: str
    category: str
    quantity_available: float
    unit: str
    farmer_price: float
    ai_suggested_price: Optional[float] = None
    description: Optional[str] = None
    crop_image: Optional[str] = None
    quality_grade: str
    freshness_score: float
    demand_score: float
    demand_level: str
    market_suitability: str
    location: Optional[str] = None
    status: str
    created_at: datetime
