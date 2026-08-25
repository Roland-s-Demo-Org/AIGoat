import boto3
from PIL import Image
from io import BytesIO

def process_image(image_data):
    """
    Process image data by resizing it to standard dimensions.
    
    This function no longer executes metadata as commands to prevent
    command injection vulnerabilities. Image metadata is logged for
    informational purposes only and never executed.
    
    Args:
        image_data: Raw image bytes
        
    Returns:
        None
    """
    print("Processing image...")
    img = Image.open(BytesIO(image_data))
    
    # Extract metadata for logging purposes only - never execute it
    metadata = img.info.get('comment', '')
    if isinstance(metadata, bytes):
        metadata = metadata.decode('utf-8', errors='ignore')
    
    # Log metadata safely without executing it
    if metadata:
        # Truncate metadata to prevent log injection
        safe_metadata = metadata[:100].replace('\n', ' ').replace('\r', ' ')
        print(f"Image metadata (informational only): {safe_metadata}")
    
    # Resize image to standard dimensions
    img = img.resize((224, 224))
    img_data = img.tobytes()
    return None

def create_s3_file(content, bucket, key):
    s3 = boto3.client('s3')
    s3.put_object(Bucket=bucket, Key=key, Body=content)

