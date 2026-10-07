resource "aws_sns_topic" "alarms" { name = "${local.name}-alarms" }
resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "alb_5xx" {
  alarm_name          = "${local.name}-alb-5xx"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  dimensions          = { LoadBalancer = aws_lb.main.arn_suffix }
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 10
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}
resource "aws_cloudwatch_metric_alarm" "dlq" {
  alarm_name          = "${local.name}-ingest-dlq"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}
resource "aws_cloudwatch_metric_alarm" "db_cpu" {
  alarm_name          = "${local.name}-db-cpu"
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  dimensions          = { DBInstanceIdentifier = aws_db_instance.main.identifier }
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

# App metrics (AIAnalyst namespace) are emitted by the API via CloudWatch Embedded Metric Format.
resource "aws_cloudwatch_dashboard" "main" {
  dashboard_name = local.name
  dashboard_body = jsonencode({
    widgets = [
      { type = "metric", x = 0, y = 0, width = 12, height = 6, properties = { title = "Ask latency (ms)", region = var.region, stat = "p90", period = 300,
      metrics = [["AIAnalyst", "AskLatencyMs", "Status", "ok"], ["AIAnalyst", "AskLatencyMs", "Status", "failed"]] } },
      { type = "metric", x = 12, y = 0, width = 12, height = 6, properties = { title = "LLM cost (USD) and tokens", region = var.region, stat = "Sum", period = 3600,
      metrics = [["AIAnalyst", "LLMCostUSD"], ["AIAnalyst", "LLMTokens", { yAxis = "right" }]] } },
      { type = "metric", x = 0, y = 6, width = 12, height = 6, properties = { title = "ALB requests / 5xx", region = var.region, stat = "Sum", period = 300,
      metrics = [["AWS/ApplicationELB", "RequestCount", "LoadBalancer", aws_lb.main.arn_suffix], [".", "HTTPCode_Target_5XX_Count", ".", "."]] } },
      { type = "metric", x = 12, y = 6, width = 12, height = 6, properties = { title = "Ingestion", region = var.region, stat = "Sum", period = 300,
      metrics = [["AIAnalyst", "IngestionFailures"], ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", aws_sqs_queue.ingest.name]] } },
    ]
  })
}
