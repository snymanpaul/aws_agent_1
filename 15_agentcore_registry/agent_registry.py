"""
Level 71: AgentCore Agent Registry — Publish & Discover an AGENT_SKILLS Bundle
=============================================================================
AWS Bedrock AgentCore (Preview, 2026) — a private, *governed* catalog where an
agent's skills, MCP servers, and A2A agents live side by side and are discovered
by semantic search after an approval workflow.

Goal: publish a skill to the cloud registry and discover it — and see that an
approval step gates discoverability. This is the cloud-catalog counterpart to
L30's local Strands `AgentSkills` plugin: L30 loads skills in-process; L71
publishes them to a shared, governed, searchable catalog.

L30 local skills vs L71 cloud registry (the framing):
    L30 AgentSkills plugin — in-process, per-agent, no governance, no discovery.
                             You ship the skill files with the agent.
    L71 Agent Registry     — one catalog for the org. DescriptorType is one of
                             MCP / A2A / CUSTOM / AGENT_SKILLS, so skills sit
                             beside MCP servers and A2A agents. Records are
                             DRAFT until an admin APPROVES them; only APPROVED
                             records are discoverable via semantic search.

Two API surfaces:
    control plane  bedrock-agentcore-control : Create/Get/List/Update/Delete
                   Registry + RegistryRecord, Submit/UpdateStatus (governance).
    data plane     bedrock-agentcore         : SearchRegistryRecords (discovery).

Depends on: L30 (local AgentSkills), L27/L33 (AgentCore control plane)
Unlocks:    org-wide skill discovery; a governed alternative to shipping skills inline.

Iterations:
  1. Create a governed registry   — autoApproval=False; poll CREATING -> READY.
  2. Publish an AGENT_SKILLS record — a real SKILL.md (frontmatter required);
                                      poll CREATING -> DRAFT.
  3. Governance gates discovery    — search finds NOTHING while DRAFT; submit ->
                                      PENDING_APPROVAL -> approve -> APPROVED;
                                      then search finds it (eventually consistent).
  4. Teardown                      — delete record + registry (always, in finally).

Critical API facts (validated by live probe, not docs):
    * Region us-east-1 (one of the preview regions). Needs AWS creds:
        aws sso login --profile <your-admin-profile>
    * DescriptorType enum: MCP | A2A | CUSTOM | AGENT_SKILLS — ONE catalog.
    * create_registry is ASYNC (HTTP 202): status CREATING -> READY. You MUST
      poll get_registry until READY before adding records or deleting (deleting a
      CREATING registry raises ConflictException). delete_registry is async too.
    * registry_id = registryArn.split('/')[-1] (CreateRegistry returns only the ARN).
    * create_registry_record: descriptors.agentSkills.skillMd.inlineContent MUST
      be a SKILL.md with YAML '---' frontmatter, else ValidationException. With
      approvalConfiguration.autoApproval=False the record settles to DRAFT.
    * Governance: submit_registry_record_for_approval -> PENDING_APPROVAL;
      update_registry_record_status(status='APPROVED', statusReason=...) -> APPROVED.
    * SearchRegistryRecords (data plane) returns ONLY APPROVED records — DRAFT and
      PENDING are hidden. It is eventually consistent (~8-12s after approval), so
      poll. Input requires searchQuery AND registryIds.

Usage:
    AWS_PROFILE=<admin-profile> uv run python 15_agentcore_registry/agent_registry.py
"""

import sys
import time

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"
REGISTRY_NAME = "l71skillscatalog"

# A real SKILL.md — the registry validates the YAML frontmatter ('---' delimited).
SKILL_MD = (
    "---\n"
    "name: invoice-extractor\n"
    "description: Extract totals and line items from invoice PDFs.\n"
    "---\n"
    "# Invoice Extractor\n"
    "Given an invoice PDF, extract the invoice number, date, vendor, line items,\n"
    "and grand total as structured JSON.\n"
)

control = boto3.client("bedrock-agentcore-control", region_name=REGION)
data = boto3.client("bedrock-agentcore", region_name=REGION)


