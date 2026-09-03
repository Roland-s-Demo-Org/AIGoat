import boto3
import time
import datetime
import logging
import os
import json
import hashlib

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize clients
sm_client = boto3.client('sagemaker')
iam_client = boto3.client('iam')
dynamodb = boto3.resource('dynamodb')
s3_client = boto3.client('s3')

# Constants
ALLOWED_KEY = "product_ratings.csv"
MAX_CONCURRENT_JOBS = 1

def lambda_handler(event, context):
    """
    Lambda handler that validates S3 events before triggering retraining.
    Implements authorization, exact-key validation, and idempotency.
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        # Validate that this is an S3 event
        if 'Records' not in event:
            logger.error("Invalid event: No Records field found")
            return {
                'statusCode': 400,
                'body': json.dumps('Invalid event format')
            }
        
        # Process each S3 record
        for record in event['Records']:
            # Validate event source
            if record.get('eventSource') != 'aws:s3':
                logger.error(f"Invalid event source: {record.get('eventSource')}")
                continue
            
            # Extract bucket and key information
            bucket_name = record['s3']['bucket']['name']
            object_key = record['s3']['object']['key']
            
            logger.info(f"Processing S3 event for bucket: {bucket_name}, key: {object_key}")
            
            # Exact key validation - reject any key that is not exactly "product_ratings.csv"
            if object_key != ALLOWED_KEY:
                logger.warning(f"Rejected: Key '{object_key}' does not match allowed key '{ALLOWED_KEY}'")
                continue
            
            # Validate bucket matches expected bucket
            expected_bucket = os.environ.get('S3_BUCKET_URI')
            if bucket_name != expected_bucket:
                logger.error(f"Rejected: Bucket '{bucket_name}' does not match expected bucket '{expected_bucket}'")
                continue
            
            # Verify object exists and get metadata for additional validation
            try:
                obj_metadata = s3_client.head_object(Bucket=bucket_name, Key=object_key)
                object_size = obj_metadata['ContentLength']
                
                # Validate object size (prevent empty or suspiciously large files)
                if object_size == 0:
                    logger.error(f"Rejected: Object is empty")
                    continue
                if object_size > 100 * 1024 * 1024:  # 100 MB limit
                    logger.error(f"Rejected: Object size {object_size} exceeds maximum allowed size")
                    continue
                    
            except Exception as e:
                logger.error(f"Failed to validate object: {str(e)}")
                continue
            
            # Check for concurrent training jobs
            if check_concurrent_jobs():
                logger.warning("Rejected: Maximum concurrent training jobs already running")
                return {
                    'statusCode': 429,
                    'body': json.dumps('Maximum concurrent training jobs limit reached')
                }
            
            # Generate idempotency key based on object version and timestamp
            etag = obj_metadata.get('ETag', '').strip('"')
            request_id = f"{bucket_name}:{object_key}:{etag}"
            
            # Check idempotency
            if check_idempotency(request_id):
                logger.info(f"Skipping: Training already initiated for request_id: {request_id}")
                continue
            
            # Record this request for idempotency
            record_request(request_id)
            
            # Trigger retraining with validated parameters
            retrain_model(bucket_name, object_key)
        
        return {
            'statusCode': 200,
            'body': json.dumps('Processing completed')
        }
        
    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }

def check_idempotency(request_id):
    """
    Check if this request has already been processed.
    Returns True if already processed, False otherwise.
    """
    try:
        table_name = os.environ.get('IDEMPOTENCY_TABLE_NAME')
        table = dynamodb.Table(table_name)
        
        response = table.get_item(Key={'request_id': request_id})
        
        if 'Item' in response:
            # Check if the training job is still in progress or completed
            status = response['Item'].get('status')
            if status in ['InProgress', 'Completed']:
                return True
        
        return False
    except Exception as e:
        logger.error(f"Error checking idempotency: {str(e)}")
        # Fail open to prevent blocking legitimate requests
        return False

def record_request(request_id):
    """
    Record this request in DynamoDB for idempotency tracking.
    """
    try:
        table_name = os.environ.get('IDEMPOTENCY_TABLE_NAME')
        table = dynamodb.Table(table_name)
        
        # TTL set to 7 days from now
        ttl = int(time.time()) + (7 * 24 * 60 * 60)
        
        table.put_item(
            Item={
                'request_id': request_id,
                'status': 'InProgress',
                'timestamp': datetime.datetime.now().isoformat(),
                'ttl': ttl
            }
        )
        logger.info(f"Recorded request: {request_id}")
    except Exception as e:
        logger.error(f"Error recording request: {str(e)}")

def check_concurrent_jobs():
    """
    Check if there are already training jobs running.
    Returns True if max concurrent jobs reached, False otherwise.
    """
    try:
        response = sm_client.list_training_jobs(
            StatusEquals='InProgress',
            MaxResults=10
        )
        
        in_progress_jobs = len(response.get('TrainingJobSummaries', []))
        logger.info(f"Current in-progress training jobs: {in_progress_jobs}")
        
        return in_progress_jobs >= MAX_CONCURRENT_JOBS
    except Exception as e:
        logger.error(f"Error checking concurrent jobs: {str(e)}")
        # Fail safe - assume limit reached on error
        return True

def retrain_model(bucket_name, object_key):
    """
    Trigger SageMaker training job with validated inputs and bounded execution.
    """
    logger.info(f"Starting retraining process at {datetime.datetime.now()}")
    
    # Get the SageMaker execution role
    role_name = os.environ['SAGEMAKER_ROLE_NAME']
    s3_bucket_uri = os.environ['S3_BUCKET_URI']
    max_runtime = int(os.environ.get('MAX_TRAINING_RUNTIME', '3600'))  # Default 1 hour
    
    role_response = iam_client.get_role(RoleName=role_name)
    role_arn = role_response['Role']['Arn']
    
    # Create training job with bounded runtime
    training_job_name = f'sklearn-training-job-{int(time.time())}'
    
    sm_client.create_training_job(
        TrainingJobName=training_job_name,
        AlgorithmSpecification={
            'TrainingImage': '683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3',
            'TrainingInputMode': 'File'
        },
        RoleArn=role_arn,
        InputDataConfig=[
            {
                'ChannelName': 'train',
                'DataSource': {
                    'S3DataSource': {
                        'S3DataType': 'S3Prefix',
                        'S3Uri': f's3://{s3_bucket_uri}/{object_key}',
                        'S3DataDistributionType': 'FullyReplicated'
                    }
                },
                'ContentType': 'text/csv'
            }
        ],
        OutputDataConfig={
            'S3OutputPath': f's3://{s3_bucket_uri}/'
        },
        ResourceConfig={
            'InstanceType': 'ml.m5.4xlarge',
            'InstanceCount': 1,
            'VolumeSizeInGB': 30
        },
        HyperParameters={
            'sagemaker_program': 'training_script.py',
            'sagemaker_submit_directory': f's3://{s3_bucket_uri}/code/code.tar.gz',
            'bucket_name': s3_bucket_uri
        },
        StoppingCondition={
            'MaxRuntimeInSeconds': max_runtime  # Reduced from 24 hours to 1 hour
        }
    )
    
    logger.info(f"Training job '{training_job_name}' created successfully")
    
    # Wait for training job to complete
    while True:
        response = sm_client.describe_training_job(TrainingJobName=training_job_name)
        status = response['TrainingJobStatus']
        if status in ['Completed', 'Failed', 'Stopped']:
            break
        time.sleep(30)
    
    if status != 'Completed':
        raise Exception(f"Training job failed with status: {status}")
    
    logger.info("Training completed, starting model creation")
    
    # Create model
    model_name = f'sklearn-model-{int(time.time())}'
    sm_client.create_model(
        ModelName=model_name,
        PrimaryContainer={
            'Image': '683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3',
            'ModelDataUrl': f"s3://{s3_bucket_uri}/model.tar.gz",
            'Environment': {
                'SAGEMAKER_PROGRAM': 'inference.py',
                'SAGEMAKER_SUBMIT_DIRECTORY': f's3://{s3_bucket_uri}/code/code.tar.gz'
            }
        },
        ExecutionRoleArn=role_arn
    )
    
    logger.info("Model created successfully")
    
    # Create endpoint configuration
    endpoint_config_name = f'endpoint-config-{int(time.time())}'
    sm_client.create_endpoint_config(
        EndpointConfigName=endpoint_config_name,
        ProductionVariants=[
            {
                'VariantName': 'AllTraffic',
                'ModelName': model_name,
                'InitialInstanceCount': 1,
                'InstanceType': 'ml.m5.4xlarge'
            }
        ]
    )
    
    logger.info("Endpoint configuration created")
    
    # Update existing endpoint
    existing_endpoint_name = "reccomendation-system-endpoint"
    sm_client.update_endpoint(
        EndpointName=existing_endpoint_name,
        EndpointConfigName=endpoint_config_name
    )
    
    logger.info(f"Updating endpoint at {datetime.datetime.now()}")
    
    # Wait for endpoint update to complete
    while True:
        response = sm_client.describe_endpoint(EndpointName=existing_endpoint_name)
        status = response['EndpointStatus']
        if status in ['InService', 'Failed']:
            break
        time.sleep(30)
    
    if status != 'InService':
        raise Exception(f"Endpoint update failed with status: {status}")
    
    logger.info(f"Endpoint update completed at {datetime.datetime.now()}")
    
    # Clean up temporary endpoint configuration
    sm_client.delete_endpoint_config(EndpointConfigName=endpoint_config_name)
    
    logger.info("Model retraining and endpoint update completed successfully.")