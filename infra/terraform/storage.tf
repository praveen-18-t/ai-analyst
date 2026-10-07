# One bucket, tenant prefix: s3://bucket/org=<id>/dataset=<id>/{raw,data}/...
resource "aws_kms_key" "s3" {
  description         = "${local.name} S3 encryption"
  enable_key_rotation = true
}

resource "aws_kms_alias" "s3" {
  name          = "alias/${local.name}-s3"
  target_key_id = aws_kms_key.s3.key_id
}

#trivy:ignore:AWS-0086
#trivy:ignore:AWS-0087
#trivy:ignore:AWS-0091
#trivy:ignore:AWS-0093
resource "aws_s3_bucket" "data" {
  bucket = "${local.name}-data-${data.aws_caller_identity.me.account_id}"
}
resource "aws_s3_bucket" "athena" {
  bucket = "${local.name}-athena-${data.aws_caller_identity.me.account_id}"
}

resource "aws_s3_bucket_public_access_block" "all" {
  for_each                = { data = aws_s3_bucket.data.id, athena = aws_s3_bucket.athena.id }
  bucket                  = each.value
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_server_side_encryption_configuration" "all" {
  for_each = { data = aws_s3_bucket.data.id, athena = aws_s3_bucket.athena.id }
  bucket   = each.value
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3.arn
    }
  }
}
resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_lifecycle_configuration" "athena" {
  bucket = aws_s3_bucket.athena.id
  rule {
    id     = "expire-results"
    status = "Enabled"
    filter {}
    expiration { days = 7 }
  }
}
# Send object events to EventBridge (filtered to raw/ uploads in queue.tf)
resource "aws_s3_bucket_notification" "data" {
  bucket      = aws_s3_bucket.data.id
  eventbridge = true
}

resource "aws_athena_workgroup" "main" {
  name          = var.project
  force_destroy = true
  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = var.athena_scan_limit_bytes
    engine_version { selected_engine_version = "Athena engine version 3" }
    result_configuration {
      output_location = "s3://${aws_s3_bucket.athena.bucket}/results/"
      encryption_configuration { encryption_option = "SSE_S3" }
    }
  }
}
