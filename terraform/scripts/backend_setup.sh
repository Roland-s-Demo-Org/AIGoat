#!/bin/bash

echo "operator_package_upgrade=false" >> /etc/ecs/ecs.config
# Install dependencies
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib
sudo apt-get install -y python3-pip jq
pip3 install -r requirements.txt

# Set environment variables
echo "FLASK_APP=app.py" >> ~/.bashrc
# Note: Database credentials should be retrieved from AWS Secrets Manager at runtime
# Do not hardcode credentials in this script
source ~/.bashrc

# Run migrations
# Credentials should be passed as command-line arguments from a secure source
python3 migrate_data.py
nohup python3 app.py --host=0.0.0.0 &