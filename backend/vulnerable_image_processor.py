import boto3
from PIL import Image
from io import BytesIO

def process_image(image_data):
    print("Processing image...")
    img = Image.open(BytesIO(image_data))
    # Image metadata (e.g. the 'comment' field) is untrusted input and must
    # never be interpreted as a command; it is deliberately ignored here.
    img = img.resize((224, 224))
    img_data = img.tobytes()
    return

def create_s3_file(content, bucket, key):
    s3 = boto3.client('s3')
    s3.put_object(Bucket=bucket, Key=key, Body=content)

