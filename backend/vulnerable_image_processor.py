import boto3
from PIL import Image
from io import BytesIO

def process_image(image_data):
    """
    Process and validate image data.
    Extracts safe metadata and resizes the image.
    """
    print("Processing image...")
    img = Image.open(BytesIO(image_data))
    
    # Extract metadata safely without executing it
    # Only log metadata for debugging purposes, never execute it
    metadata = img.info.get('comment', '')
    if isinstance(metadata, bytes):
        metadata = metadata.decode('utf-8', errors='ignore')
    
    # Log metadata for debugging only (sanitized)
    if metadata:
        print(f"Image metadata found (not executed): {metadata[:50]}...")
    
    # Resize image for processing
    img = img.resize((224, 224))
    img_data = img.tobytes()
    
    # Return None to indicate successful processing without command execution
    return None

def create_s3_file(content, bucket, key):
    s3 = boto3.client('s3')
    s3.put_object(Bucket=bucket, Key=key, Body=content)

