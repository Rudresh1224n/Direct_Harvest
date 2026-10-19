import math
import logging
from typing import Tuple, Dict, Any, List

logger = logging.getLogger("geocoding_service")

# Standard geographical coordinates for major cities and districts
KNOWN_COORDINATES: Dict[str, Tuple[float, float]] = {
    "indore": (22.7196, 75.8577),
    "bhopal": (23.2599, 77.4126),
    "ujjain": (23.1760, 75.7885),
    "dewas": (22.9623, 76.0508),
    "jabalpur": (23.1686, 79.9339),
    "gwalior": (26.2183, 78.1828),
    "sagar": (23.8388, 78.7378),
    "satna": (24.5772, 80.8252),
    "rewa": (24.5349, 81.2996),
    "ratlam": (23.3315, 75.0367),
    "mandsaur": (24.0722, 75.0683),
    "neemuch": (24.4756, 74.8705),
    "khargone": (21.8232, 75.6186),
    "khandwa": (21.8314, 76.3498),
    "dhar": (22.5987, 75.2974),
    "hoshangabad": (22.7519, 77.7289),
    "narmadapuram": (22.7519, 77.7289),
    "sehore": (23.2032, 77.0844),
    "vidisha": (23.5251, 77.8081),
    "malkapur": (20.8841, 76.2023),
    "pune": (18.5204, 73.8567),
    "mumbai": (19.0760, 72.8777),
    "ratnagiri": (16.9902, 73.3120),
    "delhi": (28.6139, 77.2090),
    "bengaluru": (12.9716, 77.5946),
}

DEFAULT_COORDS = (22.7196, 75.8577)  # Indore baseline center


class GeocodingService:
    @staticmethod
    def get_coordinates_for_address(address: str, fallback_offset: float = 0.0) -> Tuple[float, float]:
        """
        Extract coordinates from city/district name in address string.
        Adds subtle deterministic offset if requested to prevent overlapping pins.
        """
        if not address:
            return DEFAULT_COORDS

        addr_lower = address.lower()
        for city, coords in KNOWN_COORDINATES.items():
            if city in addr_lower:
                lat, lng = coords
                if fallback_offset != 0.0:
                    lat += fallback_offset * 0.005
                    lng += fallback_offset * 0.005
                return round(lat, 5), round(lng, 5)

        # Hash-based deterministic fallback within MP region if city name not explicitly matched
        addr_hash = abs(hash(addr_lower)) % 1000
        lat = 22.70 + (addr_hash % 50) * 0.01 + (fallback_offset * 0.003)
        lng = 75.80 + ((addr_hash // 50) % 50) * 0.01 + (fallback_offset * 0.003)
        return round(lat, 5), round(lng, 5)

    @staticmethod
    def calculate_haversine_distance_km(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
        """Calculate approximate distance in kilometers between two lat/lng pairs."""
        lat1, lon1 = coord1
        lat2, lon2 = coord2
        R = 6371.0  # Earth radius in km

        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (math.sin(dlat / 2) ** 2 +
             math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return round(R * c, 2)

    @staticmethod
    def estimate_eta_minutes(distance_km: float, speed_kmh: float = 30.0) -> int:
        """Estimate delivery ETA in minutes assuming urban two-wheeler speed."""
        if distance_km <= 0.1:
            return 1
        hours = distance_km / max(speed_kmh, 10.0)
        minutes = int(math.ceil(hours * 60))
        return max(minutes, 2)

    @staticmethod
    def interpolate_route(start: Tuple[float, float], end: Tuple[float, float], num_points: int = 15) -> List[Tuple[float, float]]:
        """Generates waypoint coordinates along a route between two points."""
        points = []
        lat1, lng1 = start
        lat2, lng2 = end
        for i in range(num_points + 1):
            ratio = i / float(num_points)
            lat = lat1 + (lat2 - lat1) * ratio
            lng = lng1 + (lng2 - lng1) * ratio
            points.append((round(lat, 5), round(lng, 5)))
        return points
