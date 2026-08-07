include "root" {
  path   = find_in_parent_folders("root.hcl")
  expose = true
}

terraform {
  source = "../../../../../modules/app"
}

dependency "network" {
  config_path = "../network"
}

inputs = {
  environment   = "prod"
  instance_type = "m7g.large"
  worker_count  = 3
  vpc_id        = dependency.network.outputs.vpc_id
  subnet_ids    = dependency.network.outputs.private_subnet_ids
}
