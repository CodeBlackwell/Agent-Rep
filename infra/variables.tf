variable "domain" {
  description = "CDN subdomain for static assets"
  type        = string
  default     = "cdn.prove.codeblackwell.ai"
}

variable "origin_domain" {
  description = "Origin server domain (Caddy handles TLS)"
  type        = string
  default     = "prove.codeblackwell.ai"
}

variable "tags" {
  description = "Resource tags"
  type        = map(string)
  default = {
    Project = "prove"
  }
}
