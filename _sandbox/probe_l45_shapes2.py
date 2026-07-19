"""
L45 Probe 2: S3 Vectors nested shapes — vector item, queryVector, enums.
"""
import boto3, json

client = boto3.client("s3vectors", region_name="us-east-1")
sm = client._service_model

def dump_shape(shape, indent=0):
    prefix = "  " * indent
    if shape is None:
        print(f"{prefix}None")
        return
    print(f"{prefix}type={shape.type_name}, name={shape.name}")
    if shape.type_name == "structure":
        required = shape.metadata.get('required', []) if hasattr(shape, 'metadata') else []
        for k, v in shape.members.items():
            req = "*" if k in required else " "
            print(f"{prefix}  {req} {k}: {v.type_name}")
            if v.type_name in ("structure", "list", "map"):
                dump_shape(v, indent + 2)
    elif shape.type_name == "list":
        print(f"{prefix}  items:")
        dump_shape(shape.member, indent + 2)
    elif shape.type_name == "string" and hasattr(shape, 'enum'):
        print(f"{prefix}  enum={shape.enum}")

print("=== PutVectors — vector item shape ===")
op = sm.operation_model("PutVectors")
vec_list = op.input_shape.members["vectors"]
dump_shape(vec_list)

print("\n=== QueryVectors — queryVector shape ===")
op2 = sm.operation_model("QueryVectors")
qv = op2.input_shape.members["queryVector"]
dump_shape(qv)

print("\n=== CreateIndex — dataType enum ===")
op3 = sm.operation_model("CreateIndex")
dt = op3.input_shape.members["dataType"]
dump_shape(dt)

print("\n=== CreateIndex — distanceMetric enum ===")
dm = op3.input_shape.members["distanceMetric"]
dump_shape(dm)

print("\n=== CreateIndex — metadataConfiguration shape ===")
mc = op3.input_shape.members["metadataConfiguration"]
dump_shape(mc)

print("\n=== GetIndex — index output shape ===")
op4 = sm.operation_model("GetIndex")
idx = op4.output_shape.members["index"]
dump_shape(idx)
