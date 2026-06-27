"""
Tesseract wrapper. Single responsibility: image → raw text.
"""

from PIL import Image
import pytesseract

from .image_processor import preprocess


def extract_text(image_path: str, preprocess_image: bool = True) -> str:
    """
    Run OCR on image file. Returns raw text string.
    """
    image = Image.open(image_path)
    
    if preprocess_image:
        image = preprocess(image)
    
    text = pytesseract.image_to_string(image)
    return text.strip()