include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "../../../../../modules/network"
}

inputs = {
  environment = "prod"
  vpc_cidr    = "10.20.0.0/16"
  subnet_cidrs = ["10.20.10.0/24", "10.20.20.0/24"]
  tags         = include.root.locals.default_tags
}
