terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# CloudFront requires ACM certs in us-east-1
provider "aws" {
  region = "us-east-1"
}
