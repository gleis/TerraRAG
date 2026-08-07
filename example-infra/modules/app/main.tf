variable "environment" {
  type = string
}

variable "instance_type" {
  type = string
}

variable "worker_count" {
  type = number
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

resource "aws_instance" "worker" {
  count         = var.worker_count
  instance_type = var.instance_type
  subnet_id     = var.subnet_ids[count.index % length(var.subnet_ids)]

  tags = {
    Name        = "${var.environment}-worker-${count.index + 1}"
    Environment = var.environment
    VpcId       = var.vpc_id
  }
}

output "worker_ids" {
  value = aws_instance.worker[*].id
}
