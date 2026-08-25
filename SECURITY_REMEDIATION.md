# SECURITY REMEDIATION NOTICE

## Critical Security Issue - Private Key Exposure

### Issue
The file `terraform/resources/webserver.pem` contains a private SSH key that was previously committed to this repository. This key has been used to provision EC2 instances and must be considered **COMPROMISED**.

### Actions Required

1. **Remove the private key from repository history**
   ```bash
   # Use git-filter-repo or BFG Repo-Cleaner to remove the file from all commits
   git filter-repo --path terraform/resources/webserver.pem --invert-paths
   # OR
   bfg --delete-files webserver.pem
   ```

2. **Revoke the compromised key pair in AWS**
   ```bash
   aws ec2 delete-key-pair --key-name webserver-key --region <your-region>
   ```

3. **Terminate any EC2 instances using the compromised key**
   - Identify instances with the key pair: `aws ec2 describe-instances --filters "Name=key-name,Values=webserver-key"`
   - Terminate or replace these instances

4. **Review access logs**
   - Check CloudTrail logs for any unauthorized access attempts
   - Review EC2 instance logs for suspicious activity
   - Check for any lateral movement or data exfiltration

5. **Rotate all related credentials**
   - Database passwords (currently hardcoded - separate issue)
   - API keys and tokens
   - Any other secrets that may have been accessible from the compromised instance

6. **Clean up CI/CD artifacts**
   - Remove the private key from any CI/CD workspace caches
   - Invalidate any build artifacts that may contain the key
   - Review GitHub Actions logs and artifacts

### Changes Made

This patch implements the following security improvements:

1. **Removed SSH file provisioner** - The Terraform configuration no longer uses SSH to provision files, eliminating the need for a repository-committed private key.

2. **Removed SSH key pair resource** - The `aws_key_pair` resource has been commented out and should be removed entirely after verification.

3. **Removed world-open SSH ingress rule** - The security group no longer allows SSH (port 22) from 0.0.0.0/0.

4. **Added .gitignore** - Prevents future accidental commits of sensitive credential files.

### Recommended Secure Alternatives

For EC2 instance access and file deployment:

1. **AWS Systems Manager Session Manager**
   - No inbound ports required
   - Centralized access logging
   - IAM-based authentication
   - No SSH keys to manage

2. **File Deployment Options**
   - **Custom AMI**: Pre-bake application files into the AMI
   - **S3**: Upload files to S3 and download using instance IAM role
   - **CodeDeploy**: Use AWS CodeDeploy for application deployment
   - **Container**: Package application as a Docker container

3. **Emergency SSH Access** (if absolutely necessary)
   - Use EC2 Instance Connect for temporary SSH access
   - Restrict SSH to specific IP ranges (VPN, bastion host)
   - Use short-lived SSH certificates
   - Never commit private keys to source control

### Verification

After applying this patch:
- [ ] Verify no SSH provisioner exists in Terraform code
- [ ] Verify SSH port 22 is not exposed to 0.0.0.0/0
- [ ] Verify webserver.pem is removed from repository history
- [ ] Verify AWS key pair "webserver-key" is deleted
- [ ] Verify .gitignore prevents future credential commits
- [ ] Implement secure file deployment method
- [ ] Test instance provisioning with new deployment method

### References

- [AWS Systems Manager Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html)
- [AWS EC2 Instance Connect](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Connect-using-EC2-Instance-Connect.html)
- [Removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)
