locals {
  organization = "rednine"
  default_tags = {
    ManagedBy = "terragrunt"
    Project   = "TerraRAG Demo"
  }
}

remote_state {
  backend = "s3"
  config = {
    bucket = "rednine-terraform-state"
    key    = "${path_relative_to_include()}/terraform.tfstate"
    region = "us-east-1"
  }
}
