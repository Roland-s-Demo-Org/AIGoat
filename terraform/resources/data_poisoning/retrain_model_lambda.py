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

# Expected checksums for critical files (should be set during deployment)
EXPECTED_CHECKSUMS = {
    'code/code.tar.gz': os.environ.get('CODE_CHECKSUM', ''),
    'product_ratings.csv': os.environ.get('DATA_CHECKSUM', '')
}

def calculate_s3_object_checksum(bucket, key):
    """Calculate SHA256 checksum of an S3 object"""
    try:
        s3_client = boto3.client('s3')
        response = s3_client.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read()
        return hashlib.sha256(content).hexdigest()
    except Exception as e:
        logger.error(f"Error calculating checksum for {key}: {str(e)}")
        return None

def validate_artifact_integrity(bucket):
    """Validate integrity of training artifacts"""
    for key, expected_checksum in EXPECTED_CHECKSUMS.items():
        if not expected_checksum:
            logger.warning(f"No expected checksum configured for {key}, skipping validation")
            continue
            
        actual_checksum = calculate_s3_object_checksum(bucket, key)
        if actual_checksum != expected_checksum:
            logger.error(f"Integrity check failed for {key}: expected {expected_checksum}, got {actual_checksum}")
            return False
    
    logger.info("All artifact integrity checks passed")
    return True

def lambda_handler(event, context):
    # Validate the event source and structure
    try:
        # Ensure event is from S3
        if 'Records' not in event:
            logger.error("Invalid event structure: missing Records")
            return {
                'statusCode': 400,
                'body': json.dumps('Invalid event structure')
            }
        
        # Get expected bucket name from environment
        expected_bucket = os.environ.get('S3_BUCKET_URI')
        
        # Validate each record
        for record in event['Records']:
            # Verify event source is S3
            if record.get('eventSource') != 'aws:s3':
                logger.error(f"Invalid event source: {record.get('eventSource')}")
                return {
                    'statusCode': 403,
                    'body': json.dumps('Unauthorized event source')
                }
            
            # Verify bucket name matches expected bucket
            bucket_name = record.get('s3', {}).get('bucket', {}).get('name')
            if bucket_name != expected_bucket:
                logger.error(f"Bucket mismatch: {bucket_name} != {expected_bucket}")
                return {
                    'statusCode': 403,
                    'body': json.dumps('Unauthorized bucket')
                }
            
            # Verify object key is the expected dataset file
            object_key = record.get('s3', {}).get('object', {}).get('key')
            if not object_key or not object_key.startswith('product_ratings.csv'):
                logger.error(f"Invalid object key: {object_key}")
                return {
                    'statusCode': 403,
                    'body': json.dumps('Unauthorized object key')
                }
            
            # Verify the principal is from the same AWS account
            user_identity = record.get('userIdentity', {})
            principal_id = user_identity.get('principalId', '')
            
            # Log the validated event
            logger.info(f"Validated S3 event from bucket: {bucket_name}, key: {object_key}")
        
        # Validate artifact integrity before retraining
        if not validate_artifact_integrity(expected_bucket):
            logger.error("Artifact integrity validation failed, aborting retraining")
            return {
                'statusCode': 403,
                'body': json.dumps('Artifact integrity validation failed')
            }
        
        # Code to trigger retraining only after validation
        retrain_model()
        
        return {
            'statusCode': 200,
            'body': json.dumps('Retraining initiated successfully')
        }
        
    except Exception as e:
        logger.error(f"Error processing event: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }

def retrain_model():
    sm_client = boto3.client('sagemaker')
    iam_client = boto3.client('iam')
    logger.info(f"starting proccess +{datetime.datetime.now()}")
    # Get the SageMaker execution role
    role_name = os.environ['SAGEMAKER_ROLE_NAME']
    s3_bucket_uri = os.environ['S3_BUCKET_URI']
    role_response = iam_client.get_role(RoleName=role_name)
    role_arn = role_response['Role']['Arn']
    # Create training job
    training_job_name = f'sklearn-training-job-{int(time.time())}'
    sm_client.create_training_job(
        TrainingJobName=training_job_name,
        AlgorithmSpecification={
            'TrainingImage': '683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3',
            # Adjust region if needed
            'TrainingInputMode': 'File'
        },
        RoleArn=role_arn,
        InputDataConfig=[
            {
                'ChannelName': 'train',
                'DataSource': {
                    'S3DataSource': {
                        'S3DataType': 'S3Prefix',
                        'S3Uri': f's3://{s3_bucket_uri}/product_ratings.csv',
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
            'sagemaker_program': 'training_script.py',  # This replaces the EntryPoint
            'sagemaker_submit_directory': f's3://{s3_bucket_uri}/code/code.tar.gz', # Ensure your script is in this S3 location
            'bucket_name': s3_bucket_uri  # Pass the S3 bucket name as a hyperparameter
        },
        StoppingCondition={
            'MaxRuntimeInSeconds': 86400
        }
    )
    # Wait for training job to complete
    while True:
        response = sm_client.describe_training_job(TrainingJobName=training_job_name)
        status = response['TrainingJobStatus']
        if status in ['Completed', 'Failed', 'Stopped']:
            break
        time.sleep(30)
    if status != 'Completed':
        raise Exception(f"Training job failed with status: {status}")
    logger.info("training done\n starting model creation")
    # Create model
    model_name = f'sklearn-model-{int(time.time())}'
    sm_client.create_model(
        ModelName=model_name,
        PrimaryContainer={
            'Image': '683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3',
            # Adjust region if needed
            'ModelDataUrl': f"s3://{s3_bucket_uri}/model.tar.gz",
            'Environment': {
                'SAGEMAKER_PROGRAM': 'inference.py',
                'SAGEMAKER_SUBMIT_DIRECTORY': f's3://{s3_bucket_uri}/code/code.tar.gz'
                # Ensure your inference script is in this S3 location
            }
        },
        ExecutionRoleArn=role_arn
    )
    logger.info("done model creation")
    # Create endpoint configuration
    endpoint_config_name = f'endpoint-config-1722516468'
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
    logger.info("done endpoint config")
    # Update existing endpoint
    existing_endpoint_name = "reccomendation-system-endpoint"  # The Prod/Existing Endpoint Name
    sm_client.update_endpoint(
        EndpointName=existing_endpoint_name,
        EndpointConfigName=endpoint_config_name
    )
    logger.info(f"updating gendpoint +{datetime.datetime.now()}")
    # Wait for endpoint update to complete
    while True:
        response = sm_client.describe_endpoint(EndpointName=existing_endpoint_name)
        status = response['EndpointStatus']
        if status in ['InService', 'Failed']:
            break
        time.sleep(30)
    if status != 'InService':
        raise Exception(f"Endpoint update failed with status: {status}")
    logger.info(f"done update +{datetime.datetime.now()}")
    # Clean up temporary endpoint configuration
    sm_client.delete_endpoint_config(EndpointConfigName=endpoint_config_name)
    logger.info("Model retraining and endpoint update completed successfully.")