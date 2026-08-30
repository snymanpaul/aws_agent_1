"""Record what the A5 memory-effect run measured.

Every figure was read from `tests/memory_effect/memory_effect_n5.json` through
`analyse_memory_effect.py`, which recomputes each rate from the stored answer text with the
current verifiers.

    uv run python _sandbox/append_a5_result_obs.py            # dry run
    uv run python _sandbox/append_a5_result_obs.py --write
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.obs_log import append  # noqa: E402

TS = "2026-08-31T00:20:00Z"
REPORT = "tests/memory_effect/memory_effect_n5.json"

ENTRIES = [
    dict(
        ts=TS, level=0, cat="insight", topic="a-captured-mistake-in-context-does-not-recur",
        obs="A5, 600 calls over 20 captured mistakes spanning L5 to L58. With the observation "
            "in the system prompt the recorded mistake recurred 0 times in 268 runs that "
            "reached the fork [0.00,0.01]. Without it, 86 times in 200 [0.36,0.50]. "
            "perm_test p=0.0003. Per case: 12 USED (the mistake vanished with the note), 6 "
            "where the model never made the mistake unaided, 2 where one arm never reached "
            "the fork so the arms are not comparable. Zero IGNORED.",
        ctx=f"gpt-5-nano, n=5 per case per paraphrase per arm. {REPORT}.",
        entities=["A5", "Memory", "Measurement", "Recurrence"],
    ),
    dict(
        ts=TS, level=0, cat="insight", topic="a5-measures-the-ceiling-not-a-memory-system",
        obs="What A5 does NOT show. The note is placed directly in the system prompt, keyed to "
            "the case by hand, so retrieval is perfect by construction. The number is "
            "therefore a ceiling: given the right observation, in context, relevant to the "
            "task, it gets used. It says nothing about selecting that observation out of the "
            "1008 in the log, which is the part a real memory system has to do and the part "
            "the published work calls the bottleneck. Reading this as 'the memory works' "
            "would be reading past the design.",
        ctx="Design of run_memory_effect.py: system_for() injects note_for(obs_id) directly.",
        entities=["A5", "Memory", "Retrieval", "Limits"],
    ),
    dict(
        ts=TS, level=0, cat="insight", topic="six-of-twenty-captured-mistakes-bought-nothing",
        obs="6 of the 20 cases recurred 0 times in BOTH arms: the graph safety limit "
            "(obs-0032), the container proxy URL (obs-0319), the @tool .func attribute "
            "(obs-0337), the Temporal result timeout (obs-0578), the MCPAgentTool attribute "
            "(obs-0675) and the SessionMessage role (obs-0680). For this model on these "
            "tasks, capturing those mistakes bought nothing, "
            "because it does not make them unaided. That is not an argument against capturing "
            "them: it is a measured reason to expect a memory's value to depend on the model "
            "as much as on the mistake, and it is exactly the kind of line a context budget "
            "should be spent on last.",
        ctx=f"Per-case section of analyse_memory_effect.py over {REPORT}.",
        entities=["A5", "Memory", "ContextBudget"],
    ),
    dict(
        ts=TS, level=0, cat="mistake", topic="four-verifier-defects-all-found-by-reading-answers",
        obs="Four defects in the A5 verifiers, none visible in a rate, all found by opening "
            "the answers. (1) A correct answer that added 'not Swarm(agents=[...])' as an "
            "explanation was scored as the mistake, and the bias ran one way, since the arm "
            "carrying the memory is the arm that restates it: fixing it moved that case from "
            "7/15 to 0/15. (2) Agent(name=session_id, ...) counted as passing session_id to "
            "the Agent. (3) A coroutine awaited two lines below its call counted as the sync "
            "bug. (4) getattr(tool, 'tool_name') plus a docstring saying 'there is no .name "
            "attribute' was scored as a .name access, which was A5's ONLY memory-arm "
            "recurrence: fixing it took the pooled figure from 1/275 to 0/268. Storing raw "
            "answers is what made all four fixable after the run rather than fatal to it.",
        ctx="Each defect is now pinned by a control in tests/memory_effect/test_cases.py.",
        entities=["A5", "Verifier", "R9", "Measurement"],
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
