locals {
  name = "${var.project}-${var.environment}"
  azs  = slice(data.aws_availability_zones.az.names, 0, 2)
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.13"

  name            = local.name
  cidr            = "10.20.0.0/16"
  azs             = local.azs
  public_subnets  = ["10.20.0.0/24", "10.20.1.0/24"]
  private_subnets = ["10.20.10.0/24", "10.20.11.0/24"]
  database_subnets = ["10.20.20.0/24", "10.20.21.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = var.environment != "prod"
  one_nat_gateway_per_az = var.environment == "prod"
  create_database_subnet_group = true
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = module.vpc.vpc_id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = module.vpc.private_route_table_ids
}
