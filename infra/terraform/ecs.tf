resource "aws_ecs_cluster" "main" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

resource "aws_cloudwatch_log_group" "svc" {
  for_each          = toset(["api", "web", "worker"])
  name              = "/ecs/${local.name}/${each.value}"
  retention_in_days = 30
}

resource "aws_security_group" "tasks" {
  name   = "${local.name}-tasks"
  vpc_id = module.vpc.vpc_id
  ingress {
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ---- IAM ------------------------------------------------------------------------------------------
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "exec" {
  name               = "${local.name}-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}
resource "aws_iam_role_policy_attachment" "exec" {
  role       = aws_iam_role.exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}
resource "aws_iam_role_policy" "exec_secrets" {
  role = aws_iam_role.exec.id
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = ["secretsmanager:GetSecretValue"], Resource = aws_db_instance.main.master_user_secret[0].secret_arn }]
  })
}

resource "aws_iam_role" "task" {
  name               = "${local.name}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}
resource "aws_iam_role_policy" "task" {
  role = aws_iam_role.task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"], Resource = "${aws_s3_bucket.data.arn}/*" },
      { Effect = "Allow", Action = ["s3:ListBucket", "s3:GetBucketLocation"], Resource = [aws_s3_bucket.data.arn, aws_s3_bucket.athena.arn] },
      { Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject", "s3:AbortMultipartUpload"], Resource = "${aws_s3_bucket.athena.arn}/*" },
      { Effect = "Allow", Action = ["athena:StartQueryExecution", "athena:GetQueryExecution", "athena:GetQueryResults", "athena:StopQueryExecution"], Resource = aws_athena_workgroup.main.arn },
      { Effect = "Allow", Action = ["glue:GetDatabase", "glue:GetDatabases", "glue:CreateDatabase", "glue:GetTable", "glue:GetTables", "glue:CreateTable", "glue:UpdateTable", "glue:DeleteTable", "glue:GetPartitions"], Resource = "*" },
      { Effect = "Allow", Action = ["bedrock:InvokeModel", "bedrock:Converse"], Resource = "*" },
      { Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"], Resource = aws_sqs_queue.ingest.arn },
    ]
  })
}

# ---- Task definitions -----------------------------------------------------------------------------
locals {
  api_env = {
    ENV                  = var.environment
    AUTH_MODE            = "cognito"
    COGNITO_USER_POOL_ID = aws_cognito_user_pool.main.id
    COGNITO_CLIENT_ID    = aws_cognito_user_pool_client.web.id
    AWS_REGION           = var.region
    STORAGE              = "s3"
    S3_BUCKET            = aws_s3_bucket.data.bucket
    QUERY_ENGINE         = "athena"
    ATHENA_WORKGROUP     = aws_athena_workgroup.main.name
    LLM_PROVIDER         = "bedrock"
    BEDROCK_MODEL_ID     = var.bedrock_model_id
    EMBEDDINGS_PROVIDER  = "bedrock"
    ALLOW_PRIVATE_HOSTS  = "false"
    DB_HOST              = aws_db_instance.main.address
    DB_NAME              = "analyst"
    DB_USER              = "analyst"
    DATA_DIR             = "/tmp/data"
    CORS_ORIGINS         = ""
  }
  db_secret = [{ name = "DB_PASSWORD", valueFrom = "${aws_db_instance.main.master_user_secret[0].secret_arn}:password::" }]
}

resource "aws_ecs_task_definition" "api" {
  family                   = "${local.name}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = 4096
  execution_role_arn       = aws_iam_role.exec.arn
  task_role_arn            = aws_iam_role.task.arn
  container_definitions = jsonencode([{
    name             = "api"
    image            = "${aws_ecr_repository.repos["api"].repository_url}:${var.image_tag}"
    essential        = true
    portMappings     = [{ containerPort = 8000 }]
    environment      = [for k, v in local.api_env : { name = k, value = v }]
    secrets          = local.db_secret
    logConfiguration = { logDriver = "awslogs", options = { awslogs-group = aws_cloudwatch_log_group.svc["api"].name, awslogs-region = var.region, awslogs-stream-prefix = "api" } }
  }])
}

resource "aws_ecs_task_definition" "worker" {
  family                   = "${local.name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 2048
  memory                   = 8192
  ephemeral_storage { size_in_gib = 100 }
  execution_role_arn = aws_iam_role.exec.arn
  task_role_arn      = aws_iam_role.task.arn
  container_definitions = jsonencode([{
    name             = "worker"
    image            = "${aws_ecr_repository.repos["api"].repository_url}:${var.image_tag}"
    essential        = true
    command          = ["python", "-m", "app.ingestion.worker"]
    environment      = concat([for k, v in local.api_env : { name = k, value = v }], [{ name = "QUEUE_URL", value = aws_sqs_queue.ingest.url }])
    secrets          = local.db_secret
    logConfiguration = { logDriver = "awslogs", options = { awslogs-group = aws_cloudwatch_log_group.svc["worker"].name, awslogs-region = var.region, awslogs-stream-prefix = "worker" } }
  }])
}

resource "aws_ecs_task_definition" "web" {
  family                   = "${local.name}-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.exec.arn
  container_definitions = jsonencode([{
    name             = "web"
    image            = "${aws_ecr_repository.repos["web"].repository_url}:${var.image_tag}"
    essential        = true
    portMappings     = [{ containerPort = 3000 }]
    logConfiguration = { logDriver = "awslogs", options = { awslogs-group = aws_cloudwatch_log_group.svc["web"].name, awslogs-region = var.region, awslogs-stream-prefix = "web" } }
  }])
}

# ---- Services ---------------------------------------------------------------------------------------
resource "aws_ecs_service" "api" {
  name            = "api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets         = module.vpc.private_subnets
    security_groups = [aws_security_group.tasks.id]
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  depends_on = [aws_lb_listener_rule.api]
}

resource "aws_ecs_service" "web" {
  name            = "web"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.web.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets         = module.vpc.private_subnets
    security_groups = [aws_security_group.tasks.id]
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "web"
    container_port   = 3000
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }
  depends_on = [aws_lb_listener.http]
}

resource "aws_ecs_service" "worker" {
  name            = "worker"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.worker.arn
  desired_count   = var.desired_count == 0 ? 0 : 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets         = module.vpc.private_subnets
    security_groups = [aws_security_group.tasks.id]
  }
}

# ---- Autoscaling (API) ------------------------------------------------------------------------------
resource "aws_appautoscaling_target" "api" {
  max_capacity       = 10
  min_capacity       = max(var.desired_count, 1)
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.api.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}
resource "aws_appautoscaling_policy" "api_cpu" {
  name               = "cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.api.resource_id
  scalable_dimension = aws_appautoscaling_target.api.scalable_dimension
  service_namespace  = aws_appautoscaling_target.api.service_namespace
  target_tracking_scaling_policy_configuration {
    target_value = 60
    predefined_metric_specification { predefined_metric_type = "ECSServiceAverageCPUUtilization" }
  }
}
