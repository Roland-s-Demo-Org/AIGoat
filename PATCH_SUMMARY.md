# Security Patch Summary: TLS/HTTPS Enforcement

## Issue
The application exposed Flask directly on HTTP port 8000 to the Internet and published the frontend through an HTTP-only S3 website endpoint without enforcing HTTPS. This allowed login credentials and bearer tokens to traverse plaintext HTTP, making them vulnerable to interception or modification by on-path attackers.

## Changes Made

### 1. Backend Application (backend/app.py)
**Lines 432-450**

- Added environment-based binding logic using `FLASK_ENV` environment variable
- **Development mode** (`FLASK_ENV=development`): Binds to `0.0.0.0:8000` for local testing
- **Production mode** (default): Binds to `127.0.0.1:8000` to prevent direct Internet exposure
- Added security warning log message in production mode
- Added comprehensive security comments explaining the TLS requirement

**Impact:** Flask no longer accepts direct connections from the Internet in production mode. It must be fronted by a TLS-terminating reverse proxy.

### 2. Frontend Configuration (frontend/src/config/index.ts)
**Lines 1-56**

- Added `validateApiUrl()` function to enforce HTTPS in production
- Validates that API URLs use `https://` scheme (except for localhost/127.0.0.1)
- Logs security errors when non-HTTPS URLs are detected
- Throws error in strict production mode (`NODE_ENV=production`) to prevent insecure connections
- Added comprehensive security comments

**Impact:** Frontend will reject non-HTTPS API URLs in production, preventing plaintext credential transmission.

### 3. URL Update Script (terraform/scripts/update_urls.sh)
**Line 8**

- Changed from: `s|PLACE_HOLDER|http://$url:8000|g`
- Changed to: `s|PLACE_HOLDER|https://$url|g`
- Added security comments explaining the HTTPS requirement

**Impact:** Frontend will be configured with HTTPS API URLs by default.

### 4. Backend Setup Script (terraform/scripts/backend_setup.sh)
**Lines 11-18**

- Added `FLASK_ENV=production` environment variable
- Added security comments explaining the TLS proxy requirement
- Added TODO note for configuring nginx or ALB with TLS certificate

**Impact:** Backend will start in production mode by default, binding to localhost only.

### 5. Terraform Security Group (terraform/modules/webserver/main.tf)
**Lines 73-103**

- Added security warning comments on the `0.0.0.0/0 → EC2:8000` ingress rule
- Marked the rule as a security risk that should be removed or restricted
- Added port 443 ingress rule for HTTPS traffic
- Added comments explaining proper TLS termination architecture

**Impact:** Infrastructure code now documents the security risk and provides guidance for remediation.

### 6. Terraform S3 Configuration (terraform/modules/front/main.tf)
**Lines 100-120**

- Added comprehensive security comments before S3 website configuration
- Documented that S3 website endpoints only support HTTP
- Explained requirement for CloudFront, ALB, or other HTTPS-capable CDN
- Warned about plaintext exposure of credentials and tokens

**Impact:** Infrastructure code now documents the HTTPS requirement for the frontend.

### 7. Documentation Files (New)

Created three comprehensive documentation files:

- **SECURITY_TLS_REQUIREMENTS.md**: Detailed security requirements and controls
- **DEPLOYMENT_GUIDE.md**: Step-by-step deployment instructions with three options (ALB, CloudFront, Nginx)
- Both files include configuration examples, verification steps, and troubleshooting guidance

**Impact:** Operators have clear guidance on how to deploy the application securely.

## Security Improvements

### Before Patch
- ❌ Flask bound to `0.0.0.0:8000` accepting Internet traffic
- ❌ EC2 security group allowed `0.0.0.0/0` → port 8000
- ❌ Frontend configured with `http://` API URLs
- ❌ S3 website endpoint served over HTTP only
- ❌ No HTTPS validation in frontend
- ❌ No documentation of security requirements

### After Patch
- ✅ Flask binds to `127.0.0.1:8000` in production (localhost only)
- ✅ Security group rule documented as risk requiring remediation
- ✅ Frontend configured with `https://` API URLs
- ✅ Frontend validates and enforces HTTPS in production
- ✅ S3 configuration documented with HTTPS requirement
- ✅ Comprehensive security documentation provided
- ✅ Clear deployment guidance with three secure options

## Deployment Requirements

To fully mitigate this vulnerability, operators must:

1. **Deploy a TLS-terminating reverse proxy** (choose one):
   - AWS Application Load Balancer with ACM certificate
   - Amazon CloudFront distribution with ACM certificate
   - Nginx on EC2 with Let's Encrypt certificate

2. **Update security groups**:
   - Remove or restrict the `0.0.0.0/0 → EC2:8000` ingress rule
   - Allow only reverse proxy → EC2:8000 traffic

3. **Configure DNS**:
   - Point domain to TLS termination endpoint (ALB, CloudFront, etc.)

4. **Set environment variables**:
   - `FLASK_ENV=production` (already set in backend_setup.sh)
   - `NODE_ENV=production` for frontend build

5. **Verify deployment**:
   - Test that HTTP requests redirect to HTTPS
   - Verify direct port 8000 access is blocked
   - Confirm authentication works over HTTPS only

## Testing

Verification commands are provided in DEPLOYMENT_GUIDE.md, including:
- HTTPS enforcement testing
- Direct port 8000 access testing (should fail)
- Authentication flow testing over HTTPS
- Browser console verification (no mixed content)

## Backward Compatibility

- **Development environments**: Set `FLASK_ENV=development` to maintain `0.0.0.0:8000` binding
- **Existing deployments**: Will default to production mode and bind to localhost
- **Frontend**: HTTPS validation allows localhost for development

## References

- OWASP Transport Layer Protection Cheat Sheet
- AWS ALB HTTPS Listeners Documentation
- CloudFront with S3 Documentation
- Flask Deployment Best Practices
