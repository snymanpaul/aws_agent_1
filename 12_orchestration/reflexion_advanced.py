"""
Level 42 (Iteration 2): Beam Reflexion — K parallel actors per round

Upgrade over reflexion.py:
  reflexion.py     → 1 actor per round, reflects on its own failures
  reflexion_adv.py → K actors per round (parallel), each with a different strategy
                     hint; Reflector sees ALL K failure sets and identifies COMMON
                     vs UNIQUE failures — richer signal than a single actor can give

Architecture:
  Round N:
    ┌─ Actor-1 (loop strategy) ──┐
    ├─ Actor-2 (chain strategy) ─┤ → evaluate all K → collective Reflector
    └─ Actor-3 (yield strategy) ─┘        ↑ common failures = systematic bug
  Loop until any candidate hits threshold OR budget exhausted

Key beam insight:
  Different strategies expose different failure modes. "chain.from_iterable"
  only flattens one level — misses deep nesting. A loop or generator handles
  arbitrary depth. The collective Reflector sees which failure is common
  (systematic) vs unique (implementation-specific).

Domain: flatten(nested: list) -> list  (recursive list flattening)
  Test suite includes 3-deep and 5-deep nesting NOT shown in spec examples.
  Actors using itertools.chain without recursion will fail those cases.

  Actor = haiku (cheap). Beam buys quality via exploration + collective retry.
  Evaluator = full Python (imports allowed — strategies may use itertools).
"""
import asyncio
import re
from dataclasses import dataclass, field
from pydantic import BaseModel
from strands import Agent
from tools import get_model

actor_model = get_model("haiku")    # cheap actor; beam buys quality via retries
reflector_model = get_model("haiku")


# ── Task + test suite ─────────────────────────────────────────────────────────

TASK = """Write a Python function called `flatten` that recursively flattens
a nested list into a single flat list.

Signature: flatten(nested: list) -> list

Rules:
  - Any element that is a list should be flattened recursively
  - Non-list elements are kept as-is (strings, ints, None, etc.)
  - Return a new flat list
  - Empty input returns []

Examples:
  flatten([1, [2, 3], 4])       → [1, 2, 3, 4]
  flatten([1, [2, [3, 4]], 5])  → [1, 2, 3, 4, 5]
  flatten([])                    → []
  flatten([1, 2, 3])             → [1, 2, 3]
"""

# Test suite includes hidden edge cases (3-deep, 5-deep) NOT in spec examples.
# Naive chain.from_iterable (1-level only) will fail on those.
TEST_CASES: list[tuple[tuple, list]] = [
    (([1, [2, 3], 4],),          [1, 2, 3, 4]),
    (([1, [2, [3, 4]], 5],),     [1, 2, 3, 4, 5]),
    (([],),                       []),
    (([1, 2, 3],),                [1, 2, 3]),
    (([[[1]], [[2]]],),            [1, 2]),              # 3-deep (hidden)
    (([1, [2, [3, [4, [5]]]]],),  [1, 2, 3, 4, 5]),     # 5-deep (hidden)
    (([[[], [1]], 2],),            [1, 2]),               # empty nested (hidden)
]


# ── Prompts ───────────────────────────────────────────────────────────────────

ACTOR_BASE = """You are an expert Python programmer.
Write clean, correct Python functions.
Return ONLY a ```python code block — no explanation, no prose."""

# Three strategy hints — each actor gets a different one to maximize diversity
ACTOR_STRATEGIES = [
    "Use a manual for-loop with isinstance(item, list) checks and recursion.",
    "Use itertools.chain — import itertools at the top if needed.",
    "Use a recursive generator with yield / yield from.",
]

REFLECTOR_SYSTEM = """You are a Python code reviewer analyzing failures across MULTIPLE candidate implementations.
Identify which failures are COMMON (2+ candidates failed) vs UNIQUE (only 1 failed).
Common failures indicate a systematic misunderstanding — prioritize these in your advice.
Be precise and brief."""


# ── Structured types ──────────────────────────────────────────────────────────

class BeamReflectionOutput(BaseModel):
    common_failures: list[str]  # failures in 2+ candidates — highest priority
    unique_failures: list[str]  # failures in only 1 candidate — lower priority
    improvement_advice: str     # concrete, actionable guidance for next round


# ── Code extraction + evaluation ──────────────────────────────────────────────

def extract_code(response: str, fn_name: str) -> str | None:
    block = re.search(r'```python\s*(.*?)```', str(response), re.DOTALL)
    if block:
        return block.group(1).strip()
    m = re.search(rf'(def {fn_name}\b.*)', str(response), re.DOTALL)
    return m.group(1).strip() if m else None

