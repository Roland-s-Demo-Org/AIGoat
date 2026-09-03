import boto3
import time
import datetime
import logging
import os
# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def validate_s3_object(s3_client, bucket, key, expected_version_id=None, expected_etag=None):
    """
    Validate S3 object integrity by checking version ID and ETag.
    Returns True if validation passes, False otherwise.
    """
    try:
        # Get object metadata
        response = s3_client.head_object(Bucket=bucket, Key=key)
        
        # Check version ID if provided
        if expected_version_id:
            actual_version_id = response.get('VersionId', '')
            if actual_version_id != expected_version_id:
                logger.error(f"Version ID mismatch for {key}. Expected: {expected_version_id}, Got: {actual_version_id}")
                return False
        
        # Check ETag if provided
        if expected_etag:
            actual_etag = response.get('ETag', '').strip('"')
            expected_etag_clean = expected_etag.strip('"')
            if actual_etag != expected_etag_clean:
                logger.error(f"ETag mismatch for {key}. Expected: {expected_etag_clean}, Got: {actual_etag}")
                return False
        
        logger.info(f"Validation passed for {key}")
        return True
    except Exception as e:
        logger.error(f"Error validating {key}: {str(e)}")
        return False

def lambda_handler(event, context):
    # Code to trigger retraining
    retrain_model()
def retrain_model():
    sm_client = boto3.client('sagemaker')
    iam_client = boto3.client('iam')
    s3_client = boto3.client('s3')
    
    logger.info(f"starting proccess +{datetime.datetime.now()}")
    
    # Get the SageMaker execution role
    role_name = os.environ['SAGEMAKER_ROLE_NAME']
    s3_bucket_uri = os.environ['S3_BUCKET_URI']
    
    # Get trusted artifact identifiers from environment
    trusted_code_version_id = os.environ.get('TRUSTED_CODE_VERSION_ID')
    trusted_code_etag = os.environ.get('TRUSTED_CODE_ETAG')
    
    # Validate code artifact integrity before proceeding
    code_key = 'code/code.tar.gz'
    if not validate_s3_object(s3_client, s3_bucket_uri, code_key, 
                             expected_version_id=trusted_code_version_id,
                             expected_etag=trusted_code_etag):
        raise Exception(f"Code artifact validation failed for {code_key}. Aborting retraining to prevent execution of untrusted code.")
    
    role_response = iam_client.get_role(RoleName=role_name)
    role_arn = role_response['Role']['Arn']
    
    # Create training job
    training_job_name = f'sklearn-training-job-{int(time.time())}'
    
    # Use version-pinned S3 URI for code artifact
    code_s3_uri = f's3://{s3_bucket_uri}/{code_key}'
    if trusted_code_version_id:
        code_s3_uri = f's3://{s3_bucket_uri}/{code_key}?versionId={trusted_code_version_id}'
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
            'sagemaker_submit_directory': code_s3_uri, # Use version-pinned URI
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
    
    # Validate model artifact before creating model
    model_key = 'model.tar.gz'
    model_response = s3_client.head_object(Bucket=s3_bucket_uri, Key=model_key)
    model_version_id = model_response.get('VersionId', '')
    logger.info(f"Using model artifact version: {model_version_id}")
    
    # Create model with version-pinned URIs
    model_data_url = f"s3://{s3_bucket_uri}/{model_key}"
    if model_version_id:
        model_data_url = f"s3://{s3_bucket_uri}/{model_key}?versionId={model_version_id}"
    model_name = f'sklearn-model-{int(time.time())}'
    sm_client.create_model(
        ModelName=model_name,
        PrimaryContainer={
            'Image': '683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3',
            # Adjust region if needed
            'ModelDataUrl': model_data_url,
            'Environment': {
                'SAGEMAKER_PROGRAM': 'inference.py',
                'SAGEMAKER_SUBMIT_DIRECTORY': code_s3_uri  # Use version-pinned URI
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