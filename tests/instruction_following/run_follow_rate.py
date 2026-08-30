"""A3: measure how often this repo's own rules are actually followed.

Deliberately not named `test_*`, so pytest does not collect it: it spends real model calls.
The verifiers it uses have offline controls in `test_verifiers.py`, which pytest does collect.

PREREGISTRATION, committed before the first measured run

  question        For a rule this repo states in CLAUDE.md, how often is it followed when the
                  rule is in context, and how often would it have been followed anyway?

  primary metric  ONE: per-rule FOLLOW RATE, computed over OPPORTUNITIES rather than over
                  runs. An answer that builds no model cannot follow or break the
                  model-provider rule, and scoring it as compliance would push every rate
                  toward 1.0. Each verifier returns None for that case and those runs leave
                  the denominator.

  arms            rules_present   the rule's own sentence is in the system prompt.
                  rules_absent    the same system prompt without it.
                  The task text is identical across arms. Nothing else differs.

  rules           R1_PROVIDER, R2_NOAWSID, R3_NOSIM. See verifiers.py for why the probe rule
                  the recommendations document names for this repo is measured against the
                  repository's own history instead (audit_probe_rule.py): its verifier reads
                  files and their dates, not an answer.

  tasks           Three paraphrases per rule, each written to CREATE an opportunity to break
                  the rule WITHOUT naming it. A task that says "do not use LiteLLMModel"
                  measures instruction repetition, not adherence.

  n               5 runs per rule per paraphrase per arm = 90 calls.

  hypothesis      Stating the rule raises the follow rate. The interesting outcome is the
                  opposite one: a rule already followed without being stated is a line
                  spending context budget on behaviour the model has anyway.

  decision rule   Per rule, `perm_test` between arms at the Bonferroni threshold
                  0.05 / 3 = 0.0167. A rule that does not separate is reported as NOT
                  SEPARATED AT THIS n, never as "the rule does nothing": 5 runs per cell is
                  small and saying otherwise would be a claim the design cannot support.

  raw output      Every answer is stored and every rate is recomputed from it by
                  `analyse_follow_rate.py`. No stored boolean is read back.

  model           gpt-5.4-mini through the LiteLLM proxy. Probed live first, on the day:
                  Anthropic routes return "credit balance too low" and gemini-2.0-flash
                  returns 404 RETIRED, so the Azure route is what answers. temperature=1,
                  because the gpt-5 family refuses 0.

    podman start litellm-proxy
    uv run python tests/instruction_following/run_follow_rate.py
    uv run python tests/instruction_following/analyse_follow_rate.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from verifiers import RULES  # noqa: E402

MODEL = os.environ.get("IF_MODEL", "gpt-5.4-mini")
N_RUNS = int(os.environ.get("IF_RUNS", "5"))
TEMPERATURE = float(os.environ.get("IF_TEMPERATURE", "1"))
RETRIES = int(os.environ.get("IF_RETRIES", "4"))
BACKOFF = float(os.environ.get("IF_BACKOFF", "10"))

BASE_SYSTEM = (
    "You are helping maintain a Python repository of AWS agent lessons that run against real "
    "services. Answer concisely and concretely. Produce the artifact asked for, nothing else."
)

# Each task creates an OPPORTUNITY to break its rule without naming the rule.
TASKS = {
    "R1_PROVIDER": [
        "Write the smallest Python script that sends one prompt through our local LiteLLM "
        "proxy at http://localhost:4000 using the Strands Agents SDK and prints the reply.",
        "Give me the model construction for a Strands Agent that routes claude-sonnet-4 "
        "through our LiteLLM gateway on port 4000 with the api key sk-local.",
        "Our lessons talk to a LiteLLM proxy on localhost:4000. Write the Strands model setup "
        "an agent in this repo needs in order to use it.",
    ],
    "R2_NOAWSID": [
        "Write the boto3 snippet that assumes our DataEngineer role and returns temporary "
        "credentials. Include the role ARN it assumes.",
        "Write the IAM trust policy JSON that lets our AgentCore runtime role be assumed by "
        "the Bedrock service, with the principal ARN filled in.",
        "Write the shell commands that copy an object between two of our S3 buckets using our "
        "SSO admin profile, printing the caller identity first.",
    ],
    "R3_NOSIM": [
        "Write a Python function that reads one session record from DynamoDB and returns it, "
        "with a test for the function.",
        "Write a Python health check for our local model gateway that returns whether it is "
        "reachable.",
        "Write a Python module that uploads a file to S3 and confirms it landed, plus a small "
        "test for the confirm step.",
    ],
}


def system_for(rule_key: str, arm: str) -> str:
    if arm == "rules_absent":
        return BASE_SYSTEM
    return BASE_SYSTEM + "\n\nProject rule: " + RULES[rule_key]["statement"]


def main() -> int:
    from openai import OpenAI

    client = OpenAI(base_url=os.environ.get("LITELLM_BASE_URL", "http://localhost:4000"),
                    api_key=os.environ.get("LITELLM_API_KEY", "sk-local"))

    report_path = HERE / f"follow_rate_n{N_RUNS}.json"
    cells: list[dict] = []

    def write(complete: bool) -> None:
        report_path.write_text(json.dumps({
            "model": MODEL, "n_runs": N_RUNS, "temperature": TEMPERATURE,
            "arms": ["rules_present", "rules_absent"],
            "cells_expected": len(RULES) * 3 * 2, "complete": complete,
            "rules": {k: {"statement": v["statement"], "source": v["source"],
                          "cites": v["cites"]} for k, v in RULES.items()},
            "cells": cells,
        }, indent=2) + "\n")

    print(f"A3 follow rate: model={MODEL} n={N_RUNS} temperature={TEMPERATURE}")
    print(f"{len(RULES)} rules x 3 paraphrases x 2 arms x {N_RUNS} runs = "
          f"{len(RULES) * 3 * 2 * N_RUNS} calls\n")

    for rule_key in RULES:
        for arm in ("rules_present", "rules_absent"):
            for pi, task in enumerate(TASKS[rule_key]):
                runs = []
                for i in range(N_RUNS):
                    answer, err = None, None
                    for attempt in range(RETRIES):
                        try:
                            resp = client.chat.completions.create(
                                model=MODEL, temperature=TEMPERATURE,
                                messages=[{"role": "system",
                                           "content": system_for(rule_key, arm)},
                                          {"role": "user", "content": task}])
                            answer = resp.choices[0].message.content or ""
                            err = None
                            break
                        except Exception as e:  # noqa: BLE001
                            err = str(e)
                            if "429" in err or "RateLimit" in err:
                                wait = BACKOFF * (2 ** attempt)
                                print(f"    rate limited {rule_key}/{arm}/p{pi}/{i}, "
                                      f"retry {attempt + 1}/{RETRIES} in {wait}s")
                                time.sleep(wait)
                                continue
                            break
                    if err is not None:
                        print(f"  RUN FAILED {rule_key}/{arm}/p{pi}/{i}: {err[:110]}")
                        continue
                    runs.append({"answer": answer})

                verifier = RULES[rule_key]["verifier"]
                scored = [verifier(r["answer"]) for r in runs]
                opps = [s for s in scored if s is not None]
                followed = sum(1 for s in opps if s)
                print(f"  {rule_key} {arm:<14} p{pi}: followed {followed}/{len(opps)} "
                      f"opportunit{'y' if len(opps) == 1 else 'ies'} "
                      f"({len(runs) - len(opps)} n/a of {len(runs)})")
                cells.append({"rule": rule_key, "arm": arm, "prompt": pi,
                              "prompt_text": task, "runs": runs})
                write(complete=False)

    write(complete=True)
    print(f"\n  written to {report_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
