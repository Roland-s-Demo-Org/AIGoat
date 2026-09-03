output "backend_url" {
  value = aws_lb.backend_alb.dns_name
}

output "rds_endpoint" {
  value = aws_db_instance.rds.endpoint
}

output "rds_address" {
  value = aws_db_instance.rds.address
}
