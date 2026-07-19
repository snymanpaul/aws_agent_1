import os
import boto3, botocore, importlib.metadata as md
print("botocore:", botocore.__version__)
print("boto3:", boto3.__version__)
s = boto3.Session(profile_name=os.environ.get("AWS_PROFILE"), region_name="us-east-1")
c = s.client("bedrock-agentcore-control")
print("has create_dataset method:", hasattr(c, "create_dataset"))
print("has create_evaluator method:", hasattr(c, "create_evaluator"))
# does bedrock_agentcore bundle its own botocore data model?
import bedrock_agentcore, glob
base = os.path.dirname(bedrock_agentcore.__file__)
models = glob.glob(os.path.join(base, "**", "*.json"), recursive=True)
print("bundled json models in bedrock_agentcore:", [os.path.relpath(m, base) for m in models][:10])
