"""Append the 2026-08-26 session observations to the append-only log.

A named script rather than an inline one-liner, so the append is reviewable and
re-runnable, and so the entries themselves are diffable before they land.

Session: corrected the AgentCore Gateway finding in the coverage assessment (twice),
then split data-plane work into ~/Code/aws_data_engineering and built its L01.
"""

import json
import pathlib

LOG = pathlib.Path(__file__).resolve().parent.parent / ".claude/learnings/observations.jsonl"
TS = "2026-08-26T22:45:00Z"

ENTRIES = [
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="mistake",
        topic="pathspec-is-itself-a-claim",
        obs="The coverage assessment asserted 'AgentCore Gateway: never built against'. FALSE. "
            "10_production/l27agentcore/cdk/lib/stacks/agentcore-stack.ts:76 creates a CfnGateway "
            "(MCP, CUSTOM_JWT) and :94 a CfnGatewayTarget onto a Lambda with an inline toolSchema. "
            "Root cause: the absence search used `git grep -ril <term> -- '*.md' '*.py' '*.json' "
            "'*.yaml' '*.toml'`, which omits '*.ts', and the repo tracks 8 TypeScript files holding "
            "the CDK infra. FIX: prove absence with NO pathspec, or enumerate tracked extensions "
            "first (`git ls-files | sed 's/.*\\.//' | sort | uniq -c | sort -rn`). A pathspec is "
            "itself an unstated claim about where the answer could live.",
        ctx="Revising docs/assessment-aws-agent-1-cross-reference.md; 278 py / 224 md / 8 ts tracked.",
        entities=["Evidence", "AbsenceProof", "git-grep", "AgentCore", "Gateway", "CDK"],
    ),
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="mistake",
        topic="corrected-a-wrong-claim-with-an-overclaim",
        obs="Having disproved 'Gateway never built', I wrote 'a real Strands agent calling real tools "
            "through a real Gateway with JWT auth'. Also unsupported: that asserts RUNTIME behaviour "
            "from IaC bytes. Counter-evidence found afterwards in level-33-reflection.md:61: 'the "
            "gateway has no registered tool schema, so NL2Cedar has nothing to map onto'. Searched "
            "observations.jsonl + 97 reflections + docs/levels/ and found NO record of a completed "
            "MCP call through the Gateway. Correct statement: wired in code, stack deployed "
            "(observations.jsonl:815 names l27agentcore-AgentCoreStack), never demonstrated end to "
            "end. LESSON: when correcting a wrong negative, the replacement claim needs its own "
            "evidence tier; 'declared in IaC' and 'observed at runtime' are different claims.",
        ctx="Two-step correction of the same finding inside one session.",
        entities=["Evidence", "Overclaim", "Gateway", "L27", "L33", "IaC"],
    ),
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="insight",
        topic="the-repo-has-an-unproven-integration-on-its-own-gateway",
        obs="aws_agent_1's central standard is that nothing is claimed without a run behind it, yet "
            "its own AgentCore Gateway has a Lambda target serving placeholder_tool (a no-op echoing "
            "its arguments) and no evidence any call ever landed. The anti-simulation gate does not "
            "catch this: no_sim_check scans *.py and the Gateway is declared in *.ts, and the "
            "placeholder returns real echoed event args rather than a fabricated success. GAP: the "
            "gate's file-type scope is narrower than the repo's language surface.",
        ctx="no_sim_check reports 0 hits over 277 py files; the CDK stack is never scanned.",
        entities=["no_sim_check", "AntiSimulation", "Gateway", "Gap", "TypeScript"],
    ),
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="pattern",
        topic="three-way-split-control-plane-data-plane-package",
        obs="Decided not to extend aws_agent_1 to the data plane. Evidence for the split: 0 tracked "
            "Python mentions Athena/Glue/Redshift/S3 Tables/Iceberg/Lake Formation; CI is declared "
            "free-and-deterministic in .github/workflows/gates.yml while data lessons meter on bytes "
            "scanned; 33 runtime deps are all agent-SDK-shaped. Split three ways, not two: agent-side "
            "work stays here, data-plane goes to ~/Code/aws_data_engineering, and anything both need "
            "(e.g. a bytes-scanned cost gate) goes into packages/agent-build-gates. The third leg "
            "already existing is what made the split cheap.",
        ctx="docs/assessment-aws-agent-1-cross-reference.md section 6 + NEXT_STEPS_PLAN tier 23.",
        entities=["Architecture", "RepoSplit", "agent-build-gates", "DataPlane"],
    ),
    dict(
        ts=TS, repo="aws_agent_1", level=0, cat="insight",
        topic="extracted-package-claim-tested-over-the-network",
        obs="README claimed agent-build-gates is 'installable into other projects'; that had only "
            "been proven from a local wheel. Now tested properly: a fresh repo declared "
            "`agent-build-gates = { git = 'https://github.com/snymanpaul/aws_agent_1', subdirectory "
            "= 'packages/agent-build-gates' }`, uv sync resolved it, and both console scripts ran "
            "(no-sim-check, check-no-aws-ids). It is NOT on PyPI (pypi.org/pypi/agent-build-gates/json "
            "returns 404), so `pip install agent-build-gates` as written in CLAUDE.md is currently "
            "wrong and should say the git source until it is published.",
        ctx="Bootstrapping ~/Code/aws_data_engineering; uv 0.8.22.",
        entities=["agent-build-gates", "Packaging", "uv", "PyPI", "DocDrift"],
    ),
]


def main() -> None:
    existing = LOG.read_text().splitlines()
    print(f"before: {len(existing)} entries, last ts {json.loads(existing[-1])['ts']}")
    with LOG.open("a") as fh:
        for e in ENTRIES:
            fh.write(json.dumps(e) + "\n")
    after = LOG.read_text().splitlines()
    print(f"after:  {len(after)} entries (+{len(after) - len(existing)})")
    for line in after[-len(ENTRIES):]:
        rec = json.loads(line)
        print(f"  {rec['cat']:8} {rec['topic']}")


if __name__ == "__main__":
    main()
