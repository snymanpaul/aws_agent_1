"""
L45 Probe 1: S3 Vectors API shapes — enumerate all operation input/output shapes.
"""
import boto3, json

client = boto3.client("s3vectors", region_name="us-east-1")
sm = client._service_model

ops = [
    "CreateVectorBucket", "DeleteVectorBucket", "GetVectorBucket", "ListVectorBuckets",
    "CreateIndex", "DeleteIndex", "GetIndex", "ListIndexes",
    "PutVectors", "GetVectors", "DeleteVectors", "QueryVectors", "ListVectors",
]

for op in ops:
    try:
        shape = sm.operation_model(op)
        inp = shape.input_shape
        out = shape.output_shape
        print(f"\n=== {op} ===")
        if inp:
            members = inp.members if hasattr(inp, 'members') else {}
            required = inp.metadata.get('required', []) if hasattr(inp, 'metadata') else []
            print(f"  INPUT  required={required}")
            for k, v in members.items():
                print(f"    {k}: {v.type_name}")
        else:
            print("  INPUT: none")
        if out:
            members = out.members if hasattr(out, 'members') else {}
            print(f"  OUTPUT fields: {list(members.keys())}")
    except Exception as e:
        print(f"\n=== {op} === ERROR: {e}")
