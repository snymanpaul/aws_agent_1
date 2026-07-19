"""
Level 41: ReWOO — Custom Orchestration (Plan → Execute → Synthesize)

ReWOO (Reasoning Without Observation) replaces the default ReAct loop with
a three-phase strategy:
  Phase 1 (Plan):      LLM writes the full tool-call script in ONE pass
  Phase 2 (Execute):   Tools run in order — zero LLM calls, each result fills a placeholder
  Phase 3 (Synthesize): LLM produces the final answer from task + all evidence

This is different from L11 Reflection:
  L11 = prompt-level self-critique (the agent talks to itself)
  L41 = loop-level override (we replace HOW the agent dispatches tool calls)

Domain: trip planning — search flights, hotels, weather, calculate budget
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pydantic import BaseModel
from strands import Agent, tool
from tools import get_model

model = get_model("claude-sonnet-4")
fast_model = get_model("haiku")


# ── Domain tools ──────────────────────────────────────────────────────────────
# Plain Python functions used directly by the ReWOO executor (no agent loop)

def search_flights_fn(origin: str, destination: str, date: str) -> dict:
    # Simulated — in production this would call a flights API
    return {"price": 450, "airline": "United", "flight": "UA342",
            "duration": "5h30m", "departs": "08:00"}

def search_hotels_fn(city: str, checkin: str, checkout: str) -> dict:
    return {"price": 280, "name": "Marriott Times Square",
            "stars": 4, "cancellation": "free"}

def get_weather_fn(city: str, date: str) -> dict:
    return {"forecast": "Partly cloudy", "high_f": 45,
            "low_f": 32, "precip_pct": 10}

def calculate_budget_fn(flight_cost: float, hotel_cost: float, days: int) -> dict:
    hotel_total = float(hotel_cost) * int(days)
    total = float(flight_cost) + hotel_total
    return {"total": total,
            "breakdown": f"flights ${flight_cost} + hotel ${hotel_total} ({days}×${hotel_cost})"}

TOOL_REGISTRY = {
    "search_flights":   search_flights_fn,
    "search_hotels":    search_hotels_fn,
    "get_weather":      get_weather_fn,
    "calculate_budget": calculate_budget_fn,
}

# @tool decorated versions — only used by the ReAct agent for comparison
@tool
def search_flights(origin: str, destination: str, date: str) -> str:
    """Search for available flights between two cities on a given date."""
    r = search_flights_fn(origin, destination, date)
    return f"{r['airline']} {r['flight']}: ${r['price']}, {r['duration']}, departs {r['departs']}"

@tool
def search_hotels(city: str, checkin: str, checkout: str) -> str:
    """Search for hotels in a city for given check-in and check-out dates."""
    r = search_hotels_fn(city, checkin, checkout)
    return f"{r['name']} ({r['stars']}★): ${r['price']}/night, {r['cancellation']} cancellation"

@tool
def get_weather(city: str, date: str) -> str:
    """Get weather forecast for a city on a specific date."""
    r = get_weather_fn(city, date)
    return f"{r['forecast']}, high {r['high_f']}°F / low {r['low_f']}°F, {r['precip_pct']}% precip"

@tool
def calculate_budget(flight_cost: float, hotel_cost: float, days: int) -> str:
    """Calculate total trip budget from flight cost, nightly hotel rate, and number of days."""
    r = calculate_budget_fn(flight_cost, hotel_cost, days)
    return f"Total: ${r['total']} ({r['breakdown']})"


# ── ReWOO: structured plan types ──────────────────────────────────────────────

class PlanStep(BaseModel):
    evidence_id: str           # "E1", "E2", ... — used as placeholder keys
    description: str           # human-readable step summary
    tool_name: str             # must match a key in TOOL_REGISTRY
    arguments: dict[str, str]  # arg values may be "#En" or "#En.field" references

class ExecutionPlan(BaseModel):
    reasoning: str             # why this sequence of steps
    steps: list[PlanStep]


# ── ReWOO: prompts ────────────────────────────────────────────────────────────

PLANNER_PROMPT = """You are a trip planning orchestrator.

Given a task, produce a step-by-step execution plan using the available tools.
DO NOT execute any tools yourself — plan only.

Rules:
- Assign each step an evidence ID: E1, E2, E3, ...
- If a step needs output from a prior step, use "#En" or "#En.field_name" as the argument value
- Use exact argument names as listed in the tool signatures

Available tools:
  search_flights(origin, destination, date)
    → returns: {price, airline, flight, duration, departs}

  search_hotels(city, checkin, checkout)
    → returns: {price, name, stars, cancellation}

  get_weather(city, date)
    → returns: {forecast, high_f, low_f, precip_pct}

  calculate_budget(flight_cost, hotel_cost, days)
    → returns: {total, breakdown}
    NOTE: flight_cost = #En.price, hotel_cost = #En.price, days = integer string
