"""
Level 42: Reflexion — Iterative Self-Critique Loop

Reflexion overlays a structured quality loop on top of any generation task:

  Actor      → generates a candidate answer
  Evaluator  → scores it objectively (0.0–1.0) against ground truth
  Reflector  → given failures, produces targeted improvement advice
  Loop       → repeats until score >= threshold OR budget exhausted

What makes this different from L11 (Reflection):
  L11 = one prompt-level critique ("review and improve")
  L42 = loop-level control with numeric threshold, retry budget,
        best-answer tracking, and accumulating critique context

What makes this different from ReWOO (L41):
  ReWOO  = fixed plan, zero adaptation after Phase 1
  Reflexion = iterates until quality criteria are met

Domain: code generation — `format_duration(seconds: int) -> str`
  Zero-component suppression is the edge case that trips LLMs on first attempt.
  The Evaluator is pure Python (runs test suite, no LLM cost).
  The Reflector uses an LLM to translate test failures into targeted critique.
"""
import re
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dataclasses import dataclass, field
from pydantic import BaseModel
from strands import Agent
from tools import get_model

model      = get_model("claude-sonnet-4")
fast_model = get_model("haiku")


# ── Task + test suite ─────────────────────────────────────────────────────────

TASK = """Write a Python function called `format_duration` that converts an integer
number of seconds into a human-readable duration string.

Requirements:
  - Break seconds into days, hours, minutes, seconds
  - OMIT any component that is zero (e.g. 3605s → "1h 5s", NOT "1h 0m 5s")
  - When all components are zero (input is 0), return "0s"
  - Components are separated by a single space
  - Order: days (d), hours (h), minutes (m), seconds (s)

Examples:
  0       → "0s"
  30      → "30s"
  60      → "1m"
  65      → "1m 5s"
  3600    → "1h"
  3661    → "1h 1m 1s"
"""

TEST_CASES: list[tuple[tuple, str]] = [
    ((0,),      "0s"),
    ((30,),     "30s"),
    ((60,),     "1m"),
    ((65,),     "1m 5s"),
    ((3600,),   "1h"),
    ((3661,),   "1h 1m 1s"),
    ((3605,),   "1h 5s"),        # zero minutes must be suppressed
    ((86400,),  "1d"),
    ((90061,),  "1d 1h 1m 1s"),
    ((86405,),  "1d 5s"),        # zero hours and minutes must be suppressed
]


# ── Prompts ───────────────────────────────────────────────────────────────────

ACTOR_SYSTEM = """You are an expert Python programmer.
Write clean, correct Python functions.
Return ONLY a ```python code block — no explanation, no prose."""

REFLECTOR_SYSTEM = """You are a Python code reviewer.
Given a function's test failures, identify exactly what is wrong and give
specific, actionable advice for the next implementation attempt.
Be precise and brief — the programmer will use your advice to fix the code."""


# ── Structured types ──────────────────────────────────────────────────────────

class ReflectionOutput(BaseModel):
    passed: int
    total: int
    score: float               # passed / total, range 0.0–1.0
    what_failed: list[str]     # one line per failing test: "f(x) → got Y, expected Z"
    improvement_advice: str    # concrete next-attempt guidance, max 3 sentences


# ── Code extraction + evaluation ──────────────────────────────────────────────

def extract_code(response: str, fn_name: str) -> str | None:
    block = re.search(r'```python\s*(.*?)```', str(response), re.DOTALL)
    if block:
        return block.group(1).strip()
    m = re.search(rf'(def {fn_name}\b.*)', str(response), re.DOTALL)
    return m.group(1).strip() if m else None

def evaluate(code: str, fn_name: str) -> tuple[float, list[str], list[str]]:
    """
    Run code against TEST_CASES.
    Returns (score, failures, passes) where score = passed/total.
    """
    safe_builtins = {
        "round": round, "min": min, "max": max, "len": len,
        "list": list, "range": range, "int": int, "str": str,
        "divmod": divmod, "abs": abs, "sum": sum, "enumerate": enumerate,
    }
    ns: dict = {"__builtins__": safe_builtins}

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
                passes.append(f"format_duration({args[0]}) → {result!r} ✓")
            else:
                failures.append(
                    f"format_duration({args[0]}) → got {result!r}, expected {expected!r}"
                )
        except Exception as e:
            failures.append(f"format_duration({args[0]}) → exception: {e}")

    score = len(passes) / len(TEST_CASES)
    return score, failures, passes


# ── Reflexion loop ────────────────────────────────────────────────────────────

@dataclass
class Attempt:
    number: int
    code: str
    score: float
    failures: list[str]
    reflection: str = ""

@dataclass
class ReflexionResult:
    best: Attempt
    attempts: list[Attempt] = field(default_factory=list)
    converged: bool = False

