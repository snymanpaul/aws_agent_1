"""
Level 80 (+ Foundation F1): AgentCore Memory with a real LTM strategy + filtered retrieval
========================================================================================
Closes the audit's marquee memory gap: L66 could only verify the filter API SHAPE because
its reused store was STM-only ("extraction-gated"). This PROVISIONS a Memory with a real
semantic (LTM extraction) strategy, writes cohort-tagged events, waits for extraction, and
proves namespace-FILTERED retrieval actually discriminates between cohorts.

Anti-simulation design (no fakes/stubs):
  - A LIVE AgentCore Memory is created with a real semanticMemoryStrategy (self-cleaned).
  - Cohort facts are distinctive (US: USD/Texas; EU: EUR/Ireland); extraction is real and
    ASYNC -- we poll retrieve_memories until records appear or time out (no faked records).
  - Discrimination is the proof: the US namespace returns US facts and NOT EU facts (and
    vice-versa). A no-op or STM-only store cannot produce this.
  - Negative control: a non-existent cohort namespace returns nothing.
  - If extraction never lands (e.g., needs an execution role), the test FAILS honestly --
    that is a real finding, not a simulated pass.

Run (needs AWS creds + region; runs several minutes for async extraction):
  AWS_PROFILE=... AWS_REGION=us-east-1 uv run python 14_agentcore_platform/ltm_filtered_retrieval.py
"""

import os
import time
import uuid

from bedrock_agentcore.memory import MemoryClient

REGION = os.environ.get("AWS_REGION", "us-east-1")
# MemoryClient.create_event expects (text, role) tuples (role in USER/ASSISTANT/TOOL/OTHER).
US = [("Our US cohort pays in USD and ships from Texas warehouses.", "USER"),
      ("Recorded: the US cohort uses USD and ships from Texas.", "ASSISTANT")]
EU = [("Our EU cohort pays in EUR, is GDPR-bound, and ships from Ireland.", "USER"),
      ("Recorded: the EU cohort uses EUR, is GDPR-bound, ships from Ireland.", "ASSISTANT")]


def _mem_id(resp):
    return resp.get("id") or resp.get("memoryId") or resp.get("memory", {}).get("id")


def _text(records):
    return " ".join(str(r) for r in records).lower()


def verify():
    client = MemoryClient(region_name=REGION)
    suffix = uuid.uuid4().hex[:8]
    resp = client.create_memory_and_wait(
        name=f"adk_l80_ltm_{suffix}",
        strategies=[{"semanticMemoryStrategy": {"name": "cohort_facts",
                                                "namespaces": ["/facts/{actorId}"]}}],
        event_expiry_days=7, max_wait=300, poll_interval=10)
    memory_id = _mem_id(resp)
    print(f"[L80] created memory {memory_id} with a semantic LTM strategy")
    try:
        client.create_event(memory_id, actor_id="cohort_us", session_id="s_us", messages=US)
        client.create_event(memory_id, actor_id="cohort_eu", session_id="s_eu", messages=EU)
        print("[L80] wrote cohort-tagged events; polling for async extraction...")

        us = eu = []
        for attempt in range(20):  # up to ~5 min for extraction to land
            us = client.retrieve_memories(memory_id, namespace="/facts/cohort_us",
                                          query="currency and shipping", top_k=5)
            eu = client.retrieve_memories(memory_id, namespace="/facts/cohort_eu",
                                          query="currency and shipping", top_k=5)
            print(f"  attempt {attempt+1}: us_records={len(us)} eu_records={len(eu)}")
            if us and eu:
                break
            time.sleep(15)

        none_ns = client.retrieve_memories(memory_id, namespace="/facts/cohort_none",
                                           query="currency", top_k=5)
        ut, et = _text(us), _text(eu)
        print(f"[L80] US namespace text: {ut[:120]!r}")
        print(f"[L80] EU namespace text: {et[:120]!r}")

        checks = {
            "extraction landed: US namespace has LTM records": len(us) > 0,
            "extraction landed: EU namespace has LTM records": len(eu) > 0,
            "US facts present in US namespace (USD/Texas)": ("usd" in ut or "texas" in ut),
            "EU facts present in EU namespace (EUR/Ireland)": ("eur" in et or "ireland" in et),
            "FILTER discriminates: US namespace excludes EU facts": ("eur" not in ut and "ireland" not in ut),
            "FILTER discriminates: EU namespace excludes US facts": ("usd" not in et and "texas" not in et),
            "negative control: unknown cohort namespace is empty": len(none_ns) == 0,
        }
        for k, v in checks.items():
            print(f"  {'PASS' if v else 'FAIL'}  {k}")
        assert all(checks.values()), "L80 FAILED"
        print("[L80] PASS — real LTM extraction + namespace-filtered retrieval discriminates by cohort")
    finally:
        client.delete_memory(memory_id)
        print(f"[L80] cleanup: deleted memory {memory_id}")


if __name__ == "__main__":
    verify()
