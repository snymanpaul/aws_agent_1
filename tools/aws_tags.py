"""
One tag set for every AWS resource a lesson creates.

The sandbox account is shared with another team, so name prefixes alone cannot separate
this repo's resources from theirs. Every created resource carries the same four tags.

Listing what this repo has left running takes two queries (checked 2026-10-08):

    aws resourcegroupstaggingapi get-resources --region us-east-1 \
        --tag-filters Key=owner,Values=paul Key=project,Values=aws_agent_1
    aws iam list-roles --query 'Roles[].RoleName'   # then list-role-tags; IAM is not returned above

The `paul-aws-agent-1` Resource Group (us-east-1) selects on the same two tags, but it shows
only the types Resource Groups supports: it lists S3, Bedrock guardrails and log groups, and
omits AgentCore resources and IAM roles. Use the tagging API query above, not the group.

AWS APIs disagree on the shape of tags, so the helpers return each shape:
    lesson_tags(...)          {"owner": "paul", ...}             AgentCore, Bedrock, Lambda, Kinesis, S3 Vectors
    tag_list(lesson_tags())   [{"Key": "owner", "Value": ...}]   IAM, S3 bucket tagging, DynamoDB
    tag_list(t, "key", "value")  [{"key": "owner", ...}]         Step Functions
Check each operation's input shape before choosing; a wrong shape fails at call time.
"""

OWNER = "paul"
PROJECT = "aws_agent_1"


def lesson_tags(lesson: str, teardown: str) -> dict[str, str]:
    """Tags for a resource created by `lesson` (e.g. "L75") and removed by `teardown`
    (the script or command that deletes it, e.g. "18_agentcore_config/config_bundles.py finally")."""
    if not lesson or not teardown:
        raise ValueError("lesson and teardown are both required: an untagged teardown is the gap these tags close")
    return {"owner": OWNER, "project": PROJECT, "lesson": lesson, "teardown": teardown}


def tag_list(tags: dict[str, str], key: str = "Key", value: str = "Value") -> list[dict[str, str]]:
    """The same tags as a list of {key: k, value: v} pairs."""
    return [{key: k, value: v} for k, v in tags.items()]
