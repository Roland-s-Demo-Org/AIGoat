# Secure Deployment Guide

## Quick Start - Secure Production Deployment

This guide provides step-by-step instructions for deploying the application with proper TLS/HTTPS security.

## Option 1: AWS Application Load Balancer (Recommended)

### Step 1: Create ACM Certificate

```bash
# Request a certificate in AWS Certificate Manager
aws acm request-certificate \
  --domain-name your-domain.com \
  --validation-method DNS \
  --region us-east-1
```

Validate the certificate by adding the DNS records provided by ACM.

### Step 2: Update Terraform Configuration

Add to `terraform/modules/webserver/main.tf`:

```hcl
# Application Load Balancer
resource "aws_lb" "backend_alb" {
  name               = "backend-alb"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb_sg.id]
  subnets            = [var.subd_public, var.subd_public_2]  # Requires 2+ subnets

  enable_deletion_protection = false
}

# ALB Security Group
resource "aws_security_group" "alb_sg" {
  name        = "alb-sg"
  description = "Security group for ALB"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Target Group
resource "aws_lb_target_group" "backend_tg" {
  name     = "backend-tg"
  port     = 8000
  protocol = "HTTP"
  vpc_id   = var.vpc_id

  health_check {
    enabled             = true
    healthy_threshold   = 2
    interval            = 30
    matcher             = "200"
    path                = "/api/products"  # Use a valid health check endpoint
    port                = "traffic-port"
    protocol            = "HTTP"
    timeout             = 5
    unhealthy_threshold = 2
  }
}

# Attach EC2 instance to target group
resource "aws_lb_target_group_attachment" "backend_attachment" {
  target_group_arn = aws_lb_target_group.backend_tg.arn
  target_id        = aws_instance.backend.id
  port             = 8000
}

# HTTPS Listener
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.backend_alb.arn
  port              = "443"
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS-1-2-2017-01"
  certificate_arn   = "arn:aws:acm:region:account:certificate/certificate-id"  # Replace with your ACM cert ARN

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.backend_tg.arn
  }
}

# HTTP Listener (redirect to HTTPS)
resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.backend_alb.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type = "redirect"

    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

# Output ALB DNS name
output "alb_dns_name" {
  value = aws_lb.backend_alb.dns_name
}
```

### Step 3: Update EC2 Security Group

Modify the EC2 security group to only allow traffic from ALB:

```hcl
resource "aws_security_group" "ec2-sg" {
  # ... existing configuration ...

  # Remove or comment out the public 8000 ingress rule
  # ingress {
  #   from_port   = 8000
  #   to_port     = 8000
  #   protocol    = "tcp"
  #   cidr_blocks = ["0.0.0.0/0"]  # REMOVED
  # }

  # Add restricted 8000 ingress from ALB only
  ingress {
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb_sg.id]
    description     = "Allow traffic from ALB only"
  }
}
```

### Step 4: Update DNS

Point your domain to the ALB:

```bash
# Create CNAME or A record (alias) pointing to ALB DNS name
# Example: api.your-domain.com -> backend-alb-123456789.us-east-1.elb.amazonaws.com
```

### Step 5: Update Frontend Configuration

Modify `terraform/modules/front/variables.tf` to accept ALB URL:

```hcl
variable "backend_url" {
  description = "Backend API URL (should be ALB DNS name or custom domain)"
  type        = string
}
```

Update `terraform/scripts/update_urls.sh` call to use ALB URL instead of EC2 IP.

## Option 2: CloudFront + S3 + ALB

### Frontend (CloudFront + S3)

Add to `terraform/modules/front/main.tf`:

