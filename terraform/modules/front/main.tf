variable "vpc_id" {}

resource "random_string" "suffix" {
  length  = 8
  special = false
  upper   = false
  numeric = true
  lower   = true
}

resource "null_resource" "update_frontend_urls" {
  provisioner "local-exec" {
    command = "${path.module}/../../scripts/update_urls.sh ../frontend/out ${var.backend_url}"
  }
}

#resource "null_resource" "upload_frontend_files" {
#  depends_on = [null_resource.update_frontend_urls, aws_s3_bucket.frontend_bucket, aws_s3_bucket_policy.s3_bucket_policy]
#
#  provisioner "local-exec" {
#    command = "aws s3 sync ../frontend/out s3://${aws_s3_bucket.frontend_bucket.bucket} --acl public-read"
#  }
#}

resource "aws_s3_bucket" "frontend_bucket" {
  bucket = format("aigoat-frontend-bucket-${random_string.suffix.result}")
  force_destroy = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "frontend_bucket_encryption" {
  bucket = aws_s3_bucket.frontend_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true

  }
}

resource "aws_s3_bucket_ownership_controls" "s3_bucket_acl_ownership" {
  bucket = aws_s3_bucket.frontend_bucket.id
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

# CloudFront Origin Access Identity for secure S3 access
resource "aws_cloudfront_origin_access_identity" "frontend_oai" {
  comment = "OAI for AIGoat frontend bucket"
}

# Update S3 bucket policy to allow CloudFront access
resource "aws_s3_bucket_policy" "cloudfront_s3_policy" {
  bucket = aws_s3_bucket.frontend_bucket.id
  depends_on = [
    aws_s3_bucket_ownership_controls.s3_bucket_acl_ownership
  ]

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = aws_cloudfront_origin_access_identity.frontend_oai.iam_arn
        }
        Action = "s3:GetObject"
        Resource = "${aws_s3_bucket.frontend_bucket.arn}/*"
      }
    ]
  })
}

resource "aws_s3_bucket_public_access_block" "public_access_block" {
  bucket = aws_s3_bucket.frontend_bucket.id
  depends_on = [aws_s3_bucket_policy.cloudfront_s3_policy]

  block_public_acls       = true
  block_public_policy     = false
  ignore_public_acls      = true
  restrict_public_buckets = false
}

resource "aws_s3_bucket_object" "frontend_bucket" {
  depends_on = [null_resource.update_frontend_urls]
  for_each = fileset("../frontend/out/", "**/*")
  bucket = aws_s3_bucket.frontend_bucket.id
  key    = each.value
  source = "../frontend/out/${each.value}"
#  etag   = filemd5("../frontend/out/${each.value}")
  content_type  = lookup(local.content_types, split(".", each.value)[length(split(".", each.value)) - 1], "text/html")
#  content_type = file_content_type(each.value)
  cache_control = "no-cache"

}

resource "aws_s3_bucket_website_configuration" "frontend_website" {
  bucket = aws_s3_bucket.frontend_bucket.id

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "404.html"
  }

}

# CloudFront distribution for HTTPS frontend
resource "aws_cloudfront_distribution" "frontend_distribution" {
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  price_class         = "PriceClass_100"

  origin {
    domain_name = aws_s3_bucket.frontend_bucket.bucket_regional_domain_name
    origin_id   = "S3-${aws_s3_bucket.frontend_bucket.id}"

    s3_origin_config {
      origin_access_identity = aws_cloudfront_origin_access_identity.frontend_oai.cloudfront_access_identity_path
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
    default_ttl            = 0
    max_ttl                = 0
    compress               = true
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
    minimum_protocol_version       = "TLSv1.2_2021"
  }

  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/404.html"
  }

  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }

  tags = {
    Name = "aigoat-frontend-cloudfront"
  }
}

# Helper function to determine content type based on file extension
locals {
  content_types = {
    "html" = "text/html"
    "js"   = "application/javascript"
    "css"  = "text/css"
    "png"  = "image/png"
    "jpg"  = "image/jpeg"
    "jpeg" = "image/jpeg"
    "gif"  = "image/gif"
    "svg"  = "image/svg+xml"
    "ico"  = "image/x-icon"
    # Add more mappings as needed
  }
}