#!/bin/bash

echo "operator_package_upgrade=false" >> /etc/ecs/ecs.config
# Install dependencies
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib
sudo apt-get install -y python3-pip
pip3 install -r requirements.txt

# Set environment variables
echo "FLASK_APP=app.py" >> ~/.bashrc
# Database credentials are retrieved from AWS Secrets Manager via environment variables
# DB_SECRET_ARN and AWS_DEFAULT_REGION should be set before running this script
source ~/.bashrc

# Run migrations
python3 migrate_data.py
nohup python3 app.py --host=0.0.0.0 &