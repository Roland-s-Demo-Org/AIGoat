# Security Fix: Terraform State Integrity and Locking

## Vulnerability Summary
The original implementation had critical security vulnerabilities in how Terraform state was managed:
- No S3 backend configuration in Terraform
- Manual state download/upload without integrity verification
- TOCTOU (Time-of-Check-Time-of-Use) race condition
- Download failures suppressed with `|| true`
- No state locking mechanism
- Auto-approved destroy without plan validation
- Unconditional state upload even on failures

## Security Improvements Implemented

### 1. S3 Backend Configuration (terraform/main.tf)
- **Added**: Proper S3 backend configuration with encryption enabled
- **Added**: DynamoDB table reference for state locking
- **Added**: Validation flags to prevent skipping security checks
- **Benefit**: Terraform now manages state directly through its backend, eliminating manual file handling

### 2. Apply Workflow (.github/workflows/tf-apply-main.yml)

#### S3 Bucket Security Controls
- **Added**: S3 versioning for state file integrity and rollback capability
- **Added**: Server-side encryption (AES256) for data at rest
- **Added**: Public access block to prevent unauthorized access
- **Added**: Bucket ownership controls (BucketOwnerEnforced)
- **Benefit**: State files are protected from tampering and unauthorized access

#### DynamoDB State Locking
- **Added**: DynamoDB table creation for distributed state locking
- **Added**: PAY_PER_REQUEST billing mode for cost efficiency
- **Benefit**: Prevents concurrent modifications and race conditions

#### Backend Initialization
- **Removed**: Manual state download with `aws s3 cp || true`
- **Removed**: Unconditional state upload with `if: always()`
- **Added**: Backend configuration passed to `terraform init`
- **Benefit**: Terraform handles state management with built-in integrity checks

### 3. Destroy Workflow (.github/workflows/tf-destroy-main.yml)

#### Pre-flight Validation
- **Added**: Comprehensive backend readiness checks
- **Added**: S3 bucket existence verification
- **Added**: DynamoDB table existence verification
- **Added**: Versioning status validation
- **Added**: State file metadata capture (ETag, VersionId)
- **Benefit**: Ensures all prerequisites are met before attempting destroy

#### State Integrity Verification
- **Removed**: Manual state download with `aws s3 cp || true`
- **Added**: Backend-managed state retrieval through `terraform init`
- **Added**: State validation with `terraform validate`
- **Benefit**: Eliminates TOCTOU vulnerability and ensures state integrity

#### Destroy Plan Generation
- **Added**: Explicit destroy plan generation with `terraform plan -destroy`
- **Added**: Plan output display for audit trail
- **Changed**: Execute destroy using pre-generated plan instead of direct destroy
- **Benefit**: Provides visibility into what will be destroyed and validates operations

#### State Cleanup
- **Added**: State archival before deletion for audit purposes
- **Added**: DynamoDB table cleanup after successful destroy
- **Added**: Explicit failure handling with state preservation
- **Benefit**: Maintains audit trail and ensures clean resource removal

## Attack Vector Mitigation

### Original Attack Vector
1. Attacker with S3 write access overwrites `terraform.tfstate`
2. Workflow performs existence check (passes)
3. Attacker overwrites state again (TOCTOU window)
4. Workflow downloads tampered state
5. `terraform destroy -auto-approve` executes with forged state
6. Attacker-controlled resources are destroyed

### Mitigations Applied

#### 1. S3 Versioning
- Every state modification creates a new version
- Terraform backend tracks specific versions
- Tampering creates detectable version mismatches

#### 2. DynamoDB State Locking
- Terraform acquires exclusive lock before state operations
- Concurrent modifications are blocked
- Lock prevents TOCTOU race conditions

#### 3. Backend-Managed State
- Terraform directly manages state through S3 backend
- No manual file handling in workflows
- Built-in integrity checks and checksums

#### 4. Encryption and Access Controls
- Server-side encryption protects data at rest
- Public access blocked at bucket level
- Bucket ownership enforced

#### 5. Plan-Based Destroy
- Destroy plan generated and validated before execution
- Plan output visible in workflow logs
- State locked during plan generation and execution

#### 6. Fail-Fast Error Handling
- Removed `|| true` that suppressed errors
- Added `set -e` for immediate failure on errors
- Backend validation before operations

## Residual Risks

While these mitigations significantly improve security, some risks remain:

1. **Privileged S3 Access**: An attacker with sufficient S3 permissions could still:
   - Delete state versions
   - Modify bucket policies
   - Disable versioning
   - **Mitigation**: Implement least-privilege IAM policies, enable CloudTrail logging, use S3 Object Lock for immutability

2. **DynamoDB Access**: An attacker with DynamoDB access could:
   - Delete the lock table
   - Manipulate lock entries
   - **Mitigation**: Restrict DynamoDB permissions, enable CloudTrail logging

3. **Workflow Secrets**: Compromised AWS credentials still allow full access
   - **Mitigation**: Use OIDC federation instead of long-lived credentials, implement credential rotation

4. **Auto-Approve**: Destroy still uses auto-approve (though with a validated plan)
   - **Mitigation**: Consider requiring manual approval for production environments

## Recommendations for Further Hardening

1. **S3 Object Lock**: Enable compliance mode to make state versions immutable
2. **OIDC Federation**: Replace long-lived AWS credentials with GitHub OIDC
3. **State Encryption**: Use AWS KMS for customer-managed encryption keys
4. **Audit Logging**: Enable CloudTrail for all S3 and DynamoDB operations
5. **Manual Approval**: Add manual approval gate for destroy operations in production
6. **Checksum Validation**: Add explicit MD5/SHA256 validation for critical operations
7. **Bucket Policies**: Implement restrictive bucket policies limiting access to specific principals
8. **MFA Delete**: Enable MFA delete on the state bucket for additional protection