def evaluate(code: str, fn_name: str) -> tuple[float, list[str], list[str]]:
    """Run code against TEST_CASES with full Python environment (imports allowed)."""
    ns: dict = {}
    try:
        exec(code, ns)
    except Exception as e:
        return 0.0, [f"exec failed: {e}"], []

    fn = ns.get(fn_name)
    if fn is None:
        return 0.0, [f"function '{fn_name}' not defined"], []

    failures, passes = [], []
    for args, expected in TEST_CASES:
        try:
            result = fn(*args)
            if result == expected:
                passes.append(f"flatten({args[0]}) → {result} ✓")
            else:
                failures.append(
                    f"flatten({args[0]}) → got {result}, expected {expected}"
                )
        except Exception as e:
            failures.append(f"flatten({args[0]}) → exception: {e}")

    score = len(passes) / len(TEST_CASES)
    return score, failures, passes


# ── Beam data types ───────────────────────────────────────────────────────────

@dataclass
class Candidate:
    round_num: int
    idx: int
    strategy: str
    code: str
    score: float
    failures: list[str]
    passes: list[str]

@dataclass
class BeamRound:
    round_num: int
    candidates: list[Candidate]
    best_score: float
    collective_advice: str = ""

@dataclass
class BeamReflexionResult:
    best: Candidate
    rounds: list[BeamRound] = field(default_factory=list)
    converged: bool = False


# ── Parallel strategy-diverse actors ─────────────────────────────────────────

async def _generate_candidates(task: str, strategies: list[str], context: str) -> list[str]:
    """Run one actor per strategy concurrently — each gets a different impl hint."""
    prompt = task
    if context:
        prompt += f"\n\n{context}\n\nWrite a corrected implementation:"

    actors = [
        Agent(
            model=actor_model,
            system_prompt=ACTOR_BASE + f"\n\nImplementation approach: {s}",
            tools=[],
            callback_handler=None,
        )
        for s in strategies
    ]
    results = await asyncio.gather(*[asyncio.to_thread(a, prompt) for a in actors])
    return [str(r) for r in results]


# ── Collective failure analysis ───────────────────────────────────────────────

def collective_failures(candidates: list[Candidate]) -> tuple[list[str], list[str]]:
    from collections import Counter
    all_f = [f for c in candidates for f in c.failures]
    counts = Counter(all_f)
    common = [f for f, n in counts.items() if n >= 2]
    unique = [f for f, n in counts.items() if n == 1]
    return common, unique


# ── Beam Reflexion loop ───────────────────────────────────────────────────────

