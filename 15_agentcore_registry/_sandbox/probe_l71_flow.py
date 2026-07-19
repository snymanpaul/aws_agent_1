"""Probe the real AgentCore Registry governance+search lifecycle (with teardown).
Discovers: registry status lifecycle, record status flow with autoApproval=False,
whether search only returns APPROVED records, and consistency timing."""
import boto3, json, time

REGION = "us-east-1"
c = boto3.client("bedrock-agentcore-control", region_name=REGION)
dp = boto3.client("bedrock-agentcore", region_name=REGION)


def j(x):
    return json.dumps(x, default=str)


def reg_status(rid):
    return c.get_registry(registryId=rid).get("status")


def rec_status(rid, rec):
    return c.get_registry_record(registryId=rid, recordId=rec).get("status")


def wait(fn, want_not=("CREATING", "UPDATING"), timeout=180, label=""):
    for _ in range(timeout // 3):
        st = fn()
        if st not in want_not:
            return st
        time.sleep(3)
    return f"TIMEOUT(last={st})"


SKILL_MD = (
    "---\n"
    "name: invoice-extractor\n"
    "description: Extract totals and line items from invoice PDFs.\n"
    "---\n"
    "# Invoice Extractor\n"
    "Extract the invoice number, date, vendor, line items, and grand total.\n"
)


def cleanup_existing():
    """Delete any leftover l71demoregistry registries (poll to deletable first)."""
    for r in c.list_registries().get("registries", []):
        if r.get("name") == "l71demoregistry":
            rid = r.get("registryId") or r.get("registryArn", "").split("/")[-1]
            print(f"[cleanup] found leftover {rid} status={r.get('status')}")
            try:
                # delete any records first
                for rec in c.list_registry_records(registryId=rid).get("registryRecords", []):
                    recid = rec.get("recordId") or rec.get("recordArn", "").split("/")[-1]
                    c.delete_registry_record(registryId=rid, recordId=recid)
                    print(f"[cleanup] deleted record {recid}")
                st = wait(lambda: reg_status(rid), label="cleanup-reg")
                print(f"[cleanup] registry now {st}; deleting")
                c.delete_registry(registryId=rid)
            except Exception as e:
                print("[cleanup] err:", type(e).__name__, str(e)[:160])


def main():
    cleanup_existing()
    registry_id = record_id = None
    try:
        r = c.create_registry(name="l71demoregistry", description="L71 demo skills catalog",
                              authorizerType="AWS_IAM", approvalConfiguration={"autoApproval": False})
        registry_id = r["registryArn"].split("/")[-1]
        print("created registry:", registry_id)
        print("registry status ->", wait(lambda: reg_status(registry_id), label="reg"))

        rec = c.create_registry_record(registryId=registry_id, name="invoice-extractor",
                description="Extract invoice fields", descriptorType="AGENT_SKILLS",
                descriptors={"agentSkills": {"skillMd": {"inlineContent": SKILL_MD}}})
        record_id = rec["recordArn"].split("/")[-1]
        print("created record:", record_id, "| initial status:", rec.get("status"))
        print("record status ->", wait(lambda: rec_status(registry_id, record_id), label="rec"))

        # search BEFORE approval (governance: should it be hidden?)
        s0 = dp.search_registry_records(searchQuery="extract invoice fields",
                                        registryIds=[registry_id], maxResults=5)
        print("search BEFORE approval:", [(h["name"], h["status"]) for h in s0.get("registryRecords", [])])

        # governance: submit -> approve
        try:
            c.submit_registry_record_for_approval(registryId=registry_id, recordId=record_id)
            print("submitted; status ->", wait(lambda: rec_status(registry_id, record_id)))
        except Exception as e:
            print("submit err:", type(e).__name__, str(e)[:160])
        c.update_registry_record_status(registryId=registry_id, recordId=record_id,
                                        status="APPROVED", statusReason="meets schema")
        print("approved; status ->", wait(lambda: rec_status(registry_id, record_id)))

        # search AFTER approval (poll for consistency)
        for attempt in range(5):
            s1 = dp.search_registry_records(searchQuery="extract invoice fields",
                                            registryIds=[registry_id], maxResults=5)
            hits = s1.get("registryRecords", [])
            print(f"search AFTER approval attempt {attempt}: {[(h['name'], h['status']) for h in hits]}")
            if hits:
                break
            time.sleep(4)
    finally:
        if record_id:
            try:
                c.delete_registry_record(registryId=registry_id, recordId=record_id)
                print("teardown: deleted record")
            except Exception as e:
                print("teardown record err:", str(e)[:120])
        if registry_id:
            try:
                st = wait(lambda: reg_status(registry_id), label="teardown-reg")
                c.delete_registry(registryId=registry_id)
                print(f"teardown: deleted registry (was {st})")
            except Exception as e:
                print("teardown registry err:", str(e)[:120])


if __name__ == "__main__":
    main()
