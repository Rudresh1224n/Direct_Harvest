import os
import cv2
import numpy as np
import pytest
from app.services.ai_service import AIService


def test_fresh_crop_image_analysis(tmp_path):
    # Create a synthetic fresh crop image (vibrant green, high brightness, uniform)
    img_path = str(tmp_path / "fresh_crop.jpg")
    img = np.zeros((300, 300, 3), dtype=np.uint8)
    # Fill with healthy green color in BGR: B=40, G=190, R=50
    img[:] = (40, 190, 50)
    cv2.imwrite(img_path, img)

    result = AIService.analyze_crop_image(img_path, crop_name="spinach", farmer_price=20.0)

    assert result["quality_grade"] in ("A+", "A")
    assert result["freshness_score"] >= 80.0
    assert result["defect_percentage"] < 5.0
    assert result["ai_suggested_price"] > 0.0
    assert "avg_hue" in result["metrics"]
    assert "avg_saturation" in result["metrics"]


def test_blemished_crop_image_analysis(tmp_path):
    # Create a synthetic blemished crop image with dark rotten patches
    img_path = str(tmp_path / "blemished_crop.jpg")
    img = np.zeros((300, 300, 3), dtype=np.uint8)
    img[:] = (50, 160, 50)
    # Add large black spots/bruises (values near 0)
    img[50:180, 50:180] = (10, 10, 10)
    img[200:270, 180:250] = (5, 5, 5)
    cv2.imwrite(img_path, img)

    result = AIService.analyze_crop_image(img_path, crop_name="tomato", farmer_price=25.0)

    # Defect percentage should be elevated
    assert result["defect_percentage"] > 10.0
    # Quality grade should reflect blemishes (B or C)
    assert result["quality_grade"] in ("B", "C")
    assert result["ai_suggested_price"] > 0.0


def test_missing_image_graceful_fallback():
    # Calling with nonexistent image should return valid fallback structure without crashing
    result = AIService.analyze_crop_image("non_existent_image_path.jpg", crop_name="wheat", farmer_price=24.0)

    assert "quality_grade" in result
    assert "freshness_score" in result
    assert "ai_suggested_price" in result
    assert result["confidence_score"] == 80.0
    assert "DirectHarvest Heuristic Pricing Engine" in result["data_sources"]
