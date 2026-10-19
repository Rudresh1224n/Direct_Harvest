import os
import re
import json
import logging
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Optional

logger = logging.getLogger("places_service")

# Curated street-level & locality database for instant offline/zero-latency suggestions
LOCAL_PLACES_DATABASE: List[Dict[str, str]] = [
    # --- INDORE ---
    {"street": "AB Road", "area": "Vijay Nagar", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452010"},
    {"street": "Scheme No 54", "area": "Vijay Nagar", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452010"},
    {"street": "Scheme No 78", "area": "Vijay Nagar", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452010"},
    {"street": "Scheme No 74", "area": "Vijay Nagar", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452010"},
    {"street": "Scheme No 114", "area": "Nipania", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452010"},
    {"street": "Scheme No 140", "area": "Pipliyahana", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452016"},
    {"street": "MG Road", "area": "New Palasia", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452001"},
    {"street": "Janki Nagar", "area": "Navlakha", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452001"},
    {"street": "Old Palasia", "area": "Palasia", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452018"},
    {"street": "Saket Nagar", "area": "Old Palasia", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452018"},
    {"street": "Bhanwarkuan Main Road", "area": "Bhanwarkuan", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452001"},
    {"street": "Vishnupuri Colony", "area": "Bhanwarkuan", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452001"},
    {"street": "Indrapuri Colony", "area": "Bhanwarkuan", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452001"},
    {"street": "Sapna Sangeeta Road", "area": "Snehnagar", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452001"},
    {"street": "Annapurna Road", "area": "Usha Nagar", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452009"},
    {"street": "Sudama Nagar", "area": "Annapurna", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452009"},
    {"street": "Ranjeet Hanuman Road", "area": "Dravid Nagar", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452009"},
    {"street": "Rajwada Chowk", "area": "Khajuri Bazar", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452002"},
    {"street": "Sarafa Bazar", "area": "Rajwada", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452002"},
    {"street": "Mahalaxmi Nagar", "area": "Near Bombay Hospital", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452010"},
    {"street": "Nipania Main Road", "area": "Nipania", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452010"},
    {"street": "Bypass Road", "area": "Bicholi Mardana", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452016"},
    {"street": "Kanadia Road", "area": "Vaibhav Nagar", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452016"},
    {"street": "Tilak Nagar Main Road", "area": "Tilak Nagar", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452018"},
    {"street": "Manorama Ganj", "area": "Geeta Bhawan", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452001"},
    {"street": "South Tukoganj", "area": "Chhavani", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452001"},
    {"street": "Race Course Road", "area": "Tukoganj", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452001"},
    {"street": "Khandwa Road", "area": "Limbodi", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452020"},
    {"street": "Rau Bypass", "area": "Rau", "city": "Indore", "state": "Madhya Pradesh", "pincode": "453331"},
    {"street": "Silicon City Main Road", "area": "Rau", "city": "Indore", "state": "Madhya Pradesh", "pincode": "453331"},
    {"street": "Super Corridor Road", "area": "Gandhi Nagar", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452005"},
    {"street": "Banganga Main Road", "area": "Banganga", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452015"},
    {"street": "Nyay Nagar", "area": "Sukhliya", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452010"},
    {"street": "Marimata Square", "area": "Kila Maidan", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452006"},
    {"street": "Airport Road", "area": "Kalani Nagar", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452005"},
    {"street": "Khajrana Main Road", "area": "Khajrana", "city": "Indore", "state": "Madhya Pradesh", "pincode": "452016"},

    # --- BHOPAL ---
    {"street": "MP Nagar Zone 1", "area": "MP Nagar", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462011"},
    {"street": "MP Nagar Zone 2", "area": "MP Nagar", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462011"},
    {"street": "Arera Colony E1", "area": "Arera Colony", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462016"},
    {"street": "Arera Colony E7", "area": "Arera Colony", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462016"},
    {"street": "Kolar Road", "area": "Chuna Bhatti", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462016"},
    {"street": "Kolar Main Road", "area": "Sarvadharma Colony", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462042"},
    {"street": "Hoshangabad Road", "area": "Misrod", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462026"},
    {"street": "Bawadiya Kalan Main Road", "area": "Bawadiya Kalan", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462026"},
    {"street": "Shahpura Sector A", "area": "Shahpura", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462039"},
    {"street": "Gulmohar Colony", "area": "Trilanga", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462039"},
    {"street": "Bittan Market Road", "area": "Arera Colony", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462016"},
    {"street": "New Market", "area": "TT Nagar", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462003"},
    {"street": "Malviya Nagar", "area": "Roshanpura", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462003"},
    {"street": "Ayodhya Bypass Road", "area": "Ayodhya Nagar", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462041"},
    {"street": "Indrapuri Sector C", "area": "BHEL", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462021"},
    {"street": "Sonagiri", "area": "Piplani", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462022"},
    {"street": "Sant Hirdaram Nagar (Bairagarh)", "area": "Bairagarh", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462030"},
    {"street": "Jahangirabad Main Road", "area": "Jahangirabad", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462008"},
    {"street": "Shyamla Hills Road", "area": "Shyamla Hills", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462013"},
    {"street": "Govindpura Industrial Area", "area": "Govindpura", "city": "Bhopal", "state": "Madhya Pradesh", "pincode": "462023"},

    # --- UJJAIN ---
    {"street": "Freeganj Main Road", "area": "Freeganj", "city": "Ujjain", "state": "Madhya Pradesh", "pincode": "456010"},
    {"street": "Madhav Nagar", "area": "Freeganj", "city": "Ujjain", "state": "Madhya Pradesh", "pincode": "456010"},
    {"street": "Nanakheda Ring Road", "area": "Nanakheda", "city": "Ujjain", "state": "Madhya Pradesh", "pincode": "456010"},
    {"street": "Mahakal Marg", "area": "Jaisinghpura", "city": "Ujjain", "state": "Madhya Pradesh", "pincode": "456006"},
    {"street": "Dewas Road", "area": "Sethi Nagar", "city": "Ujjain", "state": "Madhya Pradesh", "pincode": "456010"},
    {"street": "Agar Road", "area": "Chiman Ganj Mandi", "city": "Ujjain", "state": "Madhya Pradesh", "pincode": "456006"},
    {"street": "Indore Road", "area": "Rishi Nagar", "city": "Ujjain", "state": "Madhya Pradesh", "pincode": "456010"},

    # --- JABALPUR ---
    {"street": "Civil Lines", "area": "Sadar", "city": "Jabalpur", "state": "Madhya Pradesh", "pincode": "482001"},
    {"street": "Madan Mahal Station Road", "area": "Madan Mahal", "city": "Jabalpur", "state": "Madhya Pradesh", "pincode": "482002"},
    {"street": "Wright Town Main Road", "area": "Wright Town", "city": "Jabalpur", "state": "Madhya Pradesh", "pincode": "482002"},
    {"street": "Napier Town", "area": "Russel Chowk", "city": "Jabalpur", "state": "Madhya Pradesh", "pincode": "482001"},
    {"street": "Vijay Nagar", "area": "Kachnar City", "city": "Jabalpur", "state": "Madhya Pradesh", "pincode": "482002"},
    {"street": "Gorakhpur Main Road", "area": "Gorakhpur", "city": "Jabalpur", "state": "Madhya Pradesh", "pincode": "482001"},
    {"street": "Adhartal Road", "area": "Adhartal", "city": "Jabalpur", "state": "Madhya Pradesh", "pincode": "482004"},

    # --- GWALIOR ---
    {"street": "City Center", "area": "Patel Nagar", "city": "Gwalior", "state": "Madhya Pradesh", "pincode": "474011"},
    {"street": "Lashkar Main Market", "area": "Lashkar", "city": "Gwalior", "state": "Madhya Pradesh", "pincode": "474001"},
    {"street": "Morar Bazaar", "area": "Morar", "city": "Gwalior", "state": "Madhya Pradesh", "pincode": "474006"},
    {"street": "Thatipur Main Road", "area": "Thatipur", "city": "Gwalior", "state": "Madhya Pradesh", "pincode": "474011"},
    {"street": "Phoolbagh Road", "area": "Padav", "city": "Gwalior", "state": "Madhya Pradesh", "pincode": "474002"},

    # --- OTHER MP CITIES ---
    {"street": "Station Road", "area": "Civil Lines", "city": "Dewas", "state": "Madhya Pradesh", "pincode": "455001"},
    {"street": "AB Road", "area": "Bhopal Chauraha", "city": "Dewas", "state": "Madhya Pradesh", "pincode": "455001"},
    {"street": "Civil Lines", "area": "Gopal Ganj", "city": "Sagar", "state": "Madhya Pradesh", "pincode": "470001"},
    {"street": "Rewa Road", "area": "Bharhut Nagar", "city": "Satna", "state": "Madhya Pradesh", "pincode": "485001"},
    {"street": "Civil Lines", "area": "College Road", "city": "Rewa", "state": "Madhya Pradesh", "pincode": "486001"},
    {"street": "Do Batti Road", "area": "Station Road", "city": "Ratlam", "state": "Madhya Pradesh", "pincode": "457001"},
    {"street": "Bada Bazaar", "area": "Old Town", "city": "Khandwa", "state": "Madhya Pradesh", "pincode": "450001"},
    {"street": "Navgraha Mandir Road", "area": "Bistan Road", "city": "Khargone", "state": "Madhya Pradesh", "pincode": "451001"},
    {"street": "Mhow-Neemuch Road", "area": "Khanpura", "city": "Mandsaur", "state": "Madhya Pradesh", "pincode": "458001"},
    {"street": "Tagore Marg", "area": "Vikas Nagar", "city": "Neemuch", "state": "Madhya Pradesh", "pincode": "458441"},
    {"street": "Bhopal Vidisha Highway", "area": "Durga Nagar", "city": "Vidisha", "state": "Madhya Pradesh", "pincode": "464001"},
    {"street": "Chhatrapati Shivaji Marg", "area": "Main Road", "city": "Malkapur", "state": "Maharashtra", "pincode": "443101"},
    {"street": "FC Road", "area": "Shivajinagar", "city": "Pune", "state": "Maharashtra", "pincode": "411005"},
    {"street": "Linking Road", "area": "Bandra West", "city": "Mumbai", "state": "Maharashtra", "pincode": "400050"},
    {"street": "Connaught Place", "area": "Central Delhi", "city": "New Delhi", "state": "Delhi", "pincode": "110001"},
    {"street": "MG Road", "area": "Indiranagar", "city": "Bengaluru", "state": "Karnataka", "pincode": "560038"},
]


class PlacesService:
    @classmethod
    def get_google_maps_api_key(cls) -> str:
        return os.getenv("GOOGLE_MAPS_API_KEY", "").strip()

    @classmethod
    def autocomplete_google(cls, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        """Query Google Places Autocomplete API when key is configured."""
        api_key = cls.get_google_maps_api_key()
        if not api_key:
            return []

        try:
            params = {
                "input": query,
                "key": api_key,
                "components": "country:in",
                "types": "geocode",
            }
            url = f"https://maps.googleapis.com/maps/api/place/autocomplete/json?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(url, headers={"User-Agent": "DirectHarvestAI/2.0"})
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            results = []
            for pred in data.get("predictions", [])[:limit]:
                main_text = pred.get("structured_formatting", {}).get("main_text", "")
                secondary_text = pred.get("structured_formatting", {}).get("secondary_text", "")
                description = pred.get("description", "")
                
                # Parse components if possible
                terms = [t.get("value", "") for t in pred.get("terms", [])]
                city = terms[-3] if len(terms) >= 3 else (terms[-2] if len(terms) >= 2 else "Indore")
                state = terms[-2] if len(terms) >= 2 else "Madhya Pradesh"
                
                results.append({
                    "street": main_text or description,
                    "area": secondary_text or main_text,
                    "city": city,
                    "state": state,
                    "pincode": "",
                    "formatted": description,
                    "source": "google_maps"
                })
            return results
        except Exception as e:
            logger.debug("Google Places Autocomplete exception: %s", e)
            return []

    @classmethod
    def autocomplete_photon_osm(cls, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        """Query Photon (OpenStreetMap geocoding based on OSM data) for street-level search."""
        try:
            # Center near Madhya Pradesh (22.7, 75.8) with bias
            params = {
                "q": query,
                "limit": limit,
                "lat": "22.7196",
                "lon": "75.8577",
            }
            url = f"https://photon.komoot.io/api/?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(url, headers={"User-Agent": "DirectHarvestAI/2.0 (contact: info@directharvest.in)"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            results = []
            for feature in data.get("features", []):
                props = feature.get("properties", {})
                country = props.get("country", "").lower()
                # Focus on Indian locations
                if country and country not in ("india", "in"):
                    continue

                name = props.get("name") or props.get("street") or props.get("locality") or ""
                street = props.get("street") or name
                city = props.get("city") or props.get("district") or props.get("county") or "Indore"
                state = props.get("state") or "Madhya Pradesh"
                postcode = props.get("postcode") or ""
                district = props.get("district") or props.get("city") or ""

                parts = [p for p in [name, street if street != name else None, district if district != city else None, city, state, postcode] if p]
                formatted = ", ".join(parts)

                results.append({
                    "street": name or street,
                    "area": street if street != name else district or city,
                    "city": city,
                    "state": state,
                    "pincode": postcode,
                    "formatted": formatted,
                    "source": "osm_photon"
                })
            return results
        except Exception as e:
            logger.debug("Photon OSM autocomplete exception: %s", e)
            return []

    @classmethod
    def autocomplete_local(cls, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        """Instant zero-latency matching against curated local streets and localities."""
        q_clean = query.strip().lower()
        if not q_clean:
            return []

        tokens = q_clean.split()
        matches = []
        for p in LOCAL_PLACES_DATABASE:
            searchable = f"{p['street']} {p['area']} {p['city']} {p['state']} {p['pincode']}".lower()
            # Check if all tokens match
            if all(token in searchable for token in tokens):
                formatted = f"{p['street']}, {p['area']}, {p['city']}, {p['state']} - {p['pincode']}"
                matches.append({
                    "street": p["street"],
                    "area": p["area"],
                    "city": p["city"],
                    "state": p["state"],
                    "pincode": p["pincode"],
                    "formatted": formatted,
                    "source": "verified_database"
                })
                if len(matches) >= limit:
                    break
        return matches

    @classmethod
    def search_places(cls, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        """
        Multi-tier autocomplete search:
        1. Google Places Autocomplete (if key active)
        2. OpenStreetMap Photon Geocoding
        3. Local Curated Database fallback
        Combines and deduplicates results seamlessly.
        """
        q = (query or "").strip()
        if len(q) < 2:
            return []

        # 1. Try Google Places if key exists
        google_results = cls.autocomplete_google(q, limit=limit)
        if google_results:
            return google_results

        # 2. Query Local verified places
        local_results = cls.autocomplete_local(q, limit=limit)

        # 3. If local results fewer than 4, enrich with live Photon OSM
        if len(local_results) < 4:
            osm_results = cls.autocomplete_photon_osm(q, limit=limit)
            seen_formatted = {r["formatted"].lower() for r in local_results}
            for o in osm_results:
                if o["formatted"].lower() not in seen_formatted:
                    local_results.append(o)
                    seen_formatted.add(o["formatted"].lower())
                if len(local_results) >= limit:
                    break

        return local_results[:limit]
