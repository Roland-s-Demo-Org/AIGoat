import boto3
import time
import datetime
import logging
import os
import uuid
import hashlib
from decimal import Decimal

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    # Extract S3 event details for idempotency
    try:
        s3_records = event.get('Records', [])
        if not s3_records:
            logger.warning("No S3 records found in event")
            return {'statusCode': 400, 'body': 'No S3 records found'}
        
        # Get the first record (S3 event)
        record = s3_records[0]
        s3_info = record.get('s3', {})
        bucket_name = s3_info.get('bucket', {}).get('name', '')
        object_key = s3_info.get('object', {}).get('key', '')
        
        # Get object version/etag for idempotency
        s3_client = boto3.client('s3')
        try:
            obj_metadata = s3_client.head_object(Bucket=bucket_name, Key=object_key)
            etag = obj_metadata.get('ETag', '').strip('"')
            version_id = obj_metadata.get('VersionId', etag)
        except Exception as e:
            logger.error(f"Failed to get object metadata: {e}")
            etag = str(uuid.uuid4())
            version_id = etag
        
        logger.info(f"Processing S3 event for {object_key} with version {version_id}")
        
        # Code to trigger retraining with idempotency key
        retrain_model(version_id, etag)
        
        return {'statusCode': 200, 'body': 'Retraining completed successfully'}
    except Exception as e:
        logger.error(f"Error in lambda_handler: {e}")
        raise

def acquire_lock(dynamodb_client, table_name, lock_key, lock_value, ttl_seconds=900):
    """
    Acquire a distributed lock using DynamoDB conditional writes.
    Returns True if lock acquired, False otherwise.
    """
    try:
        current_time = int(time.time())
        ttl = current_time + ttl_seconds
        
        # Try to acquire lock with conditional write
        dynamodb_client.put_item(
            TableName=table_name,
            Item={
                'lock_key': {'S': lock_key},
                'lock_value': {'S': lock_value},
                'acquired_at': {'N': str(current_time)},
                'ttl': {'N': str(ttl)}
            },
            ConditionExpression='attribute_not_exists(lock_key) OR #ttl < :current_time',
            ExpressionAttributeNames={
                '#ttl': 'ttl'
            },
            ExpressionAttributeValues={
                ':current_time': {'N': str(current_time)}
            }
        )
        logger.info(f"Lock acquired: {lock_key}")
        return True
    except dynamodb_client.exceptions.ConditionalCheckFailedException:
        logger.warning(f"Lock already held: {lock_key}")
        return False
    except Exception as e:
        logger.error(f"Error acquiring lock: {e}")
        return False

def release_lock(dynamodb_client, table_name, lock_key, lock_value):
    """
    Release a distributed lock using DynamoDB conditional delete.
    """
    try:
        dynamodb_client.delete_item(
            TableName=table_name,
            Key={
                'lock_key': {'S': lock_key}
            },
            ConditionExpression='lock_value = :lock_value',
            ExpressionAttributeValues={
                ':lock_value': {'S': lock_value}
            }
        )
        logger.info(f"Lock released: {lock_key}")
    except Exception as e:
        logger.warning(f"Error releasing lock (may have expired): {e}")

def get_deployment_state(dynamodb_client, table_name):
    """
    Get the current deployment state from DynamoDB.
    """
    try:
        response = dynamodb_client.get_item(
            TableName=table_name,
            Key={
                'lock_key': {'S': 'deployment_state'}
            }
        )
        if 'Item' in response:
            return {
                'version': response['Item'].get('version', {}).get('S', ''),
                'generation': int(response['Item'].get('generation', {}).get('N', '0')),
                'model_name': response['Item'].get('model_name', {}).get('S', ''),
                'endpoint_config': response['Item'].get('endpoint_config', {}).get('S', '')
            }
        return None
    except Exception as e:
        logger.error(f"Error getting deployment state: {e}")
        return None

def update_deployment_state(dynamodb_client, table_name, version, generation, model_name, endpoint_config, expected_generation):
    """
    Update deployment state with generation check to prevent rollbacks.
    """
    try:
        current_time = int(time.time())
        
        if expected_generation is None:
            # First deployment
            dynamodb_client.put_item(
                TableName=table_name,
                Item={
                    'lock_key': {'S': 'deployment_state'},
                    'version': {'S': version},
                    'generation': {'N': str(generation)},
                    'model_name': {'S': model_name},
                    'endpoint_config': {'S': endpoint_config},
                    'updated_at': {'N': str(current_time)}
                },
                ConditionExpression='attribute_not_exists(lock_key)'
            )
        else:
            # Update only if generation is newer
            dynamodb_client.put_item(
                TableName=table_name,
                Item={
                    'lock_key': {'S': 'deployment_state'},
                    'version': {'S': version},
                    'generation': {'N': str(generation)},
                    'model_name': {'S': model_name},
                    'endpoint_config': {'S': endpoint_config},
                    'updated_at': {'N': str(current_time)}
                },
                ConditionExpression='attribute_not_exists(generation) OR generation < :new_generation',
                ExpressionAttributeValues={
                    ':new_generation': {'N': str(generation)}
                }
            )
        logger.info(f"Deployment state updated to generation {generation}")
        return True
    except dynamodb_client.exceptions.ConditionalCheckFailedException:
        logger.warning(f"Deployment state not updated - newer generation already exists")
        return False
    except Exception as e:
        logger.error(f"Error updating deployment state: {e}")
        return False

def check_idempotency(dynamodb_client, table_name, version_id):
    """
    Check if this version has already been processed.
    """
    try:
        response = dynamodb_client.get_item(
            TableName=table_name,
            Key={
                'lock_key': {'S': f'processed_{version_id}'}
            }
        )
        if 'Item' in response:
            logger.info(f"Version {version_id} already processed")
            return True
        return False
    except Exception as e:
        logger.error(f"Error checking idempotency: {e}")
        return False