def run_beam_reflexion(
    task: str,
    fn_name: str,
    strategies: list[str],
    budget: int = 4,
    threshold: float = 1.0,
) -> BeamReflexionResult:

    beam_width = len(strategies)
    reflector = Agent(
        model=reflector_model,
        system_prompt=REFLECTOR_SYSTEM,
        tools=[],
        callback_handler=None,
    )

    best_global: Candidate | None = None
    reflection_context = ""
    rounds: list[BeamRound] = []

    for round_num in range(1, budget + 1):
        print(f"\n{'═' * 60}")
        print(f"ROUND {round_num}/{budget}  (beam={beam_width} strategies)")
        print(f"{'═' * 60}")

        # ── Generate K candidates in parallel, one per strategy ────────────
        raw_results = asyncio.run(_generate_candidates(task, strategies, reflection_context))

        # ── Evaluate all K ─────────────────────────────────────────────────
        candidates: list[Candidate] = []
        for i, (raw, strategy) in enumerate(zip(raw_results, strategies)):
            code = extract_code(raw, fn_name)
            if code:
                score, failures, passes = evaluate(code, fn_name)
            else:
                score, failures, passes = 0.0, ["no code block extracted"], []
            c = Candidate(round_num, i + 1, strategy, code or "", score, failures, passes)
            candidates.append(c)
            status = "✓" if score >= threshold else f"{score:.2f}"
            strat_short = strategy[:30]
            fail_note = f"  ✗ {failures[0][:55]}..." if failures else ""
            print(f"  C{i+1} [{strat_short}]: [{status}] {len(passes)}/{len(TEST_CASES)}{fail_note}")

        # ── Track global best ──────────────────────────────────────────────
        round_best = max(candidates, key=lambda c: c.score)
        if best_global is None or round_best.score > best_global.score:
            best_global = round_best

        beam_round = BeamRound(round_num, candidates, round_best.score)
        rounds.append(beam_round)

        # ── Convergence: any candidate hits threshold ──────────────────────
        convergers = [c.idx for c in candidates if c.score >= threshold]
        if convergers:
            print(f"\n  🎯 Candidate(s) {convergers} hit threshold")
            return BeamReflexionResult(best=best_global, rounds=rounds, converged=True)

        if round_num == budget:
            break

        # ── Collective reflection ──────────────────────────────────────────
        common, unique = collective_failures(candidates)
        n_failing = sum(1 for c in candidates if c.failures)
        print(f"\n  Collective reflection — {n_failing}/{beam_width} had failures")
        print(f"  Common ({len(common)}): {[f[:55] for f in common[:2]]}")
        print(f"  Unique ({len(unique)}): {len(unique)} total")

        common_text = "\n".join(f"  [COMMON] {f}" for f in common) or "  (none)"
        unique_text = "\n".join(f"  [UNIQUE] {f}" for f in unique) or "  (none)"

        reflector_prompt = (
            f"Task: {task.splitlines()[0]}\n\n"
            f"Round {round_num}/{budget}, {beam_width} candidates, {n_failing} had failures.\n\n"
            f"COMMON failures (2+ candidates — systematic bug):\n{common_text}\n\n"
            f"UNIQUE failures (1 candidate only):\n{unique_text}\n\n"
            f"Identify the pattern and give actionable improvement advice."
        )
        ref_raw = reflector(reflector_prompt, structured_output_model=BeamReflectionOutput)
        reflection = ref_raw.structured_output

        advice = reflection.improvement_advice
        print(f"  Advice: {advice[:220]}")
        beam_round.collective_advice = advice

        reflection_context += (
            f"\n--- Round {round_num} beam critique ---\n"
            f"Common failures:\n{common_text}\n"
            f"Unique failures:\n{unique_text}\n"
            f"Fix this: {advice}\n"
        )

    return BeamReflexionResult(best=best_global, rounds=rounds, converged=False)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("L42 (Iter 2): BEAM REFLEXION — Strategy-Diverse Parallel Actors")
    print("=" * 60)
    print(f"\nTask: flatten(nested) → list  (hidden deep-nesting edge cases)")
    print(f"Actors: {len(ACTOR_STRATEGIES)} strategies | Budget: 4 rounds | Threshold: 100%")
    print(f"Evaluator: full Python (imports allowed)")
    print(f"Reflector: haiku — common vs unique failure analysis")
    print(f"\nStrategies:")
    for i, s in enumerate(ACTOR_STRATEGIES, 1):
        print(f"  {i}. {s}")

    result = run_beam_reflexion(
        task=TASK,
        fn_name="flatten",
        strategies=ACTOR_STRATEGIES,
        budget=4,
        threshold=1.0,
    )

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    status = "✓ converged" if result.converged else "✗ budget exhausted"
    total = sum(len(r.candidates) for r in result.rounds)
    print(f"  {status} after {len(result.rounds)} round(s)  ({total} candidates evaluated)")
    if result.best:
        print(f"  Best: Round {result.best.round_num} C{result.best.idx} "
              f"[{result.best.strategy[:35]}] — score {result.best.score:.2f}")
        print(f"\nBest implementation:")
        print(f"```python\n{result.best.code}\n```")

    print("\n" + "=" * 60)
    print("SCORE PROGRESSION (per round, per strategy)")
    print("=" * 60)
    for r in result.rounds:
        best = max(c.score for c in r.candidates)
        bar = "█" * int(best * 20) + "░" * (20 - int(best * 20))
        scores = "  ".join(f"C{c.idx}:{c.score:.2f}" for c in r.candidates)
        print(f"  Round {r.round_num}: [{bar}] best={best:.2f}  ({scores})")
        if r.collective_advice:
            print(f"           Advice: {r.collective_advice[:80]}...")

    print("\n" + "=" * 60)
    print("BEAM vs SINGLE-ACTOR REFLEXION")
    print("=" * 60)
    print("  Strategy diversity:  different impl approaches → different failure modes")
    print("  Collective signal:   common failures = systematic bug (fix first)")
    print("                       unique failures = strategy-specific (lower priority)")
    print("  Parallel cost:       K strategies run in ~same wall-clock time as 1")
    print("  Early stopping:      any 1 of K correct is sufficient to converge")
    print("  Best use case:       tasks where spec is ambiguous or partially specified")
    print("                       — diversity surfaces which interpretation is correct")
