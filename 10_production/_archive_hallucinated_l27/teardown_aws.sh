#!/bin/bash
# Level 27: Clean up AWS infrastructure
#
# Removes:
#   - DynamoDB tables (sessions, checkpoints)
#   - IAM role and policy
#
# Usage:
#   ./teardown_aws.sh
#   AWS_REGION=us-west-2 ./teardown_aws.sh

set -e

echo "=================================================="
echo "Level 27: AWS Infrastructure Teardown"
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

# Confirm
read -p "Are you sure you want to delete these resources? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

echo ""

# =============================================================================
# 1. Delete DynamoDB Tables
# =============================================================================

echo "Deleting DynamoDB tables..."

echo "  Deleting $SESSIONS_TABLE..."
if aws dynamodb describe-table --table-name "$SESSIONS_TABLE" --region "$REGION" > /dev/null 2>&1; then
    aws dynamodb delete-table --table-name "$SESSIONS_TABLE" --region "$REGION" --no-cli-pager
    echo "    Deleted"
else
    echo "    Table not found, skipping"
fi

echo "  Deleting $CHECKPOINTS_TABLE..."
if aws dynamodb describe-table --table-name "$CHECKPOINTS_TABLE" --region "$REGION" > /dev/null 2>&1; then
    aws dynamodb delete-table --table-name "$CHECKPOINTS_TABLE" --region "$REGION" --no-cli-pager
    echo "    Deleted"
else
    echo "    Table not found, skipping"
fi

echo ""

# =============================================================================
# 2. Delete IAM Role and Policy
# =============================================================================

echo "Deleting IAM role..."

echo "  Deleting inline policy $POLICY_NAME..."
if aws iam get-role-policy --role-name "$ROLE_NAME" --policy-name "$POLICY_NAME" > /dev/null 2>&1; then
    aws iam delete-role-policy --role-name "$ROLE_NAME" --policy-name "$POLICY_NAME" --no-cli-pager
    echo "    Deleted"
else
    echo "    Policy not found, skipping"
fi

echo "  Deleting role $ROLE_NAME..."
if aws iam get-role --role-name "$ROLE_NAME" > /dev/null 2>&1; then
    aws iam delete-role --role-name "$ROLE_NAME" --no-cli-pager
    echo "    Deleted"
else
    echo "    Role not found, skipping"
fi

echo ""

# =============================================================================
# Summary
# =============================================================================

echo "=================================================="
echo "Teardown Complete!"
echo "=================================================="
echo ""
echo "Deleted resources:"
echo "  - DynamoDB Table: $SESSIONS_TABLE"
echo "  - DynamoDB Table: $CHECKPOINTS_TABLE"
echo "  - IAM Role: $ROLE_NAME"
echo ""