def mark_processed(dynamodb_client, table_name, version_id):
    """
    Mark a version as processed with TTL.
    """
    try:
        current_time = int(time.time())
        ttl = current_time + (7 * 24 * 60 * 60)  # 7 days TTL
        
        dynamodb_client.put_item(
            TableName=table_name,
            Item={
                'lock_key': {'S': f'processed_{version_id}'},
                'processed_at': {'N': str(current_time)},
                'ttl': {'N': str(ttl)}
            }
        )
        logger.info(f"Version {version_id} marked as processed")
    except Exception as e:
        logger.error(f"Error marking version as processed: {e}")

def retrain_model(version_id, etag):
    sm_client = boto3.client('sagemaker')
    iam_client = boto3.client('iam')
    dynamodb_client = boto3.client('dynamodb')
    
    logger.info(f"Starting process +{datetime.datetime.now()}")
    
    # Get environment variables
    role_name = os.environ['SAGEMAKER_ROLE_NAME']
    s3_bucket_uri = os.environ['S3_BUCKET_URI']
    dynamodb_table = os.environ['DYNAMODB_TABLE_NAME']
    existing_endpoint_name = os.environ['ENDPOINT_NAME']
    
    # Check idempotency - skip if already processed
    if check_idempotency(dynamodb_client, dynamodb_table, version_id):
        logger.info(f"Skipping already processed version: {version_id}")
        return
    
    # Generate unique lock value for this invocation
    lock_value = str(uuid.uuid4())
    lock_key = 'retraining_lock'
    
    # Try to acquire distributed lock
    if not acquire_lock(dynamodb_client, dynamodb_table, lock_key, lock_value, ttl_seconds=900):
        logger.warning("Could not acquire lock - another retraining is in progress")
        return
    
    try:
        # Get current deployment state
        current_state = get_deployment_state(dynamodb_client, dynamodb_table)
        current_generation = current_state['generation'] if current_state else 0
        new_generation = int(time.time() * 1000)  # Use millisecond timestamp for generation
        
        logger.info(f"Current generation: {current_generation}, New generation: {new_generation}")
        
        # Get the SageMaker execution role
        role_response = iam_client.get_role(RoleName=role_name)
        role_arn = role_response['Role']['Arn']\n        
        # Create training job with unique name using millisecond timestamp and UUID
        training_job_name = f'sklearn-training-job-{new_generation}-{uuid.uuid4().hex[:8]}'
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
        
        logger.info("Training done\nStarting model creation")
        
        # Create model with unique name
        model_name = f'sklearn-model-{new_generation}-{uuid.uuid4().hex[:8]}'
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
        logger.info("Done model creation")
        
        # Create endpoint configuration with unique name
        endpoint_config_name = f'endpoint-config-{new_generation}-{uuid.uuid4().hex[:8]}'
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
        logger.info("Done endpoint config")
        
        # Update deployment state with generation check
        if not update_deployment_state(
            dynamodb_client, 
            dynamodb_table, 
            version_id, 
            new_generation, 
            model_name, 
            endpoint_config_name,
            current_generation
        ):
            logger.warning("Deployment state update failed - newer deployment exists. Cleaning up resources.")
            # Clean up resources since we won't deploy
            try:
                sm_client.delete_endpoint_config(EndpointConfigName=endpoint_config_name)
            except Exception as e:
                logger.error(f"Error cleaning up endpoint config: {e}")
            return
        
        # Update existing endpoint with generation check
        try:
            # Verify current endpoint config before updating
            endpoint_desc = sm_client.describe_endpoint(EndpointName=existing_endpoint_name)
            current_endpoint_config = endpoint_desc.get('EndpointConfigName', '')
            
            # Check if a newer config was already deployed
            if current_state and current_endpoint_config != current_state.get('endpoint_config', ''):
                logger.warning(f"Endpoint config mismatch - another deployment may have occurred")
            
            sm_client.update_endpoint(
                EndpointName=existing_endpoint_name,
                EndpointConfigName=endpoint_config_name
            )
            logger.info(f"Updating endpoint +{datetime.datetime.now()}")
            
            # Wait for endpoint update to complete
            while True:
                response = sm_client.describe_endpoint(EndpointName=existing_endpoint_name)
                status = response['EndpointStatus']
                if status in ['InService', 'Failed']:
                    break
                time.sleep(30)
            
            if status != 'InService':
                raise Exception(f"Endpoint update failed with status: {status}")
            
            logger.info(f"Done update +{datetime.datetime.now()}")
            
            # Clean up old endpoint configuration if it exists
            if current_state and current_state.get('endpoint_config'):
                try:
                    sm_client.delete_endpoint_config(EndpointConfigName=current_state['endpoint_config'])
                    logger.info(f"Deleted old endpoint config: {current_state['endpoint_config']}")
                except Exception as e:
                    logger.warning(f"Could not delete old endpoint config: {e}")
            
            # Mark this version as processed
            mark_processed(dynamodb_client, dynamodb_table, version_id)
            
            logger.info("Model retraining and endpoint update completed successfully.")
            
        except Exception as e:
            logger.error(f"Error updating endpoint: {e}")
            # Clean up the endpoint config we created since deployment failed
            try:
                sm_client.delete_endpoint_config(EndpointConfigName=endpoint_config_name)
            except Exception as cleanup_error:
                logger.error(f"Error cleaning up endpoint config: {cleanup_error}")
            raise
            
    finally:
        # Always release the lock
        release_lock(dynamodb_client, dynamodb_table, lock_key, lock_value)
