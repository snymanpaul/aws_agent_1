import json, os
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "learnings", "observations.jsonl")
L68 = {"invocation-limits-verified"}
L69 = {"payments-x402-plugin", "payments-pricing-is-wallet-ops-only", "payment-manager-provisioning"}
out, changed, skipped = [], 0, 0
for ln in open(LOG, encoding="utf-8").read().splitlines():
    if not ln.strip():
        out.append(ln); continue
    try:
        d = json.loads(ln)
    except json.JSONDecodeError:
        out.append(ln); skipped += 1; continue   # keep malformed pre-existing lines verbatim
    if d.get("topic") in L68 and d.get("level") == 64:
        d["level"] = 68; changed += 1
    elif d.get("topic") in L69 and d.get("level") == 67:
        d["level"] = 69; changed += 1
    out.append(json.dumps(d))
open(LOG, "w", encoding="utf-8").write("\n".join(out) + "\n")
print(f"renumbered {changed} lesson obs; kept {skipped} unparseable line(s) verbatim")
