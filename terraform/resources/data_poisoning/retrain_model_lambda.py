import boto3
import time
import datetime
import logging
import os
import hashlib

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def verify_s3_object_integrity(s3_client, bucket, key, version_id):
    """Verify S3 object exists with specific version ID"""
    try:
        response = s3_client.head_object(Bucket=bucket, Key=key, VersionId=version_id)
        logger.info(f"Verified object {key} with version {version_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to verify object {key} with version {version_id}: {str(e)}")
        return False

def lambda_handler(event, context):
    # Code to trigger retraining
    retrain_model()

def retrain_model():
    sm_client = boto3.client('sagemaker')
    iam_client = boto3.client('iam')
    s3_client = boto3.client('s3')
    
    logger.info(f"starting process +{datetime.datetime.now()}")
    
    # Get the SageMaker execution role
    role_name = os.environ['SAGEMAKER_ROLE_NAME']
    s3_bucket_uri = os.environ['S3_BUCKET_URI']
    code_archive_version_id = os.environ.get('CODE_ARCHIVE_VERSION_ID')
    allowed_training_images = os.environ.get('ALLOWED_TRAINING_IMAGES', '').split(',')
    
    # Verify code archive integrity using version ID
    if not code_archive_version_id:
        raise Exception("CODE_ARCHIVE_VERSION_ID not configured - cannot proceed without integrity protection")
    
    if not verify_s3_object_integrity(s3_client, s3_bucket_uri, 'code/code.tar.gz', code_archive_version_id):
        raise Exception("Code archive integrity verification failed")
    
    role_response = iam_client.get_role(RoleName=role_name)
    role_arn = role_response['Role']['Arn']
    
    # Use approved training image
    training_image = allowed_training_images[0] if allowed_training_images else None
    if not training_image:
        raise Exception("No approved training image configured")
    
    # Create training job
    training_job_name = f'sklearn-training-job-{int(time.time())}'
    
    # Use versioned S3 URI for code archive
    code_s3_uri = f's3://{s3_bucket_uri}/code/code.tar.gz?versionId={code_archive_version_id}'
    
    sm_client.create_training_job(
        TrainingJobName=training_job_name,
        AlgorithmSpecification={
            'TrainingImage': training_image,
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
            'S3OutputPath': f's3://{s3_bucket_uri}/output/'
        },
        ResourceConfig={
            'InstanceType': 'ml.m5.4xlarge',
            'InstanceCount': 1,
            'VolumeSizeInGB': 30
        },
        HyperParameters={
            'sagemaker_program': 'training_script.py',
            'sagemaker_submit_directory': code_s3_uri,
            'bucket_name': s3_bucket_uri
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
    
    # Get the model artifact location from training job
    training_job_response = sm_client.describe_training_job(TrainingJobName=training_job_name)
    model_data_url = training_job_response['ModelArtifacts']['S3ModelArtifacts']
    logger.info(f"Using model artifact from training job: {model_data_url}")
    # Create model
    model_name = f'sklearn-model-{int(time.time())}'
    sm_client.create_model(
        ModelName=model_name,
        PrimaryContainer={
            'Image': training_image,
            'ModelDataUrl': model_data_url,  # Use output from training job, not mutable bucket path
            'Environment': {
                'SAGEMAKER_PROGRAM': 'inference.py',
                'SAGEMAKER_SUBMIT_DIRECTORY': code_s3_uri  # Use versioned code archive
            }
        },
        ExecutionRoleArn=role_arn
    )
    logger.info("done model creation")
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