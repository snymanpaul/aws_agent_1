"""A5: does a captured mistake get avoided BECAUSE it was captured?

Both repos measure capture. Neither measures effect. This measures effect, with the
OBSERVATION as the unit rather than the level.

Not named `test_*`, so pytest does not collect it: it spends real model calls. Its verifiers
have offline controls in `test_cases.py`, which pytest does collect.

PREREGISTRATION, committed before the first measured run

  question        For a mistake this repo captured, how often does it recur when the
                  observation is reachable in context, and how often when it is not?

  primary metric  ONE: RECURRENCE RATE, the fraction of runs that took the same wrong fork,
                  computed over runs that REACHED the fork. An answer that never touched the
                  API can neither repeat the mistake nor avoid it, so it leaves the
                  denominator. Lower is better in the memory arm.

  arms            memory_present  the observation's own text, loaded from the log by id, is
                                  in the system prompt as a project note.
                  memory_absent   the same system prompt without it.
                  The task text is identical across arms.

  cases           20 entries with cat: mistake, walked in id order across L5 to L58, one per
                  topic area, subject to one eligibility rule stated up front: the mistake
                  has to be visible in a produced artifact. See cases.py.

  tasks           Three paraphrases per case (R5), each recreating the situation without
                  naming the correction. `test_cases.py` asserts no task contains the
                  giveaway token, because a task that hands over the answer measures
                  instruction repetition rather than memory.

  n               5 runs per case per paraphrase per arm = 600 calls.

  hypothesis      The memory lowers recurrence. The result worth having is the shape of the
                  failure when it does not: an observation that is in context, is relevant,
                  and is not used is a use problem, not a storage problem, and no amount of
                  further capture fixes it.

  reporting       PER CASE as well as pooled. A pooled number hides the distinction between
                  a memory that was used, one that was ignored, and one whose fork was never
                  reached, and those three call for different work.

  decision rule   Per case, `perm_test` between arms. With 20 cases the Bonferroni threshold
                  is 0.05 / 20 = 0.0025, which 5 runs per cell can rarely clear, so the
                  per-case numbers are reported as descriptive and the pooled comparison
                  carries the inference. Stated here, before the run, rather than chosen
                  afterwards.

  raw output      Every answer is stored and every rate is recomputed from it by
                  `analyse_memory_effect.py`.

  model           gpt-5-nano through the LiteLLM proxy, temperature 1, three workers. Same
                  route as A3, and for the same measured reason: the mini route returns 429
                  under load.

    podman start litellm-proxy
    uv run python tests/memory_effect/run_memory_effect.py
    uv run python tests/memory_effect/analyse_memory_effect.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cases import CASES, note_for  # noqa: E402

MODEL = os.environ.get("ME_MODEL", "gpt-5-nano")
N_RUNS = int(os.environ.get("ME_RUNS", "5"))
TEMPERATURE = float(os.environ.get("ME_TEMPERATURE", "1"))
RETRIES = int(os.environ.get("ME_RETRIES", "5"))
BACKOFF = float(os.environ.get("ME_BACKOFF", "10"))
WORKERS = int(os.environ.get("ME_WORKERS", "3"))
ONLY = [k for k in os.environ.get("ME_CASES", "").split(",") if k]

BASE_SYSTEM = (
    "You are helping maintain a Python repository of AWS agent lessons built on the Strands "
    "Agents SDK. Answer with the code asked for and a short note, nothing else."
)


def system_for(case: dict, arm: str) -> str:
    if arm == "memory_absent":
        return BASE_SYSTEM
    return (BASE_SYSTEM + "\n\nNote from this project's observation log ("
            + case["obs_id"] + "):\n" + note_for(case["obs_id"]))


def ask(client, system: str, task: str) -> tuple[str | None, str | None]:
    for attempt in range(RETRIES):
        try:
            resp = client.chat.completions.create(
                model=MODEL, temperature=TEMPERATURE,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": task}])
            return resp.choices[0].message.content or "", None
        except Exception as e:  # noqa: BLE001
            err = str(e)
            if ("429" in err or "RateLimit" in err) and attempt < RETRIES - 1:
                time.sleep(BACKOFF * (2 ** attempt))
                continue
            return None, err
    return None, "retries exhausted"


def main() -> int:
    from concurrent.futures import ThreadPoolExecutor

    from openai import OpenAI

    client = OpenAI(base_url=os.environ.get("LITELLM_BASE_URL", "http://localhost:4000"),
                    api_key=os.environ.get("LITELLM_API_KEY", "sk-local"))

    cases = [c for c in CASES if not ONLY or c["key"] in ONLY]
    report_path = HERE / f"memory_effect_n{N_RUNS}.json"
    cells: list[dict] = []

    def write(complete: bool) -> None:
        report_path.write_text(json.dumps({
            "model": MODEL, "n_runs": N_RUNS, "temperature": TEMPERATURE,
            "arms": ["memory_present", "memory_absent"],
            "cells_expected": len(cases) * 3 * 2, "complete": complete,
            "cases": {c["key"]: {"obs_id": c["obs_id"], "note": note_for(c["obs_id"])}
                      for c in cases},
            "cells": cells,
        }, indent=2) + "\n")

    print(f"A5 memory effect: model={MODEL} n={N_RUNS} temperature={TEMPERATURE} "
          f"workers={WORKERS}")
    print(f"{len(cases)} cases x 3 paraphrases x 2 arms x {N_RUNS} runs = "
          f"{len(cases) * 3 * 2 * N_RUNS} calls\n")

    for case in cases:
        for arm in ("memory_present", "memory_absent"):
            for pi, task in enumerate(case["tasks"]):
                system = system_for(case, arm)
                with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                    results = list(pool.map(lambda _: ask(client, system, task),
                                            range(N_RUNS)))
                runs = [{"answer": a} for a, err in results if err is None]
                for _, err in results:
                    if err:
                        print(f"  RUN FAILED {case['key']}/{arm}/p{pi}: {err[:110]}")

                scored = [case["recurs"](r["answer"]) for r in runs]
                reached = [s for s in scored if s is not None]
                recurred = sum(1 for s in reached if s)
                print(f"  {case['key']:<22} {arm:<15} p{pi}: recurred {recurred}/"
                      f"{len(reached)} reached ({len(runs) - len(reached)} n/a of "
                      f"{len(runs)})", flush=True)
                cells.append({"case": case["key"], "obs_id": case["obs_id"], "arm": arm,
                              "prompt": pi, "prompt_text": task, "runs": runs,
                              "failed": sum(1 for _, err in results if err)})
                write(complete=False)

    write(complete=True)
    print(f"\n  written to {report_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
