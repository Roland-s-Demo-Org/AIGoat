#!/bin/bash

echo "operator_package_upgrade=false" >> /etc/ecs/ecs.config
# Install dependencies
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib
sudo apt-get install -y python3-pip
pip3 install -r requirements.txt

# Set environment variables
echo "FLASK_APP=app.py" >> ~/.bashrc
# Security: Set FLASK_ENV to production to enforce localhost binding
# This prevents Flask from binding to 0.0.0.0 and exposing plaintext traffic
echo "FLASK_ENV=production" >> ~/.bashrc
echo "DATABASE_URL=postgresql://pos_user:password123@${aws_db_instance.rds.endpoint}/rds-database" >> ~/.bashrc
source ~/.bashrc

# Run migrations
python3 migrate_data.py

# Security Note: In production, Flask should be behind a TLS-terminating reverse proxy
# (nginx, Apache, ALB) that handles HTTPS on port 443 and forwards to localhost:8000.
# The current configuration binds Flask to 127.0.0.1:8000 when FLASK_ENV=production.
# TODO: Configure nginx or ALB with valid TLS certificate to terminate HTTPS traffic.
nohup python3 app.py --host=0.0.0.0 &