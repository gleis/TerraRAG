include "root" {
  path = find_in_parent_folders("root.hcl")
}

terraform {
  source = "../../../../../modules/app"
}

dependency "network" {
  config_path = "../network"
}

inputs = {
  environment   = "dev"
  instance_type = "t4g.small"
  worker_count  = 1
  vpc_id        = dependency.network.outputs.vpc_id
  subnet_ids    = dependency.network.outputs.private_subnet_ids
}
