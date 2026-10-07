variable "project" {
  type    = string
  default = "ai-analyst"
}
variable "environment" {
  type    = string
  default = "prod"
}
variable "region" {
  type    = string
  default = "us-east-1"
}
variable "image_tag" {
  type    = string
  default = "latest"
}
variable "desired_count" {
  description = "ECS tasks per service. Use 0 for the very first apply, push images, then apply again."
  type        = number
  default     = 2
}
variable "acm_certificate_arn" {
  description = "Optional. When set, ALB serves HTTPS and redirects HTTP."
  type        = string
  default     = ""
}
variable "db_instance_class" {
  type    = string
  default = "db.t4g.small"
}
variable "bedrock_model_id" {
  description = "Bedrock model / inference profile id enabled in this account+region."
  type        = string
  default     = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
}
variable "athena_scan_limit_bytes" {
  description = "Per-query data scan cutoff for the Athena workgroup."
  type        = number
  default     = 10737418240 # 10 GB
}
variable "alarm_email" {
  type    = string
  default = ""
}
variable "allowed_cidrs" {
  description = "CIDRs allowed to reach the ALB."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
