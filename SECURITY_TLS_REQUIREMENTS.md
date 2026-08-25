# TLS/HTTPS Security Requirements

## Overview

This document outlines the security requirements for deploying this application with proper TLS/HTTPS encryption to protect authentication credentials and bearer tokens from interception.

## Security Issue

The application handles sensitive authentication data:
- Login credentials (username/password) sent to `/api/login`
- JWT bearer tokens stored in browser localStorage
- Bearer tokens sent in `Authorization` headers on every authenticated request

**Without HTTPS, all of this data is transmitted in plaintext and can be intercepted or modified by network attackers.**

## Required Security Controls

### 1. Backend (Flask Application)

**Current State:**
- Flask binds to `127.0.0.1:8000` in production mode (when `FLASK_ENV=production`)
- Flask binds to `0.0.0.0:8000` in development mode (when `FLASK_ENV=development`)

**Production Requirements:**
- Flask MUST be deployed behind a TLS-terminating reverse proxy
- The reverse proxy MUST:
  - Listen on port 443 with a valid TLS certificate
  - Terminate TLS/HTTPS connections
  - Forward decrypted traffic to `localhost:8000` (Flask)
  - Reject or redirect HTTP (port 80) requests to HTTPS

**Recommended Reverse Proxy Options:**
1. **AWS Application Load Balancer (ALB)**
   - Configure ALB with ACM certificate
   - Create target group pointing to EC2 instance port 8000
   - Configure security group to allow ALB → EC2:8000 only
   - Remove public 0.0.0.0/0 → EC2:8000 ingress rule

2. **Nginx on EC2**
   ```nginx
   server {
       listen 443 ssl http2;
       server_name your-domain.com;
       
       ssl_certificate /path/to/cert.pem;
       ssl_certificate_key /path/to/key.pem;
       ssl_protocols TLSv1.2 TLSv1.3;
       
       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   
   server {
       listen 80;
       server_name your-domain.com;
       return 301 https://$server_name$request_uri;
   }
   ```

3. **Apache with mod_proxy**

### 2. Frontend (S3 Website)

**Current State:**
- S3 website endpoints only support HTTP (not HTTPS)
- Frontend is configured to use HTTPS API URLs (via update_urls.sh)
- Frontend validates API URLs and rejects non-HTTPS in production

**Production Requirements:**
- S3 bucket MUST be fronted by an HTTPS-capable distribution
- Options:
  1. **Amazon CloudFront (Recommended)**
     - Create CloudFront distribution with S3 bucket as origin
     - Configure ACM certificate for custom domain
     - Set default root object to `index.html`
     - Configure error pages
     - Update DNS to point to CloudFront distribution
  
  2. **Application Load Balancer**
     - Configure ALB with ACM certificate
     - Create target group with S3 website endpoint
     - Configure routing rules

### 3. Network Security (Terraform)

**Current State:**
- EC2 security group allows TCP/8000 from `0.0.0.0/0` (marked as security risk)
- Security group allows TCP/443 for HTTPS

**Production Requirements:**
- Remove or restrict the `0.0.0.0/0 → EC2:8000` ingress rule
- If using ALB: Allow only `ALB_SG → EC2:8000`
- If using nginx on EC2: Remove port 8000 ingress entirely (nginx listens on 443)
- Ensure port 443 ingress is configured for TLS termination point

### 4. API URL Configuration

**Current State:**
- `update_urls.sh` replaces `PLACE_HOLDER` with `https://` URLs
- Frontend validates API URLs and enforces HTTPS in production

**Production Requirements:**
- API URL MUST use `https://` scheme
- URL should point to the TLS termination endpoint (ALB, CloudFront, etc.)
- Never use direct EC2 public IP with HTTP

## Deployment Checklist

- [ ] Configure TLS certificate (ACM, Let's Encrypt, or commercial CA)
- [ ] Deploy TLS-terminating reverse proxy (ALB, CloudFront, nginx)
- [ ] Update backend security group to restrict port 8000 access
- [ ] Configure frontend distribution with HTTPS (CloudFront or ALB)
- [ ] Update DNS records to point to HTTPS endpoints
- [ ] Set `FLASK_ENV=production` in backend environment
- [ ] Verify API URL uses `https://` scheme
- [ ] Test that HTTP requests are rejected or redirected to HTTPS
- [ ] Verify authentication flow works over HTTPS
- [ ] Confirm bearer tokens are transmitted over encrypted connections only

## Testing

### Verify HTTPS Enforcement

1. **Backend:**
   ```bash
   # Should fail or redirect to HTTPS
   curl http://your-domain.com:8000/api/login
   
   # Should succeed
   curl https://your-domain.com/api/login
   ```

2. **Frontend:**
   ```bash
   # Should fail or redirect to HTTPS
   curl http://your-s3-website-endpoint
   
   # Should succeed
   curl https://your-cloudfront-domain
   ```

3. **Browser DevTools:**
   - Open Network tab
   - Perform login
   - Verify all requests use `https://` protocol
   - Verify no mixed content warnings

## Development vs Production

### Development Mode
- Set `FLASK_ENV=development`
- Flask binds to `0.0.0.0:8000` for local testing
- HTTPS validation is relaxed for localhost
- Use `http://localhost:8000` or `http://127.0.0.1:8000`

### Production Mode
- Set `FLASK_ENV=production`
- Flask binds to `127.0.0.1:8000`
- HTTPS validation is enforced
- Must use TLS-terminating reverse proxy
- All external traffic must use HTTPS

## References

- [OWASP Transport Layer Protection Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Protection_Cheat_Sheet.html)
- [AWS ALB HTTPS Listeners](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/create-https-listener.html)
- [CloudFront with S3](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/GettingStarted.SimpleDistribution.html)
- [Flask Deployment Options](https://flask.palletsprojects.com/en/2.3.x/deploying/)
