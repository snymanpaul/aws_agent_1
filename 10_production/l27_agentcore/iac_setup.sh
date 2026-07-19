#!/bin/bash
# Level 27: AgentCore IAM Setup via CLI (Infrastructure as Code)
#
# This script creates the IAM policy required for AgentCore deployment.
# All resources are created via CLI - zero console access.
#
# Prerequisites:
#   - AWS CLI configured with SSO or credentials
#   - Python 3.10+
#
# Usage:
#   ./iac_setup.sh
#   AWS_PROFILE=your-profile ./iac_setup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGION=${AWS_REGION:-us-east-1}
POLICY_NAME="AgentCoreStarterToolkitPolicy"

echo "=================================================="
echo "Level 27: AgentCore IAM Setup (Infrastructure as Code)"
echo "=================================================="
echo ""
echo "Configuration:"
echo "  Region: $REGION"
echo "  Policy Name: $POLICY_NAME"
echo "  Policy File: $SCRIPT_DIR/iac_policy.json"
echo ""

# Verify AWS credentials
echo "Verifying AWS credentials..."
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
CALLER_ARN=$(aws sts get-caller-identity --query Arn --output text)
echo "  Account ID: $ACCOUNT_ID"
echo "  Caller ARN: $CALLER_ARN"
echo ""

# Check if policy already exists
echo "Checking for existing policy..."
EXISTING_POLICY=$(aws iam list-policies --scope Local --query "Policies[?PolicyName=='$POLICY_NAME'].Arn" --output text)

if [ -n "$EXISTING_POLICY" ]; then
    echo "  Policy already exists: $EXISTING_POLICY"
    echo "  Skipping policy creation."
else
    echo "  Creating IAM policy..."
    POLICY_ARN=$(aws iam create-policy \
        --policy-name "$POLICY_NAME" \
        --policy-document "file://$SCRIPT_DIR/iac_policy.json" \
        --description "Permissions for AgentCore starter toolkit deployment" \
        --query 'Policy.Arn' \
        --output text)
    echo "  Created: $POLICY_ARN"
fi

echo ""

# Check if BedrockAgentCoreFullAccess managed policy exists
echo "Checking for BedrockAgentCoreFullAccess managed policy..."
MANAGED_POLICY=$(aws iam list-policies --scope AWS --query "Policies[?PolicyName=='BedrockAgentCoreFullAccess'].Arn" --output text 2>/dev/null || true)

if [ -n "$MANAGED_POLICY" ]; then
    echo "  Found: $MANAGED_POLICY"
else
    echo "  Warning: BedrockAgentCoreFullAccess managed policy not found."
    echo "  This may indicate AgentCore is not yet available in your region."
fi

echo ""
echo "=================================================="
echo "Setup Complete!"
echo "=================================================="
echo ""
echo "Created resources:"
echo "  - IAM Policy: arn:aws:iam::${ACCOUNT_ID}:policy/${POLICY_NAME}"
echo ""
echo "Next steps:"
echo "  1. Install AgentCore packages:"
echo "     pip install bedrock-agentcore strands-agents bedrock-agentcore-starter-toolkit"
echo ""
echo "  2. Create and test your agent locally:"
echo "     python hello_agent.py"
echo ""
echo "  3. Deploy to AgentCore:"
echo "     agentcore configure -e your_agent.py"
echo "     agentcore launch"
echo ""
echo "To clean up, run: ./iac_teardown.sh"
echo ""
