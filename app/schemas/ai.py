from pydantic import BaseModel
from typing import Optional, Dict, Any, List

class CropAnalysisResult(BaseModel):
    quality_grade: str
    freshness_score: float
    uniformity: float
    defect_percentage: float
    ai_suggested_price: float
    market_suitability: str
    confidence_score: float
    reasoning: str
    metrics: Dict[str, Any]
    data_sources: List[str]