def run_reflexion(
    task: str,
    fn_name: str,
    budget: int = 4,
    threshold: float = 1.0,
) -> ReflexionResult:

    actor     = Agent(model=model,      system_prompt=ACTOR_SYSTEM,     tools=[], callback_handler=None)
    reflector = Agent(model=fast_model, system_prompt=REFLECTOR_SYSTEM, tools=[], callback_handler=None)

    history: list[Attempt] = []
    best: Attempt | None   = None
    reflection_context     = ""     # accumulates across attempts

    for attempt_num in range(1, budget + 1):
        print(f"\n{'─' * 60}")
        print(f"ATTEMPT {attempt_num}/{budget}")
        print(f"{'─' * 60}")

        # ── Actor: generate candidate ──────────────────────────────────────
        actor_prompt = task
        if reflection_context:
            actor_prompt += f"\n\n{reflection_context}\n\nNow write a corrected implementation:"

        raw = actor(actor_prompt)
        code = extract_code(raw, fn_name)

        if not code:
            print("  ✗ Could not extract function from response")
            reflection_context += f"\nAttempt {attempt_num}: failed to produce a code block.\n"
            continue

        print(f"  Generated code ({len(code.splitlines())} lines)")

        # ── Evaluator: score against test suite (no LLM) ──────────────────
        score, failures, passes = evaluate(code, fn_name)
        print(f"  Score: {score:.2f}  ({len(passes)}/{len(TEST_CASES)} tests passed)")

        if failures:
            for f in failures:
                print(f"  ✗ {f}")
        else:
            print(f"  ✓ All tests passed")

        attempt = Attempt(number=attempt_num, code=code, score=score, failures=failures)
        history.append(attempt)

        if best is None or score > best.score:
            best = attempt

        if score >= threshold:
            print(f"\n  🎯 Threshold {threshold:.0%} reached — stopping early")
            best.reflection = reflection_context
            return ReflexionResult(best=best, attempts=history, converged=True)

        if attempt_num == budget:
            break  # budget exhausted — no point reflecting

        # ── Reflector: translate failures into improvement advice ──────────
        print(f"\n  Reflecting on {len(failures)} failure(s)...")

        failure_text = "\n".join(f"  - {f}" for f in failures)
        pass_text    = "\n".join(f"  - {p}" for p in passes[:3])  # show up to 3 passes
        reflector_prompt = (
            f"Function task: {task.splitlines()[0]}\n\n"
            f"Tests passed ({len(passes)}/{len(TEST_CASES)}):\n{pass_text}\n"
            f"{'  ...' if len(passes) > 3 else ''}\n\n"
            f"Tests FAILED:\n{failure_text}\n\n"
            f"Score: {score:.2f}. Provide a score (0.0–1.0 = failed/total), "
            f"list what failed, and give specific improvement advice."
        )

        ref_raw    = reflector(reflector_prompt, structured_output_model=ReflectionOutput)
        reflection = ref_raw.structured_output

        advice = reflection.improvement_advice
        print(f"  Advice: {advice[:200]}")
        attempt.reflection = advice

        # Accumulate — each attempt's critique is visible to all future attempts
        reflection_context += (
            f"\n--- Attempt {attempt_num} critique ---\n"
            f"Score: {score:.2f} ({len(passes)}/{len(TEST_CASES)} passed)\n"
            f"Failures:\n{failure_text}\n"
            f"What to fix: {advice}\n"
        )

    best.reflection = reflection_context
    return ReflexionResult(best=best, attempts=history, converged=False)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("L42: REFLEXION — Iterative Self-Critique Loop")
    print("=" * 60)
    print(f"\nTask: format_duration(seconds) → human-readable string")
    print(f"Budget: 4 attempts | Threshold: 100% tests pass")
    print(f"Evaluator: pure Python test runner (0 LLM calls for scoring)")
    print(f"Reflector: haiku — translates failures into improvement advice")

    result = run_reflexion(
        task=TASK,
        fn_name="format_duration",
        budget=4,
        threshold=1.0,
    )

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    status = "✓ converged" if result.converged else f"✗ budget exhausted"
    print(f"  {status} after {len(result.attempts)} attempt(s)")
    print(f"  Best score: {result.best.score:.2f} (attempt #{result.best.number})")
    print(f"\nBest implementation:")
    print(f"```python\n{result.best.code}\n```")

    print("\n" + "=" * 60)
    print("SCORE PROGRESSION")
    print("=" * 60)
    for a in result.attempts:
        bar = "█" * int(a.score * 20) + "░" * (20 - int(a.score * 20))
        print(f"  Attempt {a.number}: [{bar}] {a.score:.2f}")

    print("\n" + "=" * 60)
    print("KEY CONCEPTS DEMONSTRATED")
    print("=" * 60)
    print("  Numeric threshold   — loop stops when score >= 1.0, not when LLM 'feels' done")
    print("  Retry budget        — hard cap at 4 attempts; returns best even if never converged")
    print("  Accumulating context — each attempt's critique is visible to all future attempts")
    print("  Evaluator cost      — 0 LLM calls for scoring; only Actor + Reflector use LLMs")
    print("  vs L11              — L11 is one prompt exchange; Reflexion is a structured loop")
    print("                        with objective exit criteria and score tracking")
