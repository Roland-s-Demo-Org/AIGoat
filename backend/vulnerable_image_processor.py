import boto3
from PIL import Image
from io import BytesIO

def process_image(image_data):
    """
    Safely process image data and extract metadata without executing any commands.
    Returns structured metadata as inert data only.
    """
    print("Processing image...")
    img = Image.open(BytesIO(image_data))
    
    # Extract metadata safely without execution
    metadata = {}
    
    # Get basic image properties
    metadata['format'] = img.format
    metadata['mode'] = img.mode
    metadata['size'] = img.size
    
    # Extract comment field as inert data (never execute it)
    comment = img.info.get('comment', '')
    if isinstance(comment, bytes):
        comment = comment.decode('utf-8', errors='ignore')
    
    # Store comment as data only - treat as untrusted user input
    metadata['comment'] = comment
    
    # Extract other safe metadata fields
    for key in ['dpi', 'exif', 'icc_profile']:
        if key in img.info:
            value = img.info[key]
            # Convert bytes to string representation for JSON serialization
            if isinstance(value, bytes):
                metadata[key] = f"<binary data, {len(value)} bytes>"
            else:
                metadata[key] = str(value)
    
    # Resize image for processing
    img = img.resize((224, 224))
    img_data = img.tobytes()
    
    return metadata

def create_s3_file(content, bucket, key):
    s3 = boto3.client('s3')
    s3.put_object(Bucket=bucket, Key=key, Body=content)

