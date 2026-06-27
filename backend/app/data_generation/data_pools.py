"""
Static data pools used by the fake farmer generator: names, locations,
crop types, and organizations per country. Kept separate from the
generation logic so the actual generator script stays readable, and so
these lists can be extended (more names, more regions) without touching
generation logic at all.

Coordinates are approximate centers of real regions named in the project
proposal (Oyo State, Nigeria; Kirinyaga County, Kenya), with small random
jitter applied per-farmer at generation time -- see generate_dataset.py.
"""

NIGERIA_FARMER_NAMES: list[str] = [
    "Chinedu Okafor", "Ngozi Eze", "Tunde Adeyemi", "Folake Bello",
    "Emeka Nwosu", "Aisha Bello", "Ibrahim Sani", "Chidinma Okeke",
    "Adebayo Ogunleye", "Halima Yusuf", "Obinna Chukwu", "Bukola Adesanya",
    "Yakubu Garba", "Funmilayo Oladipo", "Uche Eze",
]

KENYA_FARMER_NAMES: list[str] = [
    "Mary Wanjiru", "James Kamau", "Grace Achieng", "Peter Kiprotich",
    "Faith Njeri", "Daniel Otieno", "Esther Wambui", "Samuel Mwangi",
    "Joyce Chebet", "Francis Odhiambo", "Catherine Wairimu", "John Kiplagat",
    "Agnes Auma", "David Maina", "Lucy Nyambura",
]

NIGERIA_REGION_CENTER = {"location": "Oyo State", "lat": 8.1574, "lon": 3.6147}
KENYA_REGION_CENTER = {"location": "Kirinyaga County", "lat": -0.6590, "lon": 37.3050}

NIGERIA_CROPS: list[str] = ["cassava", "rice", "maize"]
KENYA_CROPS: list[str] = ["maize", "beans", "tea"]

NIGERIA_SOIL_TYPES: list[str] = ["sandy loam", "clay loam", "loam"]
KENYA_SOIL_TYPES: list[str] = ["volcanic loam", "clay", "loam"]

# Organizations -- a small fixed set per country, matching the proposal's
# named partners (Agrovesto, Tegemeo Cereals Enterprises) plus enough
# variety to populate off_taker / cooperative / lender / mobile_money_provider
# roles distinctly.
NIGERIA_ORGANIZATIONS: list[dict] = [
    {"id": "org_ng_agrovesto", "name": "Agrovesto", "type": "Agrovesto",
     "org_role": "off_taker", "reputation_score": 0.81},
    {"id": "org_ng_coop_oyo", "name": "Oyo Farmers Cooperative", "type": "Cooperative",
     "org_role": "cooperative", "reputation_score": 0.68},
    {"id": "org_ng_lender_mfb", "name": "Oyo Microfinance Bank", "type": "Lender",
     "org_role": "lender", "reputation_score": 0.74},
    {"id": "org_ng_momo", "name": "PalmPay Agric", "type": "MobileMoneyProvider",
     "org_role": "mobile_money_provider", "reputation_score": 0.70},
]

KENYA_ORGANIZATIONS: list[dict] = [
    {"id": "org_ke_tegemeo", "name": "Tegemeo Cereals Enterprises", "type": "Tegemeo",
     "org_role": "off_taker", "reputation_score": 0.85},
    {"id": "org_ke_coop_kirinyaga", "name": "Kirinyaga Farmers Cooperative", "type": "Cooperative",
     "org_role": "cooperative", "reputation_score": 0.72},
    {"id": "org_ke_sacco", "name": "Kirinyaga SACCO", "type": "Lender",
     "org_role": "lender", "reputation_score": 0.77},
    {"id": "org_ke_momo", "name": "M-Pesa Agric", "type": "MobileMoneyProvider",
     "org_role": "mobile_money_provider", "reputation_score": 0.79},
]