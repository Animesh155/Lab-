# Lab 3 — AWS ECS Fargate deployment runbook

This directory holds the artifacts to deploy Lab 3 to AWS. Lab 3 is a single
stateful FastAPI + WebSocket server. State is in-memory; logs go to EFS.

```
deploy/
├── README.md                       this file
├── task-definition.json            ECS Fargate task definition template
├── iam-task-execution-role.json    IAM policy for the execution role
├── iam-task-role.json              IAM policy for the task role (EFS access)
└── deploy.sh                       one-shot build → push → release
```

Every JSON template uses placeholder strings (`ACCOUNT_ID`, `REGION`,
`EFS_ID`, `ACCESS_POINT_ID`). Replace them with `sed` or fill them in by
hand — there is no templating engine here on purpose.

## What you're building

```
                              ┌────────────────────────┐
                              │  Route 53  (optional)  │
                              │  lab3.example.com      │
                              └────────────┬───────────┘
                                           │
                              ┌────────────▼──────────────┐
                              │  ALB  (HTTPS, WS, sticky) │
                              │  idle timeout 300 s       │
                              └────────────┬──────────────┘
                                           │
              ┌────────────────────────────▼────────────────────────────┐
              │  ECS Fargate service "lab3-service" (desiredCount = 1)  │
              │                                                         │
              │   ┌─────────────────────────────────────────────────┐   │
              │   │  Task: 0.5 vCPU, 1 GB, public ECR image         │   │
              │   │  /  → static HMI (HTML/CSS/JS)                  │   │
              │   │  /ws/group/{gid} → WebSocket (students)         │   │
              │   │  /ws/instructor → WebSocket (instructor)        │   │
              │   │  /api/instructor/* → REST                       │   │
              │   │                                                 │   │
              │   │  EFS mount  → /data/events (JSONL session log)  │   │
              │   │  Secrets   → LAB3_INSTRUCTOR_TOKEN              │   │
              │   └─────────────────────────────────────────────────┘   │
              └─────────────────────────────────────────────────────────┘
```

Single replica is intentional. The scenario engine is in-memory; horizontal
scaling needs an external state store (out of scope today).

## One-time AWS setup

Run this once per environment, in order. After this, `./deploy.sh` is the
ongoing release flow.

### 1. Set shell variables

```bash
export AWS_ACCOUNT_ID=123456789012
export AWS_REGION=ap-south-1     # pick the region nearest your classroom
export VPC_ID=vpc-xxxxxxxx       # any VPC with at least 2 public subnets
export SUBNET_A=subnet-xxxxxxxx
export SUBNET_B=subnet-xxxxxxxx
```

### 2. ECR repository

```bash
aws ecr create-repository \
  --repository-name lab3 \
  --image-scanning-configuration scanOnPush=true \
  --region $AWS_REGION
```

### 3. CloudWatch Logs group

```bash
aws logs create-log-group --log-group-name /ecs/lab3 --region $AWS_REGION
aws logs put-retention-policy --log-group-name /ecs/lab3 --retention-in-days 30 --region $AWS_REGION
```

### 4. Secrets Manager — instructor token

```bash
TOKEN=$(openssl rand -hex 32)
aws secretsmanager create-secret \
  --name lab3/instructor-token \
  --description "Lab 3 instructor REST/WS auth token" \
  --secret-string "{\"token\":\"$TOKEN\"}" \
  --region $AWS_REGION
echo "instructor token: $TOKEN     ← save this somewhere you can find it"
```

Copy the secret's ARN into `task-definition.json` (the `valueFrom` of the
`LAB3_INSTRUCTOR_TOKEN` entry).

### 5. EFS — durable event log

