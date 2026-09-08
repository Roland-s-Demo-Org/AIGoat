import boto3
from PIL import Image
from io import BytesIO

def process_image(image_data):
    """
    Process and validate uploaded image data.
    
    This function opens the image, validates it can be processed,
    and resizes it to the required dimensions. Image metadata is
    logged for debugging purposes only and is never executed.
    
    Args:
        image_data: Raw image bytes
        
    Returns:
        None - Image is validated and processed in-place
    """
    print("Processing image...")
    img = Image.open(BytesIO(image_data))
    
    # Extract metadata for logging purposes only - never execute it
    metadata = img.info.get('comment', '')
    if isinstance(metadata, bytes):
        metadata = metadata.decode('utf-8', errors='ignore')
    
    # Log metadata for debugging (sanitized for log injection)
    if metadata:
        # Sanitize metadata to prevent log injection
        sanitized_metadata = metadata.replace('\n', ' ').replace('\r', ' ')[:100]
        print(f"Image metadata (comment): {sanitized_metadata}")
    
    # Resize image for processing
    img = img.resize((224, 224))
    img_data = img.tobytes()
    return

def create_s3_file(content, bucket, key):
    s3 = boto3.client('s3')
    s3.put_object(Bucket=bucket, Key=key, Body=content)

