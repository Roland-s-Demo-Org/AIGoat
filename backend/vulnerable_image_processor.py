import boto3
from PIL import Image
from io import BytesIO
import logging

# Configure logger
logger = logging.getLogger(__name__)

def process_image(image_data):
    """
    Process image data safely without executing any metadata.
    
    Args:
        image_data: Raw image bytes
        
    Returns:
        None
    """
    logger.info("Processing image...")
    
    # Validate image data
    if not image_data or len(image_data) == 0:
        raise ValueError("Empty image data provided")
    
    # Open and validate image
    try:
        img = Image.open(BytesIO(image_data))
        # Verify it's a valid image by checking format
        if img.format not in ['JPEG', 'PNG', 'JPG']:
            raise ValueError(f"Unsupported image format: {img.format}")
    except Exception as e:
        logger.error(f"Failed to open image: {e}")
        raise ValueError(f"Invalid image data: {e}")
    
    # Extract metadata for logging purposes only - never execute it
    metadata = img.info.get('comment', '')
    if isinstance(metadata, bytes):
        metadata = metadata.decode('utf-8', errors='ignore')
    if metadata:
        # Log metadata for informational purposes only
        # Sanitize for logging to prevent log injection
        safe_metadata = metadata.replace('\n', '\\n').replace('\r', '\\r')[:100]
        logger.info(f"Image metadata comment: {safe_metadata}")
    
    # Resize image
    img = img.resize((224, 224))
    img_data = img.tobytes()
    return None

def create_s3_file(content, bucket, key):
    s3 = boto3.client('s3')
    s3.put_object(Bucket=bucket, Key=key, Body=content)

