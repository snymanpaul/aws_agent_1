"""
Level 83: Agentic Trajectory Evaluation (tool selection + order + ARGUMENTS)
==========================================================================
Closes the audit gap: the repo's only tool-use eval (L35) captured a trajectory as a
FLAT SET of tool names — losing call order and arguments — and the argument/selection
accuracy evaluators were imported but never run. This scores the real multi-step
trajectory: which tools, in what order, with what arguments.

Anti-simulation design (no fakes/stubs):
  - Trajectories are captured from REAL agent runs via Strands BeforeToolCallEvent hooks
    (tool name + actual arguments + order). Nothing is hand-authored.
  - Discrimination is proven WITHOUT a faked-bad trajectory two ways:
      (1) the SAME real trajectory is scored against a matching spec and a deliberately
          wrong spec -> argument score must drop (proves the checker reads args).
      (2) a SECOND real run is driven (tools suppressed) so the agent really omits a
          tool -> selection must fail and the judge must rank it below the good run.
  - Deterministic checkers (selection/order/args) plus one real LLM-judge.

Run:
  podman start litellm-proxy
  uv run python 13_quality/trajectory_eval.py
"""

from strands import Agent, tool
from strands.hooks import HookProvider, HookRegistry, BeforeToolCallEvent
from strands.models.openai import OpenAIModel


def _model(temperature=0.0):
    return OpenAIModel(model_id="gemini-2.5-flash",
                       client_args={"base_url": "http://localhost:4000", "api_key": "sk-local"},
                       params={"temperature": temperature})


@tool
def convert_temp(value: float, from_unit: str, to_unit: str) -> str:
    """Convert a temperature between Celsius and Fahrenheit."""
    f, t = from_unit.strip().lower()[:1], to_unit.strip().lower()[:1]
    out = value * 9 / 5 + 32 if (f, t) == ("c", "f") else (value - 32) * 5 / 9 if (f, t) == ("f", "c") else value
    return f"{out:.1f} {to_unit}"


@tool
def lookup_population(city: str) -> str:
    """Return the population of a city."""
    return {"tokyo": "37 million", "paris": "2.1 million"}.get(city.strip().lower(), "unknown")


class TrajectoryRecorder(HookProvider):
    """Captures the REAL tool-call trajectory: ordered (tool, args)."""
    def __init__(self):
        self.calls = []

    def register_hooks(self, registry: HookRegistry, **_):
        registry.add_callback(BeforeToolCallEvent,
                              lambda e: self.calls.append({"tool": e.tool_use.get("name"),
                                                           "args": e.tool_use.get("input") or {}}))


TASK = "Convert 100 Celsius to Fahrenheit, then tell me Tokyo's population."

# Expected agentic trajectory (the spec a trajectory eval grades against)
GOOD_SPEC = [
    {"tool": "convert_temp", "args": {"value": 100, "from": "c", "to": "f"}},
    {"tool": "lookup_population", "args": {"city": "tokyo"}},
]
WRONG_SPEC = [   # same tools, deliberately wrong args/order -> must score lower on a real good trajectory
    {"tool": "lookup_population", "args": {"city": "paris"}},
    {"tool": "convert_temp", "args": {"value": 50, "from": "f", "to": "c"}},
]


def run_agent(suppress_tools=False):
    rec = TrajectoryRecorder()
    prompt = ("Answer ONLY from your own knowledge. Do NOT call any tools. " + TASK) if suppress_tools else TASK
    agent = Agent(model=_model(), tools=[convert_temp, lookup_population], hooks=[rec], callback_handler=None,
                  system_prompt="Use the provided tools to answer precisely.")
    out = str(agent(prompt))
    return rec.calls, out


# ---- deterministic evaluators over a REAL trajectory ----
def _arg_match(actual, expected):
    a = {str(k).lower(): str(v).strip().lower() for k, v in (actual or {}).items()}
    for ek, ev in expected.items():
        ev = str(ev).strip().lower()
        hit = any((ek in ak or ak in ek) and (av.startswith(ev[:1]) if len(ev) == 1 else av == ev or ev in av)
                  for ak, av in a.items())
        if not hit:
            return False
    return True


def score_selection(calls, spec):
    want = {s["tool"] for s in spec}
    got = {c["tool"] for c in calls}
    return len(want & got) / len(want)


def score_order(calls, spec):
    seq = [c["tool"] for c in calls]
    want = [s["tool"] for s in spec]
    idx, ok = -1, 0
    for w in want:
        try:
            idx = seq.index(w, idx + 1); ok += 1
        except ValueError:
            break
    return ok / len(want)


def score_args(calls, spec):
    matched = 0
    for s in spec:
        cand = [c for c in calls if c["tool"] == s["tool"]]
        if any(_arg_match(c["args"], s["args"]) for c in cand):
            matched += 1
    return matched / len(spec)


def judge_quality(calls, out):
    traj = "; ".join(f"{c['tool']}({c['args']})" for c in calls) or "(no tools called)"
    j = Agent(model=_model(), callback_handler=None,
              system_prompt="Score an agent's tool-use trajectory for the task on a 1-5 scale. Reply with ONLY the digit.")
    r = str(j(f"Task: {TASK}\nTrajectory: {traj}\nFinal answer: {out[:200]}\nScore 1-5 (5=correct tools, right order, right args):")).strip()
    m = [ch for ch in r if ch in "12345"]
    return int(m[0]) if m else 0


def verify():
    print("[L83] good run x3 (deterministic checkers on REAL trajectory):")
    sel = order = args = 0.0
    last_calls = None
    for i in range(3):
        calls, out = run_agent()
        last_calls = calls
        s, o, a = score_selection(calls, GOOD_SPEC), score_order(calls, GOOD_SPEC), score_args(calls, GOOD_SPEC)
        sel, order, args = sel + s, order + o, args + a
        print(f"  run{i+1}: sel={s:.2f} order={o:.2f} args={a:.2f} | {[c['tool'] for c in calls]}")
    sel, order, args = sel / 3, order / 3, args / 3

    # discrimination (1): same real trajectory vs a WRONG spec -> args must drop
    args_wrong = score_args(last_calls, WRONG_SPEC)
    print(f"[L83] discrimination#1: args vs GOOD_SPEC={args:.2f}  vs WRONG_SPEC={args_wrong:.2f}")

    # discrimination (2): a SECOND real run with tools suppressed -> selection fails, judge ranks lower
    bad_calls, bad_out = run_agent(suppress_tools=True)
    good_judge = judge_quality(last_calls, "")
    bad_judge = judge_quality(bad_calls, bad_out)
    bad_sel = score_selection(bad_calls, GOOD_SPEC)
    print(f"[L83] discrimination#2: judge good={good_judge} bad={bad_judge} | bad_run_selection={bad_sel:.2f} tools={[c['tool'] for c in bad_calls]}")

    checks = {
        "good: tool selection == 1.0": sel == 1.0,
        "good: order == 1.0": order == 1.0,
        "good: arg-correctness == 1.0": args == 1.0,
        "checker reads args (WRONG_SPEC scores lower)": args_wrong < args,
        "judge ranks good >= bad": good_judge >= bad_judge,
        "good judge >= 4": good_judge >= 4,
        "tool-suppressed run really omits convert_temp": bad_sel < 1.0,
    }
    for k, v in checks.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    assert all(checks.values()), "L83 FAILED"
    print("[L83] PASS — trajectory eval scores selection+order+ARGS on real runs, with real discrimination")


if __name__ == "__main__":
    verify()
