output "alb_dns_name" { value = aws_lb.main.dns_name }
output "cognito_user_pool_id" { value = aws_cognito_user_pool.main.id }
output "cognito_client_id" { value = aws_cognito_user_pool_client.web.id }
output "ecr_api_repo" { value = aws_ecr_repository.repos["api"].repository_url }
output "ecr_web_repo" { value = aws_ecr_repository.repos["web"].repository_url }
output "ecs_cluster" { value = aws_ecs_cluster.main.name }
output "data_bucket" { value = aws_s3_bucket.data.bucket }
