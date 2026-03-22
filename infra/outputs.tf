output "cloudfront_domain" {
  description = "CloudFront distribution domain — create a CNAME pointing your CDN subdomain here"
  value       = aws_cloudfront_distribution.static.domain_name
}

output "acm_validation_records" {
  description = "DNS CNAME records to add on Porkbun for ACM certificate validation"
  value = {
    for dvo in aws_acm_certificate.cdn.domain_validation_options : dvo.domain_name => {
      type  = dvo.resource_record_type
      name  = dvo.resource_record_name
      value = dvo.resource_record_value
    }
  }
}
