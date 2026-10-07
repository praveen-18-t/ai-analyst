# Upload -> S3 -> EventBridge -> SQS -> ingestion worker
resource "aws_sqs_queue" "dlq" {
  name                      = "${local.name}-ingest-dlq"
  message_retention_seconds = 1209600
  sqs_managed_sse_enabled   = true
}
resource "aws_sqs_queue" "ingest" {
  name                       = "${local.name}-ingest"
  visibility_timeout_seconds = 900
  receive_wait_time_seconds  = 20
  sqs_managed_sse_enabled    = true
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dlq.arn, maxReceiveCount = 3 })
}

resource "aws_cloudwatch_event_rule" "raw_uploaded" {
  name = "${local.name}-raw-uploaded"
  event_pattern = jsonencode({
    source        = ["aws.s3"]
    "detail-type" = ["Object Created"]
    detail = {
      bucket = { name = [aws_s3_bucket.data.bucket] }
      object = { key = [{ wildcard = "org=*/dataset=*/raw/*" }] }
    }
  })
}
resource "aws_cloudwatch_event_target" "to_sqs" {
  rule = aws_cloudwatch_event_rule.raw_uploaded.name
  arn  = aws_sqs_queue.ingest.arn
}
resource "aws_sqs_queue_policy" "allow_events" {
  queue_url = aws_sqs_queue.ingest.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.ingest.arn
      Condition = { ArnEquals = { "aws:SourceArn" = aws_cloudwatch_event_rule.raw_uploaded.arn } }
    }]
  })
}