```bash
# Create the filesystem
FS_ID=$(aws efs create-file-system \
  --performance-mode generalPurpose \
  --throughput-mode bursting \
  --encrypted \
  --tags Key=Name,Value=lab3-events \
  --region $AWS_REGION \
  --query 'FileSystemId' --output text)

# Mount targets in both subnets (use a security group that allows NFS 2049
# from your Fargate task's security group)
aws efs create-mount-target --file-system-id $FS_ID --subnet-id $SUBNET_A \
  --security-groups sg-efs-XXXX --region $AWS_REGION
aws efs create-mount-target --file-system-id $FS_ID --subnet-id $SUBNET_B \
  --security-groups sg-efs-XXXX --region $AWS_REGION

# Access point so the container writes as the lab3 (uid=1000) user
AP_ID=$(aws efs create-access-point \
  --file-system-id $FS_ID \
  --posix-user Uid=1000,Gid=1000 \
  --root-directory 'Path=/events,CreationInfo={OwnerUid=1000,OwnerGid=1000,Permissions=0755}' \
  --region $AWS_REGION \
  --query 'AccessPointId' --output text)

echo "FS_ID=$FS_ID  AP_ID=$AP_ID"
```

Paste both into `task-definition.json` (under `volumes[0].efsVolumeConfiguration`).

### 6. IAM roles

```bash
# Trust policy
cat > /tmp/trust-ecs-tasks.json <<'EOF'
{"Version":"2012-10-17","Statement":[{"Effect":"Allow",
 "Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}
EOF

# Execution role (pulls image, reads secret, writes logs)
aws iam create-role --role-name lab3-task-execution-role \
  --assume-role-policy-document file:///tmp/trust-ecs-tasks.json
aws iam put-role-policy --role-name lab3-task-execution-role \
  --policy-name lab3-task-execution-policy \
  --policy-document file://iam-task-execution-role.json

# Task role (writes events to EFS)
aws iam create-role --role-name lab3-task-role \
  --assume-role-policy-document file:///tmp/trust-ecs-tasks.json
aws iam put-role-policy --role-name lab3-task-role \
  --policy-name lab3-task-policy \
  --policy-document file://iam-task-role.json
```

Both policy JSONs in this directory have `ACCOUNT_ID`, `REGION`, and
`EFS_ID` placeholders — fill those in before running `put-role-policy`.

### 7. ECS cluster

```bash
aws ecs create-cluster \
  --cluster-name lab3-cluster \
  --capacity-providers FARGATE \
  --region $AWS_REGION
```

### 8. ALB + target group

```bash
# Security group for the ALB (open 443 from the internet)
SG_ALB=$(aws ec2 create-security-group \
  --group-name lab3-alb-sg --description "Lab 3 ALB" --vpc-id $VPC_ID \
  --region $AWS_REGION --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id $SG_ALB \
  --protocol tcp --port 443 --cidr 0.0.0.0/0 --region $AWS_REGION

# ALB
ALB_ARN=$(aws elbv2 create-load-balancer \
  --name lab3-alb --type application --scheme internet-facing \
  --subnets $SUBNET_A $SUBNET_B --security-groups $SG_ALB \
  --region $AWS_REGION --query 'LoadBalancers[0].LoadBalancerArn' --output text)

# Target group — HTTP, IP target type (required for Fargate)
TG_ARN=$(aws elbv2 create-target-group \
  --name lab3-tg --protocol HTTP --port 8080 --target-type ip \
  --vpc-id $VPC_ID \
  --health-check-path / --health-check-interval-seconds 15 \
  --region $AWS_REGION --query 'TargetGroups[0].TargetGroupArn' --output text)

# Cookie stickiness — REQUIRED, the in-memory state is per-task
aws elbv2 modify-target-group-attributes \
  --target-group-arn $TG_ARN --region $AWS_REGION \
  --attributes \
    Key=stickiness.enabled,Value=true \
    Key=stickiness.type,Value=lb_cookie \
    Key=stickiness.lb_cookie.duration_seconds,Value=86400

# Idle timeout for long-lived WebSockets
aws elbv2 modify-load-balancer-attributes \
  --load-balancer-arn $ALB_ARN --region $AWS_REGION \
  --attributes Key=idle_timeout.timeout_seconds,Value=300

# Listener (use your ACM cert ARN)
aws elbv2 create-listener \
  --load-balancer-arn $ALB_ARN \
  --protocol HTTPS --port 443 \
  --certificates CertificateArn=arn:aws:acm:$AWS_REGION:$AWS_ACCOUNT_ID:certificate/CERT_ID \
  --default-actions Type=forward,TargetGroupArn=$TG_ARN \
  --region $AWS_REGION
```

