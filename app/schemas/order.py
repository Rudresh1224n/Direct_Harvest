from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List
from datetime import datetime

class CartItemAdd(BaseModel):
    crop_id: int
    quantity: float = Field(..., gt=0)

class CartItemUpdate(BaseModel):
    quantity: float = Field(..., gt=0)

class CheckoutRequest(BaseModel):
    delivery_address: str = Field(..., min_length=5)
    payment_method: str = Field("Cash on Delivery")

class OrderStatusUpdate(BaseModel):
    status: str
    delivery_partner_id: Optional[int] = None

class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: int
    consumer_id: int
    farmer_id: int
    crop_id: int
    delivery_partner_id: Optional[int] = None
    quantity: float
    price_per_kg: float
    subtotal: float
    delivery_charge: float
    discount: float
    total_amount: float
    delivery_address: str
    payment_method: str
    payment_status: str
    status: str
    order_date: datetime
    updated_at: datetime
