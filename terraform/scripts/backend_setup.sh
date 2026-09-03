#!/bin/bash

echo "operator_package_upgrade=false" >> /etc/ecs/ecs.config
# Install dependencies
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib
sudo apt-get install -y python3-pip
sudo apt-get install -y jq awscli
pip3 install -r requirements.txt

# Note: This script is deprecated in favor of cloud-init user-data.
# Database credentials should be retrieved from AWS Secrets Manager.
# Example:
# DB_PASSWORD=$(aws secretsmanager get-secret-value --secret-id <secret-id> --region <region> --query SecretString --output text)
# python3 migrate_data.py --db_user=pos_user --db_password="$DB_PASSWORD" --db_host=<host> --db_name=<dbname>
# nohup python3 app.py --db_user=pos_user --db_password="$DB_PASSWORD" --db_host=<host> --db_name=<dbname> --host=0.0.0.0 &