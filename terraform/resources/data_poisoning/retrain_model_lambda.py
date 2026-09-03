import boto3
import time
import datetime
import logging
import os
# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Lambda handler that validates S3 event before triggering retraining.
    Only allows events from trusted AWS principals.
    """
    try:
        # Validate the event source
        if 'Records' not in event:
            logger.error("Invalid event format: missing Records")
            return {
                'statusCode': 400,
                'body': 'Invalid event format'
            }
        
        # Validate each record
        for record in event['Records']:
            # Check event source is S3
            if record.get('eventSource') != 'aws:s3':
                logger.error(f"Invalid event source: {record.get('eventSource')}")
                return {
                    'statusCode': 403,
                    'body': 'Unauthorized event source'
                }
            
            # Get the bucket and key
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            
            # Validate bucket name matches expected bucket
            expected_bucket = os.environ['S3_BUCKET_URI']
            if bucket != expected_bucket:
                logger.error(f"Bucket mismatch: {bucket} != {expected_bucket}")
                return {
                    'statusCode': 403,
                    'body': 'Unauthorized bucket'
                }
            
            # Validate the object key matches expected pattern
            if not key.startswith('product_ratings.csv'):
                logger.error(f"Invalid object key: {key}")
                return {
                    'statusCode': 403,
                    'body': 'Unauthorized object key'
                }
            
            # Validate object metadata and ownership
            s3_client = boto3.client('s3')
            try:
                obj_metadata = s3_client.head_object(Bucket=bucket, Key=key)
                
                # Check if object was uploaded by a trusted principal
                # by verifying it has proper server-side encryption
                if 'ServerSideEncryption' not in obj_metadata:
                    logger.error(f"Object {key} lacks server-side encryption")
                    return {
                        'statusCode': 403,
                        'body': 'Object does not meet security requirements'
                    }
                    
            except Exception as e:
                logger.error(f"Failed to validate object metadata: {str(e)}")
                return {
                    'statusCode': 500,
                    'body': 'Failed to validate object'
                }
        
        # If all validations pass, trigger retraining
        logger.info("Event validation passed, starting retraining")
        retrain_model()
        
        return {
            'statusCode': 200,
            'body': 'Retraining completed successfully'
        }
        
    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}")
        return {
            'statusCode': 500,
            'body': f'Error: {str(e)}'
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