def reg_status(rid: str) -> str:
    return control.get_registry(registryId=rid).get("status")


def rec_status(rid: str, rec: str) -> str:
    return control.get_registry_record(registryId=rid, recordId=rec).get("status")


def wait(fn, transient=("CREATING", "UPDATING"), timeout=180):
    """Poll fn() until it returns a non-transient status (or times out)."""
    st = None
    for _ in range(timeout // 3):
        st = fn()
        if st not in transient:
            return st
        time.sleep(3)
    return f"TIMEOUT(last={st})"


def preflight() -> bool:
    """Fail fast with a helpful message if AWS creds are missing/expired."""
    try:
        ident = boto3.client("sts", region_name=REGION).get_caller_identity()
        print(f"  authenticated as {ident['Arn'].split('/')[-1]} (acct {ident['Account']})")
        return True
    except Exception as e:
        print(f"  AWS credentials unavailable: {str(e)[:90]}")
        print("  -> run:  aws sso login --profile <your-admin-profile>   then re-run with AWS_PROFILE set.")
        return False


def cleanup_same_name() -> None:
    """Delete any leftover registry with our name so the lesson is re-runnable."""
    for r in control.list_registries().get("registries", []):
        if r.get("name") != REGISTRY_NAME:
            continue
        rid = r.get("registryId") or r["registryArn"].split("/")[-1]
        try:
            if wait(lambda: reg_status(rid)) == "READY":
                for rec in control.list_registry_records(registryId=rid).get("registryRecords", []):
                    control.delete_registry_record(
                        registryId=rid, recordId=rec.get("recordId") or rec["recordArn"].split("/")[-1])
                control.delete_registry(registryId=rid)
                print(f"  cleaned up leftover registry {rid}")
        except ClientError as e:
            print(f"  cleanup note: {str(e)[:80]}")


# ---------------------------------------------------------------------------
# ITERATION 1: create a governed registry
# ---------------------------------------------------------------------------
def iteration_1_create_registry() -> str:
    print("\n" + "=" * 70)
    print("ITERATION 1: create a governed registry (CREATING -> READY)")
    print("=" * 70)
    r = control.create_registry(
        name=REGISTRY_NAME,
        description="L71 demo: org skill catalog",
        authorizerType="AWS_IAM",
        approvalConfiguration={"autoApproval": False},  # governance ON
    )
    registry_id = r["registryArn"].split("/")[-1]
    print(f"  created (async 202). registry_id={registry_id}")
    status = wait(lambda: reg_status(registry_id))
    print(f"  status -> {status}")
    assert status == "READY", f"registry should reach READY, got {status}"
    print("  OK: registry READY (DescriptorTypes it can hold: MCP / A2A / CUSTOM / AGENT_SKILLS)")
    return registry_id


# ---------------------------------------------------------------------------
# ITERATION 2: publish an AGENT_SKILLS record
# ---------------------------------------------------------------------------
def iteration_2_publish_skill(registry_id: str) -> str:
    print("\n" + "=" * 70)
    print("ITERATION 2: publish an AGENT_SKILLS record (CREATING -> DRAFT)")
    print("=" * 70)
    rec = control.create_registry_record(
        registryId=registry_id,
        name="invoice-extractor",
        description="Extract invoice fields from PDFs",
        descriptorType="AGENT_SKILLS",
        descriptors={"agentSkills": {"skillMd": {"inlineContent": SKILL_MD}}},
    )
    record_id = rec["recordArn"].split("/")[-1]
    print(f"  created record_id={record_id} initial status={rec.get('status')}")
    status = wait(lambda: rec_status(registry_id, record_id))
    print(f"  status -> {status}")
    assert status == "DRAFT", f"with autoApproval=False the record should land in DRAFT, got {status}"
    print("  OK: skill published as DRAFT (skillMd required real '---' frontmatter).")
    return record_id


# ---------------------------------------------------------------------------
# ITERATION 3: governance gates discovery
# ---------------------------------------------------------------------------
def iteration_3_governance(registry_id: str, record_id: str) -> None:
    print("\n" + "=" * 70)
    print("ITERATION 3: approval gates discovery (search hides DRAFT records)")
    print("=" * 70)
    query = "extract invoice fields"

    before = data.search_registry_records(
        searchQuery=query, registryIds=[registry_id], maxResults=5).get("registryRecords", [])
    print(f"  search while DRAFT: {[(h['name'], h['status']) for h in before]}")
    assert before == [], "a DRAFT record must NOT be discoverable"

    control.submit_registry_record_for_approval(registryId=registry_id, recordId=record_id)
    print(f"  submitted -> {wait(lambda: rec_status(registry_id, record_id))}")
    control.update_registry_record_status(
        registryId=registry_id, recordId=record_id, status="APPROVED", statusReason="meets schema")
    print(f"  approved  -> {wait(lambda: rec_status(registry_id, record_id))}")

    # Search is eventually consistent after approval — poll.
    hits = []
    for attempt in range(6):
        hits = data.search_registry_records(
            searchQuery=query, registryIds=[registry_id], maxResults=5).get("registryRecords", [])
        if hits:
            print(f"  search after APPROVED (attempt {attempt}): "
                  f"{[(h['name'], h['status']) for h in hits]}")
            break
        time.sleep(4)
    assert hits and hits[0]["status"] == "APPROVED", "approved record should become discoverable"
    print("  OK: the SAME query that found nothing now returns the APPROVED skill — approval gated it.")


# ---------------------------------------------------------------------------
# ITERATION 4: teardown (handled by main's finally)
# ---------------------------------------------------------------------------
def teardown(registry_id, record_id) -> None:
    print("\n" + "=" * 70)
    print("ITERATION 4: teardown (delete record + registry — leave nothing behind)")
    print("=" * 70)
    if record_id:
        try:
            control.delete_registry_record(registryId=registry_id, recordId=record_id)
            print("  deleted record")
        except ClientError as e:
            print(f"  delete record note: {str(e)[:80]}")
    if registry_id:
        try:
            wait(lambda: reg_status(registry_id))  # must be READY, not CREATING/UPDATING
            control.delete_registry(registryId=registry_id)
            print("  deleted registry (delete is async; it finishes in the background)")
        except ClientError as e:
            print(f"  delete registry note: {str(e)[:80]}")


def summary() -> None:
    print("\n" + "=" * 70)
    print("L71 COMPLETE — Key Takeaways")
    print("=" * 70)
    print("""
1. What the Agent Registry is
   A private, governed catalog. One record can describe an MCP server, an A2A
   agent, a CUSTOM resource, or an AGENT_SKILLS bundle — skills live in the SAME
   catalog as the rest of your agent infrastructure.

2. Async, governed lifecycle
   Registry: CREATING -> READY (poll). Record (autoApproval=False): CREATING ->
   DRAFT -> (submit) PENDING_APPROVAL -> (approve) APPROVED.

3. Approval gates discovery (the point)
   SearchRegistryRecords returns ONLY APPROVED records. The same query finds
   nothing while the record is DRAFT and finds it once approved — governance is
   enforced at discovery, not just labelled.

4. Real SKILL.md, eventual consistency
   skillMd.inlineContent must be a '---'-frontmatter SKILL.md. Search is
   eventually consistent (~8-12s post-approval) — poll, don't assume.

5. vs L30 local AgentSkills
   L30 = skills loaded in-process per agent (no governance, no discovery).
   L71 = skills published to a shared catalog, approved, and discovered org-wide.
   Use L30 to run a skill; use L71 to PUBLISH and GOVERN one.
""")


def main() -> None:
    print("AgentCore Agent Registry — L71")
    if not preflight():
        sys.exit(1)
    cleanup_same_name()

    registry_id = record_id = None
    try:
        registry_id = iteration_1_create_registry()
        record_id = iteration_2_publish_skill(registry_id)
        iteration_3_governance(registry_id, record_id)
    finally:
        teardown(registry_id, record_id)
    summary()


if __name__ == "__main__":
    main()
