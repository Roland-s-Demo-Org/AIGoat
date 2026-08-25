#!/bin/bash
directory=$1
url=$2

# Security: Use HTTPS scheme to ensure encrypted communication.
# Plaintext HTTP exposes authentication credentials and bearer tokens to interception.
# The deployment should use a TLS-terminating load balancer or reverse proxy.
find "$directory" -type f \( -name "*.html" -o -name "*.js" -o -name "*.js.map" \) -print0 |
xargs -0 sed -i.bak "s|PLACE_HOLDER|https://$url|g"

# Check if backup files are created
find "$directory" -name "*.bak" -type f -print

# Remove backup files created by sed
find "$directory" -name "*.bak" -type f -delete

# Verify if backup files are deleted
find "$directory" -name "*.bak" -type f -print
