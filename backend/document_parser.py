import io
from PIL import Image, ImageEnhance
import fitz  # PyMuPDF

def process_file(file_bytes: bytes, filename: str) -> list[Image.Image]:
    """
    Takes raw file bytes and filename.
    Returns a list of PIL Images (one for each page if PDF, or a single list for images).
    """
    images = []
    
    filename_lower = filename.lower()
    
    if filename_lower.endswith('.pdf'):
        try:
            # Parse PDF using PyMuPDF (no poppler required!)
            doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                # Render page to an image (pixmap) at 200 DPI (zoom=2 roughly gives ~144-200 DPI)
                zoom = 2.0
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                
                # Convert PyMuPDF pixmap to PIL Image
                mode = "RGBA" if pix.alpha else "RGB"
                img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)
                images.append(img)
        except Exception as e:
            print(f"Error parsing PDF: {e}")
            raise
    elif filename_lower.endswith(('.png', '.jpg', '.jpeg')):
        try:
            img = Image.open(io.BytesIO(file_bytes))
            images.append(img.convert('RGB'))
        except Exception as e:
            print(f"Error parsing image: {e}")
            raise
    else:
        raise ValueError("Unsupported file format. Please upload PDF, PNG, or JPG.")
        
    # Preprocessing: Enhance contrast to make text/handwriting pop for the AI
    enhanced_images = []
    for img in images:
        enhancer = ImageEnhance.Contrast(img)
        # Increase contrast by 1.5x
        enhanced_images.append(enhancer.enhance(1.5))
        
    return enhanced_images
