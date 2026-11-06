terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region  = "eu-central-1"
  profile = "etl"
}

resource "aws_s3_bucket" "hn_raw" {
  bucket = "etl-hn-raw-samfez"
}
