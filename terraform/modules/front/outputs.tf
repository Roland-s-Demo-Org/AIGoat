output "frontend_url" {
  value = aws_cloudfront_distribution.frontend_distribution.domain_name
}

output "bucket_url" {
  value = aws_cloudfront_distribution.frontend_distribution.domain_name
}

output "cloudfront_url" {
  value = "https://${aws_cloudfront_distribution.frontend_distribution.domain_name}"
}