"""

SYNTHESIZER_PROMPT = """You are a travel advisor.
You will receive a trip planning task and all the evidence gathered by an automated research pipeline.
Synthesize it into a clear, helpful recommendation covering: flight, hotel, weather and budget.
Be concise — the user wants actionable advice, not a recap of the data."""


# ── ReWOO: placeholder resolver ───────────────────────────────────────────────

def resolve_arg(value: str, results: dict):
    """
    Resolve argument values that may be:
      - A literal string/number: return as-is (coercing to int/float if numeric)
      - "#En"        → the full result dict/value for step En
      - "#En.field"  → a specific field from step En's result dict
    """
    if not isinstance(value, str) or not value.startswith("#"):
        try:
            return int(value) if str(value).isdigit() else float(value)
        except (ValueError, TypeError):
            return value

    parts = value.lstrip("#").split(".", 1)
    ref_id = parts[0]                       # "E1"
    result = results.get(ref_id)

    if len(parts) == 2 and isinstance(result, dict):
        return result.get(parts[1], result)  # "#E1.price" → result["price"]
    return result


# ── ReWOO: main orchestrator ──────────────────────────────────────────────────

def run_rewoo(task: str) -> str:
    llm_calls = 0

    # ── Phase 1: Plan ─────────────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("REWOO — PHASE 1: PLAN  (1 LLM call)")
    print("═" * 60)

    planner = Agent(
        model=fast_model,
        system_prompt=PLANNER_PROMPT,
        tools=[],
        callback_handler=None,
    )
    plan_result = planner(
        f"Task: {task}",
        structured_output_model=ExecutionPlan,
    )
    plan: ExecutionPlan = plan_result.structured_output
    llm_calls += 1

    print(f"Reasoning: {plan.reasoning[:150]}...")
    print(f"\nPlan ({len(plan.steps)} steps):")
    for step in plan.steps:
        print(f"  #{step.evidence_id}: {step.description}")
        print(f"    → {step.tool_name}({step.arguments})")

    # ── Phase 2: Execute ──────────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("REWOO — PHASE 2: EXECUTE  (0 LLM calls — deterministic)")
    print("═" * 60)

    results = {}
    for step in plan.steps:
        fn = TOOL_REGISTRY.get(step.tool_name)
        if fn is None:
            print(f"  #{step.evidence_id}: UNKNOWN TOOL '{step.tool_name}' — skipping")
            continue

        resolved_args = {k: resolve_arg(v, results) for k, v in step.arguments.items()}
        result = fn(**resolved_args)
        results[step.evidence_id] = result
        print(f"  #{step.evidence_id}: {step.description}")
        print(f"    ✓ {result}")

    # ── Phase 3: Synthesize ───────────────────────────────────────────────────
    print("\n" + "═" * 60)
    print("REWOO — PHASE 3: SYNTHESIZE  (1 LLM call)")
    print("═" * 60)

    evidence = "\n".join(f"  #{eid}: {res}" for eid, res in results.items())
    synthesis_prompt = (
        f"Task: {task}\n\n"
        f"Evidence gathered by the research pipeline:\n{evidence}\n\n"
        f"Provide a clear trip recommendation."
    )
    synthesizer = Agent(
        model=model,
        system_prompt=SYNTHESIZER_PROMPT,
        tools=[],
        callback_handler=None,
    )
    final = synthesizer(synthesis_prompt)
    llm_calls += 1

    print(f"\n{final}")
    print(f"\n[ReWOO: {llm_calls} LLM calls total]")
    return str(final)


# ── ReAct: standard agent for comparison ─────────────────────────────────────

def run_react(task: str) -> str:
    print("\n" + "═" * 60)
    print("REACT — Standard Agent  (N LLM calls, interleaved)")
    print("═" * 60)

    react_agent = Agent(
        model=model,
        tools=[search_flights, search_hotels, get_weather, calculate_budget],
        callback_handler=None,
    )
    result = react_agent(task)
    print(result)
    print("\n[ReAct: LLM called once per tool result — adapts mid-flight]")
    return str(result)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    task = (
        "Plan a 3-day trip from SFO to NYC starting December 15, 2024. "
        "Find the best flight, a hotel in Manhattan, check the weather forecast, "
        "and give me a total budget estimate."
    )

    rewoo_answer = run_rewoo(task)
    react_answer = run_react(task)

    print("\n" + "═" * 60)
    print("COMPARISON")
    print("═" * 60)
    print("ReWOO  │ 2 LLM calls (plan + synthesize)")
    print("       │ Audit trail: every step logged before execution starts")
    print("       │ Policy gates possible: inspect plan before running it")
    print("       │ Weakness: plan is fixed — can't adapt if a tool returns 'no results'")
    print()
    print("ReAct  │ N LLM calls (one per tool observation)")
    print("       │ Adaptive: can re-plan mid-flight based on tool results")
    print("       │ No upfront audit — decisions emerge from observations")
    print("       │ Weakness: harder to audit, more LLM cost on long task chains")
    print()
    print("Use ReWOO when: steps have clear dependencies, you need an audit trail,")
    print("               or you want to insert policy checks before execution starts.")
    print("Use ReAct when: mid-flight adaptation matters more than predictability.")
