include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../../../modules/network"
}

inputs = {
  environment  = "dev"
  vpc_cidr     = "10.10.0.0/16"
  subnet_cidrs = ["10.10.10.0/24", "10.10.20.0/24"]
}
