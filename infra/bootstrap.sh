#!/usr/bin/env bash
# One-time setup: remote state bucket + lock table, then backend config.  Usage: ./bootstrap.sh [region]
set -euo pipefail
REGION="${1:-us-east-1}"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="ai-analyst-tfstate-${ACCOUNT}"
aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null || {
  if [ "$REGION" = "us-east-1" ]; then aws s3api create-bucket --bucket "$BUCKET" --region "$REGION"
  else aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" --create-bucket-configuration LocationConstraint="$REGION"; fi
  aws s3api put-bucket-versioning --bucket "$BUCKET" --versioning-configuration Status=Enabled
  aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
}
aws dynamodb describe-table --table-name ai-analyst-tflock --region "$REGION" >/dev/null 2>&1 || \
  aws dynamodb create-table --table-name ai-analyst-tflock --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH --billing-mode PAY_PER_REQUEST --region "$REGION" >/dev/null
cat > terraform/backend.hcl <<EOT
bucket         = "$BUCKET"
key            = "ai-analyst/prod.tfstate"
region         = "$REGION"
dynamodb_table = "ai-analyst-tflock"
encrypt        = true
EOT
echo "Wrote terraform/backend.hcl. Next:"
echo "  cd terraform && terraform init -backend-config=backend.hcl"
echo "  terraform apply -var desired_count=0     # creates everything, no tasks yet"
echo "  # push images (see README), then:  terraform apply -var image_tag=<tag>"
