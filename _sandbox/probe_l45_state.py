"""
L45 Probe 3: S3 Vectors live state — existing buckets, indexes, IAM identity.
"""
import boto3, json

# Who am I?
sts = boto3.client("sts", region_name="us-east-1")
print("=== IAM Identity ===")
try:
    ident = sts.get_caller_identity()
    print(f"  Account: {ident['Account']}")
    print(f"  ARN: {ident['Arn']}")
except Exception as e:
    print(f"  {e}")

# What vector buckets exist?
client = boto3.client("s3vectors", region_name="us-east-1")
print("\n=== Existing vector buckets (us-east-1) ===")
try:
    resp = client.list_vector_buckets()
    buckets = resp.get("vectorBuckets", [])
    if buckets:
        for b in buckets:
            print(f"  {b}")
    else:
        print("  (none)")
except Exception as e:
    print(f"  ERROR: {e}")

# Try other regions
for region in ["us-west-2", "eu-west-1"]:
    c = boto3.client("s3vectors", region_name=region)
    try:
        resp = c.list_vector_buckets()
        buckets = resp.get("vectorBuckets", [])
        if buckets:
            print(f"\n=== {region} buckets ===")
            for b in buckets:
                print(f"  {b}")
    except Exception as e:
        print(f"\n=== {region} === ERROR: {e}")

# What permissions do I have? Try creating a bucket (dry run via describe)
print("\n=== IAM policy check — s3vectors permissions ===")
iam = boto3.client("iam", region_name="us-east-1")
try:
    # Get role name from ARN
    arn = sts.get_caller_identity()['Arn']
    print(f"  Testing via assumed role ARN: {arn}")
except Exception as e:
    print(f"  {e}")
