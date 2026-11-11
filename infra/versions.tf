terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.72"
    }
  }

  # shortcut: state is local (infra/terraform.tfstate, gitignored); move it to an S3
  # backend before a second person or CI runs this.
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      project = "data-platform"
      env     = var.env
    }
  }
}