```hcl
# CloudFront Origin Access Identity
resource "aws_cloudfront_origin_access_identity" "oai" {
  comment = "OAI for frontend bucket"
}

# Update S3 bucket policy to allow CloudFront
resource "aws_s3_bucket_policy" "cloudfront_policy" {
  bucket = aws_s3_bucket.frontend_bucket.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = aws_cloudfront_origin_access_identity.oai.iam_arn
        }
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.frontend_bucket.arn}/*"
      }
    ]
  })
}

# CloudFront Distribution
resource "aws_cloudfront_distribution" "frontend_distribution" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  price_class         = "PriceClass_100"

  origin {
    domain_name = aws_s3_bucket.frontend_bucket.bucket_regional_domain_name
    origin_id   = "S3-${aws_s3_bucket.frontend_bucket.id}"

    s3_origin_config {
      origin_access_identity = aws_cloudfront_origin_access_identity.oai.cloudfront_access_identity_path
    }
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD"]
    target_origin_id = "S3-${aws_s3_bucket.frontend_bucket.id}"

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }

    viewer_protocol_policy = "redirect-to-https"
    min_ttl                = 0
    default_ttl            = 3600
    max_ttl                = 86400
    compress               = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
    # For custom domain:
    # acm_certificate_arn      = "arn:aws:acm:us-east-1:account:certificate/id"
    # ssl_support_method       = "sni-only"
    # minimum_protocol_version = "TLSv1.2_2021"
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/404.html"
  }
}

output "cloudfront_domain_name" {
  value = aws_cloudfront_distribution.frontend_distribution.domain_name
}

output "cloudfront_url" {
  value = "https://${aws_cloudfront_distribution.frontend_distribution.domain_name}"
}
```

## Option 3: Nginx Reverse Proxy on EC2

### Step 1: Install Nginx

Add to `terraform/scripts/backend_setup.sh`:

```bash
# Install nginx
sudo apt-get install -y nginx certbot python3-certbot-nginx

# Configure nginx
sudo tee /etc/nginx/sites-available/flask-app > /dev/null <<'EOF'
server {
    listen 80;
    server_name your-domain.com;
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;
    
    # SSL configuration (certbot will add these)
    # ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    # ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF

# Enable site
sudo ln -sf /etc/nginx/sites-available/flask-app /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test configuration
sudo nginx -t

# Start nginx
sudo systemctl enable nginx
sudo systemctl start nginx
```

### Step 2: Obtain TLS Certificate

```bash
# Using Let's Encrypt (after DNS is configured)
sudo certbot --nginx -d your-domain.com --non-interactive --agree-tos -m your-email@example.com

# Certbot will automatically update nginx configuration with SSL settings
```

### Step 3: Update Security Group

Remove public access to port 8000, keep only 443 and 80:

```hcl
resource "aws_security_group" "ec2-sg" {
  # Remove port 8000 ingress entirely
  
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
```

## Environment Variables

Ensure these are set in production:

```bash
# Backend
export FLASK_ENV=production
export FLASK_APP=app.py

# Frontend build
export NODE_ENV=production
```

## Verification Steps

After deployment, verify security:

1. **Test HTTPS enforcement:**
   ```bash
   # Should redirect to HTTPS
   curl -I http://your-domain.com/api/login
   
   # Should return 200 OK
   curl -I https://your-domain.com/api/login
   ```

2. **Test direct port 8000 access (should fail):**
   ```bash
   # Should timeout or be refused
   curl http://ec2-public-ip:8000/api/login
   ```

3. **Test authentication over HTTPS:**
   ```bash
   curl -X POST https://your-domain.com/api/login \
     -H "Content-Type: application/json" \
     -d '{"username":"babyshark","password":"doodoo123"}'
   ```

4. **Check browser console:**
   - No mixed content warnings
   - All requests use `https://`
   - Lock icon appears in address bar

## Troubleshooting

### Flask still binding to 0.0.0.0

Check environment variable:
```bash
echo $FLASK_ENV
# Should output: production
```

### Certificate errors

Verify certificate is valid:
```bash
openssl s_client -connect your-domain.com:443 -servername your-domain.com
```

### ALB health checks failing

- Verify security group allows ALB → EC2:8000
- Check Flask is running: `ps aux | grep python`
- Test health check endpoint: `curl http://localhost:8000/api/products`

### Frontend can't reach backend

- Verify API URL in browser console
- Check CORS configuration in Flask
- Verify DNS resolution: `nslookup your-domain.com`

## Additional Security Recommendations

1. **Use AWS Secrets Manager** for database credentials
2. **Enable AWS WAF** on ALB/CloudFront
3. **Implement rate limiting** to prevent brute force attacks
4. **Use strong JWT secrets** (not the default 'a_secret_key_that_you_should_change')
5. **Enable CloudTrail** for audit logging
6. **Implement HSTS headers** in reverse proxy
7. **Regular security updates** for all components

## References

- [AWS ALB Documentation](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/)
- [CloudFront Documentation](https://docs.aws.amazon.com/cloudfront/)
- [Let's Encrypt](https://letsencrypt.org/)
- [Nginx SSL Configuration](https://nginx.org/en/docs/http/configuring_https_servers.html)
