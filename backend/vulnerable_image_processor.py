import boto3
from PIL import Image
from io import BytesIO

def process_image(image_data):
    print("Processing image...")
    img = Image.open(BytesIO(image_data))
    metadata = img.info.get('comment', '')
    if isinstance(metadata, bytes):
        metadata = metadata.decode('utf-8', errors='ignore')
    metadata = metadata.strip('"')
    if metadata:
        # Log metadata for informational purposes only - do not execute
        print(f"Image metadata comment: {metadata}")
    img = img.resize((224, 224))
    img_data = img.tobytes()
    return None

def create_s3_file(content, bucket, key):
    s3 = boto3.client('s3')
    s3.put_object(Bucket=bucket, Key=key, Body=content)

