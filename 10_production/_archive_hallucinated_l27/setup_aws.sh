#!/bin/bash
# Level 27: Create AWS infrastructure for Research Agent
#
# Creates:
#   - DynamoDB tables (sessions, checkpoints) with TTL
#   - IAM role for AgentCore execution
#
# Prerequisites:
#   - AWS CLI configured with appropriate permissions
#   - AWS region set via AWS_REGION or defaults to us-east-1
#
# Usage:
#   ./setup_aws.sh
#   AWS_REGION=us-west-2 ./setup_aws.sh

set -e

echo "=================================================="
echo "Level 27: AWS Infrastructure Setup"
echo "=================================================="

# Configuration
REGION=${AWS_REGION:-us-east-1}
SESSIONS_TABLE="research_agent_sessions"
CHECKPOINTS_TABLE="research_agent_checkpoints"
ROLE_NAME="research-agent-agentcore-role"
POLICY_NAME="ResearchAgentPolicy"

echo ""
echo "Configuration:"
echo "  Region: $REGION"
echo "  Sessions Table: $SESSIONS_TABLE"
echo "  Checkpoints Table: $CHECKPOINTS_TABLE"
echo "  IAM Role: $ROLE_NAME"
echo ""

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo "ERROR: AWS CLI not found. Please install it first."
    exit 1
fi

# Verify AWS credentials
echo "Verifying AWS credentials..."
if ! aws sts get-caller-identity --region "$REGION" > /dev/null 2>&1; then
    echo "ERROR: AWS credentials not configured or invalid."
    echo "Run: aws configure"
    exit 1
fi
echo "  OK - Credentials valid"
echo ""

# =============================================================================
# 1. Create DynamoDB Tables
# =============================================================================

echo "Creating DynamoDB tables..."

# Sessions table
echo "  Creating $SESSIONS_TABLE..."
if aws dynamodb describe-table --table-name "$SESSIONS_TABLE" --region "$REGION" > /dev/null 2>&1; then
    echo "    Table already exists, skipping"
else
    aws dynamodb create-table \
        --table-name "$SESSIONS_TABLE" \
        --attribute-definitions \
            AttributeName=session_id,AttributeType=S \
            AttributeName=item_type,AttributeType=S \
        --key-schema \
            AttributeName=session_id,KeyType=HASH \
            AttributeName=item_type,KeyType=RANGE \
        --billing-mode PAY_PER_REQUEST \
        --region "$REGION" \
        --no-cli-pager
    echo "    Created"

    # Wait for table to be active
    echo "    Waiting for table to become active..."
    aws dynamodb wait table-exists --table-name "$SESSIONS_TABLE" --region "$REGION"
fi

# Checkpoints table
echo "  Creating $CHECKPOINTS_TABLE..."
if aws dynamodb describe-table --table-name "$CHECKPOINTS_TABLE" --region "$REGION" > /dev/null 2>&1; then
    echo "    Table already exists, skipping"
else
    aws dynamodb create-table \
        --table-name "$CHECKPOINTS_TABLE" \
        --attribute-definitions \
            AttributeName=research_id,AttributeType=S \
            AttributeName=checkpoint_id,AttributeType=S \
        --key-schema \
            AttributeName=research_id,KeyType=HASH \
            AttributeName=checkpoint_id,KeyType=RANGE \
        --billing-mode PAY_PER_REQUEST \
        --region "$REGION" \
        --no-cli-pager
    echo "    Created"

    # Wait for table to be active
    echo "    Waiting for table to become active..."
    aws dynamodb wait table-exists --table-name "$CHECKPOINTS_TABLE" --region "$REGION"
fi

echo ""

# =============================================================================
# 2. Enable TTL on Tables
# =============================================================================

echo "Enabling TTL on tables..."

echo "  Enabling TTL on $SESSIONS_TABLE (7 days)..."
aws dynamodb update-time-to-live \
    --table-name "$SESSIONS_TABLE" \
    --time-to-live-specification Enabled=true,AttributeName=ttl \
    --region "$REGION" \
    --no-cli-pager 2>/dev/null || echo "    TTL already enabled"

