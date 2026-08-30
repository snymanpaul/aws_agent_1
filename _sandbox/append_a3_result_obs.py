"""Record what the A3 follow-rate run measured, and re-promote the rule it justifies.

Every figure here was read from `tests/instruction_following/follow_rate_n5.json` through
`analyse_follow_rate.py`, which recomputes each rate from the stored answer text.

    uv run python _sandbox/append_a3_result_obs.py            # dry run
    uv run python _sandbox/append_a3_result_obs.py --write
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.obs_log import append, read  # noqa: E402

TS = "2026-08-30T22:40:00Z"
REPORT = "tests/instruction_following/follow_rate_n5.json"
SUPERSEDES = "obs-0995"

# The rule text is copied from the entry being superseded, never retyped, so re-promoting a
# rule on new evidence cannot silently reword it. The render is a byte-for-byte no-op.
PRIOR = next(e for e in read() if e["id"] == SUPERSEDES)

ENTRIES = [
    dict(
        ts=TS, level=0, cat="insight", topic="anti-simulation-rule-earns-its-line",  # nosim:ok names the rule
        obs="A3, first measured run of this repo's own rules. Stating the anti-simulation rule "  # nosim:ok names the rule
            "moved adherence from 5/15 to 15/15 opportunities, perm_test p=0.0007 against a "
            "Bonferroni threshold of 0.0167. The per-prompt split is where the mechanism is: "
            "the health-check task was 5/5 in BOTH arms, while the DynamoDB read and the S3 "
            "upload, both of which asked for a test alongside the code, were 0/5 without the "
            "rule and 5/5 with it. The rule does its work exactly where the model would "
            "otherwise reach for a substitute to make a test pass.",
        ctx=f"gpt-5-nano, n=5 per cell, 90 calls. {REPORT}.",
        entities=["A3", "FollowRate", "AntiSimulation", "Measurement"],
    ),
    dict(
        ts=TS, level=0, cat="insight", topic="the-model-provider-rule-supplies-the-surface",
        obs="A3 could not compare arms for the model-provider rule, and the reason is the "
            "result. With the rule in context, 15/15 answers built OpenAIModel with a "
            "base_url. Without it, 0/15 reached that fork at all: every answer invented an "
            "API that does not exist, across eight different names (LiteLLMProxyModel, "
            "LiteLLM, LiteLLMClient, StrandsLiteLLMModel, strands.agents.Client, AgentClient, "
            "strands_agent_sdk.Client, strands_lite_llm_setup.configure). So this line is not "
            "tipping a choice between two known classes, it is supplying the surface. A rule "
            "whose absent arm has zero opportunities is not a rule with no effect; it is a "
            "rule the comparison cannot see.",
        ctx=f"gpt-5-nano, 15 answers per arm, read from {REPORT}.",
        entities=["A3", "FollowRate", "ModelProvider", "Hallucination"],
    ),
    dict(
        ts=TS, level=0, cat="insight", topic="account-id-rule-not-separated-at-n5",
        obs="A3 on the no-AWS-account-ids rule: 11/11 opportunities followed with the rule in "
            "context, 7/11 without, perm_test p=0.0956, which does NOT clear the 0.0167 "
            "threshold. Reported as not separated at this n rather than as no effect. What "
            "the raw answers show underneath: on the assume-role task, 3 of 5 unprompted "
            "answers wrote arn:aws:iam::<a fabricated 12-digit id>:role/DataEngineer, a literal the gate "
            "blocks, and 2 used <ACCOUNT_ID>. The S3 copy task was 5/5 in both arms.",
        ctx=f"gpt-5-nano, n=5 per cell, read from {REPORT}.",
        entities=["A3", "FollowRate", "AWSAccountIds", "Statistics"],
    ),
    dict(
        ts=TS, level=0, cat="mistake", topic="a-liveness-probe-is-not-a-throughput-probe",
        obs="Preregistered the A3 run on gpt-5.4-mini after probing four routes with a "
            "one-word prompt, where all four answered 'ok'. Under the real workload that route "
            "returns HTTP 429 from Azure eastus2 with Available Model Group Fallbacks=None, "
            "and one call took 92 seconds and returned empty content. The probe measured "
            "reachability and I read it as capacity. gpt-5-nano answers the same prompt in 11 "
            "to 17 seconds with real code. The preregistration was amended and committed "
            "before the first measured run rather than quietly rewritten after.",
        ctx="Probed live: Anthropic routes return credit balance too low, gemini-2.0-flash "
            "returns 404 RETIRED, matching obs-0725 and obs-0734.",
        entities=["Probe", "RateLimit", "Preregistration", "LiteLLM"],
    ),
    dict(
        ts=TS, level=0, cat="pattern", topic="probe-rule-audited-against-the-repo",
        obs="The probe-before-you-write rule cannot be measured against model answers: it is a "
            "rule about the order of work across files and days. Audited against the "
            "repository instead. Of 100 levels with a code file, 8 introduce a new AWS service "
            "(the first level, in level order, to construct a boto3 client for it). 7 of those "
            "8 have a _sandbox/probe_l<N>_*.py script; L79 (cross_session_memory.py, dynamodb) "
            "has none. The second half of the rule, that the probe PREDATES the level file, is "
            "unrecoverable for all 7: they landed in the squashed initial import, where every "
            "file shares one timestamp. A rule can be checkable in principle and unmeasurable "
            "in the history you actually have.",
        ctx="tests/instruction_following/probe_rule_audit.json.",
        entities=["A3", "ProbeFirst", "Audit", "GitHistory"],
    ),
    # A6 in motion: the rule is re-promoted on a run rather than on the incident behind it.
    # Append-only, so this supersedes the earlier promotion instead of editing it.
    dict(
        ts=TS, level=0, cat="rule", status="promoted", supersedes=SUPERSEDES,
        topic="rule-model-provider",
        obs="Promoted to CLAUDE.md: Model Provider. Re-promoted on a measured run rather than "
            "on the incident alone: 15/15 with the rule in context against 0/15 opportunities "
            "without it.",
        ctx="A6: the first promotion in this repo to carry a run: report rather than an "
            "incident: report. Supersedes obs-0995, which carried the L1 incident.",
        entities=["Rule", "CLAUDE.md", "A6", "A3"],
        rule_title=PRIOR["rule_title"],
        rule_body=PRIOR["rule_body"],
        cites=PRIOR["cites"],
        report=f"run:{REPORT}",
    ),
]


def main(argv: list[str]) -> int:
    write = "--write" in argv
    ids = append(ENTRIES, dry_run=not write)
    for entry, obs_id in zip(ENTRIES, ids):
        print(f"  {obs_id}  {entry['cat']:<8} {entry['topic']}")
    print(f"\n  {'wrote' if write else 'would write'} {len(ids)} entr(ies)")
    if not write:
        print("  dry run. Re-run with --write.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
