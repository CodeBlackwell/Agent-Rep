# --- ACM Certificate (DNS validation via Porkbun) ---

resource "aws_acm_certificate" "cdn" {
  domain_name       = var.domain
  validation_method = "DNS"
  tags              = var.tags

  lifecycle {
    create_before_destroy = true
  }
}

# --- CloudFront Distribution ---

resource "aws_cloudfront_distribution" "static" {
  enabled         = true
  is_ipv6_enabled = true
  comment         = "PROVE static assets CDN"
  aliases         = [var.domain]
  price_class     = "PriceClass_100" # US + Europe (cheapest)

  origin {
    domain_name = var.origin_domain
    origin_id   = "caddy-origin"

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "caddy-origin"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    # Cache based on query string (for ?v=21 versioning)
    forwarded_values {
      query_string = true
      headers      = []

      cookies {
        forward = "none"
      }
    }

    min_ttl     = 0
    default_ttl = 86400     # 1 day
    max_ttl     = 31536000  # Respect origin Cache-Control up to 1 year
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate.cdn.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  tags = var.tags
}
