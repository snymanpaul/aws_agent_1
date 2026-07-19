"""
Probe: enumerate ALL operations on bedrock-agentcore + bedrock-agentcore-control
to see which 2026-Q2 features are programmatically exposed in boto3 1.42.70.

Looks specifically for:
- managed harness         (April preview)
- filesystem persistence  (April preview)
- AG-UI native runtime    (March GA)
- memory streaming / episodic / branching   (Feb-Mar GA)
- performance optimization recommendations (May preview)
- browser OS-level + profiles  (Feb-Apr GA)

Run:  uv run python _sandbox/probe_2026_05_agentcore_ops.py
"""

import boto3
import os

# Set AWS_PROFILE (your SSO profile) in the environment before running.
os.environ.setdefault("AWS_DEFAULT_REGION", "us-west-2")

KEYWORDS = [
    "harness", "filesystem", "persist", "suspend", "resume",
    "agui", "ag_ui", "ag-ui", "interrupt",
    "episodic", "branch", "stream", "notif",
    "optim", "recommend", "evaluation", "abtest", "ab_test", "a_b_test",
    "browser", "profile", "os_action", "screenshot",
    "memory", "skill",
]

def probe(service_name: str) -> dict:
    s = boto3.Session()
    try:
        client = s.client(service_name)
        sm = client.meta.service_model
        operations = sm.operation_names
    except Exception as e:
        return {"service": service_name, "error": str(e)}

    matched = {}
    for k in KEYWORDS:
        hits = [op for op in operations if k.replace('-', '').replace('_','') in op.replace('_','').lower()]
        if hits:
            matched[k] = sorted(set(hits))

    return {
        "service": service_name,
        "total_operations": len(operations),
        "operations": sorted(operations),
        "matches": matched,
    }


for svc in ["bedrock-agentcore", "bedrock-agentcore-control"]:
    print("=" * 70)
    print(f"SERVICE: {svc}")
    print("=" * 70)
    result = probe(svc)
    if "error" in result:
        print(f"ERROR: {result['error']}")
        continue
    print(f"Total operations: {result['total_operations']}")
    print(f"\nKeyword matches (features we want to find):")
    if not result["matches"]:
        print("  (no matches for any of the target keywords)")
    for kw, ops in result["matches"].items():
        print(f"  {kw:18s} -> {ops}")
    print(f"\nALL OPERATIONS:")
    for i, op in enumerate(result["operations"]):
        print(f"  {op}")
