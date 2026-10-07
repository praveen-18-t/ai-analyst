resource "aws_ecr_repository" "repos" {
  for_each             = toset(["api", "web"])
  name                 = "${var.project}-${each.value}"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration { scan_on_push = true }
  force_delete = var.environment != "prod"
}
