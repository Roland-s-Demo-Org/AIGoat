#!/bin/bash

echo "operator_package_upgrade=false" >> /etc/ecs/ecs.config
# Install dependencies
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib
sudo apt-get install -y python3-pip jq awscli
pip3 install -r requirements.txt

# Retrieve database credentials from AWS Secrets Manager
# Note: This script requires AWS_REGION and SECRET_ID to be set as environment variables
SECRET_JSON=$(aws secretsmanager get-secret-value --secret-id $SECRET_ID --region $AWS_REGION --query SecretString --output text)
DB_USER=$(echo $SECRET_JSON | jq -r '.username')
DB_PASSWORD=$(echo $SECRET_JSON | jq -r '.password')
DB_HOST=$(echo $SECRET_JSON | jq -r '.host')
DB_NAME=$(echo $SECRET_JSON | jq -r '.dbname')

# Set environment variables
echo "FLASK_APP=app.py" >> ~/.bashrc
source ~/.bashrc

# Run migrations
python3 migrate_data.py --db_user=$DB_USER --db_password=$DB_PASSWORD --db_host=$DB_HOST --db_name=$DB_NAME
nohup python3 app.py --db_user=$DB_USER --db_password=$DB_PASSWORD --db_host=$DB_HOST --db_name=$DB_NAME --host=0.0.0.0 &