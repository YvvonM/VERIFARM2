"""
OCR configuration: patterns, conversions, thresholds.
No logic — just data.
"""

# Unit conversion
ACRE_TO_HECTARE = 0.404686

# NDVI threshold (reused from satellite module)
NDVI_VEGETATION_THRESHOLD = 0.3

# OCR confidence dampening
OCR_NOISE_PENALTY = 0.90

# Regex patterns for paper register fields
HECTARE_PATTERNS = [
    r'(\d+\.?\d*)\s*ha',
    r'(\d+\.?\d*)\s*hectares?',
    r'(\d+\.?\d*)\s*acres?',
]

CROP_KEYWORDS = [
    'maize', 'cassava', 'rice', 'beans', 'sorghum',
    'millet', 'wheat', 'potato', 'yam', 'cowpea',
    'tea', 'coffee', 'sugarcane',
]

NAME_PATTERNS = [
    r'(?:name|farmer)[\s:]*([A-Za-z\s]+)',
    r'(?:member|farmer\s*name)[\s:]*([A-Za-z\s]+)',
]

DATE_PATTERNS = [
    r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    r'(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})',
]