echo "  Enabling TTL on $CHECKPOINTS_TABLE (24 hours)..."
aws dynamodb update-time-to-live \
    --table-name "$CHECKPOINTS_TABLE" \
    --time-to-live-specification Enabled=true,AttributeName=ttl \
    --region "$REGION" \
    --no-cli-pager 2>/dev/null || echo "    TTL already enabled"

echo ""

# =============================================================================
# 3. Create IAM Role for AgentCore
# =============================================================================

echo "Creating IAM role..."

# Trust policy for Bedrock AgentCore
TRUST_POLICY='{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Service": "bedrock.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }
    ]
}'

echo "  Creating role $ROLE_NAME..."
if aws iam get-role --role-name "$ROLE_NAME" > /dev/null 2>&1; then
    echo "    Role already exists, skipping creation"
else
    aws iam create-role \
        --role-name "$ROLE_NAME" \
        --assume-role-policy-document "$TRUST_POLICY" \
        --description "IAM role for L27 Research Agent in AgentCore" \
        --no-cli-pager
    echo "    Created"
fi

# =============================================================================
# 4. Attach Permissions Policy
# =============================================================================

echo "  Attaching permissions policy..."

# Get AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Permissions policy
POLICY_DOCUMENT=$(cat <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "BedrockModelAccess",
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream"
            ],
            "Resource": [
                "arn:aws:bedrock:$REGION::foundation-model/anthropic.claude-3-5-sonnet*",
                "arn:aws:bedrock:$REGION::foundation-model/anthropic.claude-3-5-haiku*"
            ]
        },
        {
            "Sid": "DynamoDBAccess",
            "Effect": "Allow",
            "Action": [
                "dynamodb:GetItem",
                "dynamodb:PutItem",
                "dynamodb:Query",
                "dynamodb:DeleteItem",
                "dynamodb:UpdateItem"
            ],
            "Resource": [
                "arn:aws:dynamodb:$REGION:$ACCOUNT_ID:table/$SESSIONS_TABLE",
                "arn:aws:dynamodb:$REGION:$ACCOUNT_ID:table/$SESSIONS_TABLE/*",
                "arn:aws:dynamodb:$REGION:$ACCOUNT_ID:table/$CHECKPOINTS_TABLE",
                "arn:aws:dynamodb:$REGION:$ACCOUNT_ID:table/$CHECKPOINTS_TABLE/*"
            ]
        },
        {
            "Sid": "CloudWatchLogs",
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:$REGION:$ACCOUNT_ID:log-group:/aws/bedrock/*"
        }
    ]
}
EOF
)

aws iam put-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-name "$POLICY_NAME" \
    --policy-document "$POLICY_DOCUMENT" \
    --no-cli-pager
echo "    Attached"

echo ""

# =============================================================================
# Summary
# =============================================================================

echo "=================================================="
echo "Setup Complete!"
echo "=================================================="
echo ""
echo "Resources created:"
echo "  - DynamoDB Table: $SESSIONS_TABLE (TTL: 7 days)"
echo "  - DynamoDB Table: $CHECKPOINTS_TABLE (TTL: 24 hours)"
echo "  - IAM Role: $ROLE_NAME"
echo ""
echo "Role ARN:"
aws iam get-role --role-name "$ROLE_NAME" --query 'Role.Arn' --output text
echo ""
echo "Next steps:"
echo "  1. Build Docker image: docker build -t research-agent:l27 --platform linux/arm64 -f 10_production/Dockerfile ."
echo "  2. Push to ECR"
echo "  3. Deploy to AgentCore"
echo ""
echo "Environment variables for deployment:"
echo "  BEDROCK_REGION=$REGION"
echo "  DYNAMODB_SESSIONS_TABLE=$SESSIONS_TABLE"
echo "  DYNAMODB_CHECKPOINTS_TABLE=$CHECKPOINTS_TABLE"
echo ""
