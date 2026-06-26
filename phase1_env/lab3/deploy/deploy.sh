#!/usr/bin/env bash
# Build → push → update Lab 3 on AWS ECS Fargate.
#
# Usage:
#   AWS_ACCOUNT_ID=123456789012 AWS_REGION=ap-south-1 ./deploy.sh
#
# Prereqs:
#   - aws CLI configured with credentials that can push to ECR + update ECS
#   - One-time setup already done (see deploy/README.md): ECR repo, EFS,
#     cluster, service, IAM roles, secret, ALB.
#   - docker daemon running locally (or buildx for remote builds).
#
# What it does:
#   1. docker build the image
#   2. tag with both `latest` and the current git short SHA
#   3. log into ECR, push both tags
#   4. force-deploy the existing ECS service (it picks up :latest)
#   5. wait until the service is steady, print the ALB DNS name
#
# It does NOT create any AWS resources. That's deliberate — first-time setup
# is a manual / IaC pass; this script is the ongoing release flow.

set -euo pipefail

: "${AWS_ACCOUNT_ID:?set AWS_ACCOUNT_ID}"
: "${AWS_REGION:?set AWS_REGION}"

CLUSTER="${LAB3_CLUSTER:-lab3-cluster}"
SERVICE="${LAB3_SERVICE:-lab3-service}"
REPO="${LAB3_ECR_REPO:-lab3}"
ECR_HOST="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

SHA="$(git rev-parse --short HEAD 2>/dev/null || echo manual-$(date +%s))"

LAB3_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "→ Building image (sha=${SHA})"
docker build \
  -t "${REPO}:${SHA}" \
  -t "${REPO}:latest" \
  -f "${LAB3_DIR}/Dockerfile" \
  "${LAB3_DIR}"

echo "→ Tagging for ECR"
docker tag "${REPO}:${SHA}"    "${ECR_HOST}/${REPO}:${SHA}"
docker tag "${REPO}:latest"    "${ECR_HOST}/${REPO}:latest"

echo "→ Logging into ECR"
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${ECR_HOST}"

echo "→ Pushing image"
docker push "${ECR_HOST}/${REPO}:${SHA}"
docker push "${ECR_HOST}/${REPO}:latest"

echo "→ Forcing new deployment of ECS service ${SERVICE} on cluster ${CLUSTER}"
aws ecs update-service \
  --cluster "${CLUSTER}" \
  --service "${SERVICE}" \
  --force-new-deployment \
  --region "${AWS_REGION}" \
  > /dev/null

echo "→ Waiting for service to reach steady state (this can take a few minutes)…"
aws ecs wait services-stable \
  --cluster "${CLUSTER}" \
  --services "${SERVICE}" \
  --region "${AWS_REGION}"

ALB_DNS="$(aws elbv2 describe-load-balancers \
  --region "${AWS_REGION}" \
  --query "LoadBalancers[?contains(LoadBalancerName, 'lab3')].DNSName | [0]" \
  --output text 2>/dev/null || echo "unknown")"

echo
echo "✓ Deployed lab3:${SHA}"
echo "  ALB:    https://${ALB_DNS}/"
echo "  Logs:   aws logs tail /ecs/lab3 --region ${AWS_REGION} --follow"
echo "  Status: aws ecs describe-services --cluster ${CLUSTER} --services ${SERVICE} --region ${AWS_REGION}"