### 9. ECS service

```bash
# Fill in task-definition.json placeholders first, then register:
aws ecs register-task-definition --cli-input-json file://task-definition.json \
  --region $AWS_REGION

# Security group for the Fargate task (8080 from ALB SG only)
SG_TASK=$(aws ec2 create-security-group \
  --group-name lab3-task-sg --description "Lab 3 task" --vpc-id $VPC_ID \
  --region $AWS_REGION --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id $SG_TASK \
  --protocol tcp --port 8080 --source-group $SG_ALB --region $AWS_REGION

# The task SG also needs to reach the EFS mount target SG on 2049 — set that
# up on whichever SG you used for sg-efs-XXXX in step 5.

aws ecs create-service \
  --cluster lab3-cluster --service-name lab3-service \
  --task-definition lab3 --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_A,$SUBNET_B],securityGroups=[$SG_TASK],assignPublicIp=ENABLED}" \
  --load-balancers "targetGroupArn=$TG_ARN,containerName=lab3,containerPort=8080" \
  --deployment-configuration "maximumPercent=100,minimumHealthyPercent=0" \
  --region $AWS_REGION
```

`maximumPercent=100, minimumHealthyPercent=0` is **not** the safe default —
it means ECS drops the old task before starting the new one (brief downtime
during deploy). Acceptable here because lab sessions are ephemeral; not
acceptable for production multi-tenant apps.

## Day-to-day: deploying a new version

After the one-time setup above:

```bash
export AWS_ACCOUNT_ID=123456789012
export AWS_REGION=ap-south-1
cd phase1_env/lab3/deploy
./deploy.sh
```

The script builds the image, tags it with `latest` and the current git SHA,
pushes both to ECR, force-redeploys the ECS service, and waits for the
service to reach steady state. Prints the ALB URL at the end.

## Verifying a deployment

After `deploy.sh` finishes, the simulator's own smoke test works against the
ALB URL — no code changes needed:

```bash
export LAB3_BASE_URL=https://lab3.example.com
export LAB3_INSTRUCTOR_TOKEN="$(aws secretsmanager get-secret-value \
  --secret-id lab3/instructor-token --region $AWS_REGION \
  --query SecretString --output text | jq -r .token)"

cd phase1_env/lab3
PYTHONPATH=. .lab3_venv/bin/python tests/smoke_test.py
```

Expected: all checks pass, including the JSONL event log under
`/data/events/` (now on EFS — visible to next task too).

## Costs (rough, ap-south-1)

| Resource | Approx monthly |
|---|---|
| Fargate task (0.5 vCPU, 1 GB, 24×7) | ~$13 |
| ALB | ~$18 |
| EFS (1 GB, burst) | <$1 |
| Secrets Manager (1 secret) | <$1 |
| CloudWatch Logs (30-day retention) | <$1 |
| **Total** | **~$33 / month** |

If you only run the lab a few times per term, set `desiredCount=0` between
sessions to drop the Fargate cost to zero.

## Common gotchas

- **WebSocket upgrades fail with 502.** Target-group stickiness not on, or
  task security group blocks ALB SG. Re-check step 8.
- **Task fails to start with "ResourceInitializationError: failed to invoke
  EFS utils".** Task SG can't reach EFS mount target on port 2049. Fix the
  EFS mount target SG to allow ingress from the task SG.
- **Image won't pull.** Execution role missing `ecr:*` permissions, or ECR
  repo in a different region than the cluster.
- **`secretsmanager:GetSecretValue` denied.** Secret ARN wildcard in the
  execution role policy doesn't match the actual secret name suffix
  (Secrets Manager appends a random 6-char suffix).
- **Container starts, ALB target stays "draining"/"unhealthy".** Health
  check path is wrong or returns non-200. ALB checks `/` — make sure
  `web/index.html` is in the image.

## Future cleanups (not blockers)

- Convert to CloudFormation or Terraform so the one-time setup is
  idempotent and reviewable.
- GitHub Actions workflow that runs `deploy.sh` on push to `main`.
- WAF in front of the ALB if students will be on the public internet.
- Switch to an internal-only ALB + Cloudflare Access for instructor auth.
