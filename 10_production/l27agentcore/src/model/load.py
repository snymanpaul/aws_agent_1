import os
from strands.models import BedrockModel

# Model configuration
# Use Amazon Nova models - accessible to ALL AWS account types including channel program accounts
# Third-party models (Claude, Llama) may require special access for some account types
#
# Available Amazon Nova models:
#   - amazon.nova-lite-v1:0   - Fast, cost-effective (for development/testing)
#   - amazon.nova-pro-v1:0    - Balanced performance (for production)
#   - amazon.nova-premier-v1:0 - Highest capability
#   - amazon.nova-micro-v1:0  - Fastest, lowest cost
#
# Note: This account is a "channel program account" which cannot directly invoke
# Anthropic Claude models. Amazon Nova models work for all AWS account types.

MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")


def load_model() -> BedrockModel:
    """
    Get Bedrock model client using Amazon Nova.

    Uses IAM authentication via the execution role.
    Configured via BEDROCK_MODEL_ID environment variable.
    Defaults to Nova Lite for development.
    """
    return BedrockModel(model_id=MODEL_ID)