"""
Image preprocessing before OCR. Optional — skip if image quality is good.
"""

from PIL import Image, ImageEnhance


def preprocess(image: Image.Image, enhance_contrast: bool = True) -> Image.Image:
    """
    Minimal preprocessing: grayscale, optional contrast boost.
    """
    img = image.convert('L')
    
    if enhance_contrast:
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)
    
    return img