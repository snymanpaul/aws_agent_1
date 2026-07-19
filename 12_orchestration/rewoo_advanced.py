"""
Level 41 (Iteration 2): ReWOO Advanced — Policy Gates + Parallel Waves

Three patterns layered on top of Iteration 1:

  1. POLICY GATE    — inspect AND modify the plan between Phase 1 and Phase 2.
                      Can BLOCK (reject plan), INJECT (add missing required steps),
                      or MODIFY (patch argument values). This is what makes the
                      pre-execution window unique — ReAct has no equivalent moment.

  2. PARALLEL WAVES — dependency analysis groups steps into waves.
                      Steps with no cross-dependencies run concurrently via asyncio.
                      A 7-step plan with 5 independent steps runs Wave 1 in ~1s
                      instead of ~5s sequential.

  3. RICHER DOMAIN  — international travel (SFO → London): 7 tools, 3-level
                      dependency chain, forces policy injection of visa + advisory
                      checks the LLM didn't include.

Domain: corporate travel booking with compliance policy
"""
import asyncio
import re
import time
from copy import deepcopy
from dataclasses import dataclass, field
from pydantic import BaseModel
from strands import Agent
from tools import get_model

model = get_model("claude-sonnet-4")
fast_model = get_model("haiku")


# ── Domain tools ───────────────────────────────────────────────────────────────
# Each sleeps 1s to simulate network latency — makes parallel speedup visible.

def search_flights_fn(origin: str, destination: str, date: str) -> dict:
    time.sleep(1.0)
    return {"price": 890, "airline": "British Airways", "flight": "BA286",
            "duration": "10h15m", "departs": "18:45", "currency": "USD"}

def search_hotels_fn(city: str, checkin: str, checkout: str,
                     budget_per_night: str = "500") -> dict:
    time.sleep(1.0)
    capped = min(float(budget_per_night), 500)
    return {"price": min(capped, 320), "name": "The Hoxton Shoreditch",
            "stars": 4, "cancellation": "free", "currency": "USD"}

def get_weather_fn(city: str, date: str) -> dict:
    time.sleep(1.0)
    return {"forecast": "Overcast with light rain", "high_c": 8,
            "low_c": 3, "precip_pct": 70}

def get_exchange_rate_fn(from_currency: str, to_currency: str) -> dict:
    time.sleep(1.0)
    rates = {("USD", "GBP"): 0.79, ("GBP", "USD"): 1.27}
    rate = rates.get((from_currency.upper(), to_currency.upper()), 1.0)
    return {"rate": rate, "from": from_currency, "to": to_currency}

def check_travel_advisory_fn(destination: str) -> dict:
    time.sleep(1.0)
    return {"level": 1, "label": "Exercise Normal Precautions",
            "summary": "UK is safe for travel. Standard urban awareness recommended.",
            "source": "US State Department"}

def get_visa_requirements_fn(citizenship: str, destination: str) -> dict:
    time.sleep(1.0)
    visa_free = {"US": ["UK", "London", "EU", "France", "Germany", "Japan"]}
    countries = visa_free.get(citizenship.upper(), [])
    required = not any(d.lower() in destination.lower() for d in countries)
    return {"required": required,
            "note": "No visa required — US citizens enter UK visa-free up to 6 months"
                    if not required else "Visa required — apply 6 weeks in advance"}

def calculate_budget_fn(flight_cost: float, hotel_cost: float,
                        days: int, exchange_rate: float = 1.0) -> dict:
    time.sleep(1.0)
    hotel_total = float(hotel_cost) * int(days)
    subtotal_usd = float(flight_cost) + hotel_total
    subtotal_gbp = subtotal_usd * float(exchange_rate)
    return {"total_usd": subtotal_usd, "total_gbp": round(subtotal_gbp, 2),
            "breakdown": f"flights ${flight_cost} + hotel ${hotel_total} ({days}×${hotel_cost})"}

TOOL_REGISTRY = {
    "search_flights":         search_flights_fn,
    "search_hotels":          search_hotels_fn,
    "get_weather":            get_weather_fn,
    "get_exchange_rate":      get_exchange_rate_fn,
    "check_travel_advisory":  check_travel_advisory_fn,
    "get_visa_requirements":  get_visa_requirements_fn,
    "calculate_budget":       calculate_budget_fn,
}


# ── Plan types ─────────────────────────────────────────────────────────────────

class PlanStep(BaseModel):
    evidence_id: str
    description: str
    tool_name: str
    arguments: dict[str, str]

class ExecutionPlan(BaseModel):
    reasoning: str
    steps: list[PlanStep]


# ── Prompts ────────────────────────────────────────────────────────────────────

PLANNER_PROMPT = """You are a corporate travel booking orchestrator.

Given a task, produce a step-by-step execution plan using only the available tools.
DO NOT execute tools yourself — plan only.

Rules:
- Assign each step an evidence ID: E1, E2, E3, ...
- If a step needs output from a prior step, use "#En.field_name" as the argument value
- Steps with no dependencies on prior steps can reference no prior evidence IDs
- Use EXACT argument names as listed

Available tools:
  search_flights(origin, destination, date)
    → returns: {price, airline, flight, duration, departs, currency}

  search_hotels(city, checkin, checkout, budget_per_night)
    → returns: {price, name, stars, cancellation, currency}

  get_weather(city, date)
    → returns: {forecast, high_c, low_c, precip_pct}

  get_exchange_rate(from_currency, to_currency)
    → returns: {rate, from, to}

  calculate_budget(flight_cost, hotel_cost, days, exchange_rate)
    → returns: {total_usd, total_gbp, breakdown}
    NOTE: flight_cost = #En.price, hotel_cost = #En.price,
          exchange_rate = #En.rate, days = integer string
"""

SYNTHESIZER_PROMPT = """You are a corporate travel advisor.
Synthesize the research evidence into a concise trip brief covering:
flight details, accommodation, weather, currency, budget, and any compliance notes.
Flag anything the traveller must action before departure."""


# ── Placeholder resolver ───────────────────────────────────────────────────────

def resolve_arg(value: str, results: dict):
    if not isinstance(value, str) or not value.startswith("#"):
        try:
            return int(value) if str(value).isdigit() else float(value)
        except (ValueError, TypeError):
            return value
    parts = value.lstrip("#").split(".", 1)
    result = results.get(parts[0])
    if len(parts) == 2 and isinstance(result, dict):
        return result.get(parts[1], result)
    return result


# ── Wave detector ──────────────────────────────────────────────────────────────

def extract_refs(arguments: dict[str, str]) -> set[str]:
    """Return all #En evidence IDs referenced in a step's arguments."""
    refs = set()
    for v in arguments.values():
        if isinstance(v, str):
            for m in re.findall(r'#(E\d+)', v):
                refs.add(m)
    return refs

def plan_waves(steps: list[PlanStep]) -> list[list[PlanStep]]:
    """
    Topological grouping: each wave contains steps whose deps are all
    satisfied by previous waves. Steps within a wave have no deps on each other
    and can run in parallel.
    """
    resolved, remaining, waves = set(), list(steps), []
    while remaining:
        ready = [s for s in remaining if extract_refs(s.arguments).issubset(resolved)]
        if not ready:
            print(f"  ⚠ unresolvable deps in: {[s.evidence_id for s in remaining]}")
            break
        waves.append(ready)
        resolved.update(s.evidence_id for s in ready)
        remaining = [s for s in remaining if s.evidence_id not in resolved]
    return waves


# ── Policy gate ────────────────────────────────────────────────────────────────

@dataclass
class PolicyViolation:
    rule: str
    severity: str        # "block" | "inject" | "modify"
    description: str
    action_taken: str

@dataclass
class PolicyResult:
    approved: bool
    plan: ExecutionPlan
    violations: list[PolicyViolation] = field(default_factory=list)

def apply_policy(plan: ExecutionPlan, config: dict) -> PolicyResult:
    """
    Inspects the plan and applies corporate travel policy rules.
    Can BLOCK (return approved=False), INJECT new steps, or MODIFY existing args.
    Returns a (possibly modified) ExecutionPlan.
    """
    violations: list[PolicyViolation] = []
    steps = list(deepcopy(plan.steps))
    tool_names = {s.tool_name for s in steps}

    # Detect destination from the flights step
    destination = None
    for s in steps:
        if s.tool_name == "search_flights":
            destination = s.arguments.get("destination", "")
            break

    domestic_hubs = {"SFO", "LAX", "JFK", "NYC", "ORD", "ATL", "DFW", "SEA", "BOS"}
    is_international = destination and destination.upper() not in domestic_hubs

    # ── Rule 1: BLOCK blocked destinations ────────────────────────────────────
    if destination and destination.upper() in {d.upper() for d in config.get("blocked_destinations", [])}:
        violations.append(PolicyViolation(
            rule="blocked_destination", severity="block",
            description=f"'{destination}' is on the corporate blocked-travel list",
            action_taken="Plan rejected — travel requires SVP approval"
        ))
        return PolicyResult(approved=False, plan=plan, violations=violations)

    # ── Rule 2: INJECT travel advisory for international trips ─────────────────
    if is_international and "check_travel_advisory" not in tool_names:
        eid = f"E{len(steps) + 1}"
        steps.append(PlanStep(
            evidence_id=eid,
            description=f"[POLICY] Check travel advisory for {destination}",
            tool_name="check_travel_advisory",
            arguments={"destination": destination}
        ))
        violations.append(PolicyViolation(
            rule="international_advisory_required", severity="inject",
            description="Travel advisory check mandatory for all international trips",
            action_taken=f"Injected #{eid}: check_travel_advisory({destination})"
        ))

    # ── Rule 3: INJECT visa check for international trips ─────────────────────
    if is_international and "get_visa_requirements" not in tool_names:
        eid = f"E{len(steps) + 1}"
        citizenship = config.get("employee_citizenship", "US")
        steps.append(PlanStep(
            evidence_id=eid,
            description=f"[POLICY] Verify visa requirements ({citizenship} → {destination})",
            tool_name="get_visa_requirements",
            arguments={"citizenship": citizenship, "destination": destination}
        ))
        violations.append(PolicyViolation(
            rule="visa_check_required", severity="inject",
            description="Visa requirements must be verified before international travel booking",
            action_taken=f"Injected #{eid}: get_visa_requirements({citizenship}, {destination})"
        ))

    # ── Rule 4: MODIFY hotel budget cap ────────────────────────────────────────
    cap = config.get("max_hotel_per_night_usd")
    if cap:
        for step in steps:
            if step.tool_name == "search_hotels":
                raw = step.arguments.get("budget_per_night", "")
                if raw and not raw.startswith("#"):
                    try:
                        if float(raw) > cap:
                            step.arguments["budget_per_night"] = str(cap)
                            violations.append(PolicyViolation(
                                rule="hotel_budget_cap", severity="modify",
                                description=f"Requested ${raw}/night exceeds company cap ${cap}",
                                action_taken=f"Capped budget_per_night to ${cap}"
                            ))
                    except ValueError:
                        pass

    return PolicyResult(
        approved=True,
        plan=ExecutionPlan(reasoning=plan.reasoning, steps=steps),
        violations=violations
    )


# ── Async parallel executor ────────────────────────────────────────────────────

async def _run_step(step: PlanStep, results: dict) -> tuple[str, object]:
    fn = TOOL_REGISTRY.get(step.tool_name)
    if fn is None:
        return step.evidence_id, {"error": f"unknown tool: {step.tool_name}"}
    resolved = {k: resolve_arg(v, results) for k, v in step.arguments.items()}
    result = await asyncio.to_thread(fn, **resolved)
    return step.evidence_id, result

async def execute_parallel(waves: list[list[PlanStep]], results: dict) -> dict:
    total_start = time.time()
    for i, wave in enumerate(waves):
        ids = " | ".join(f"#{s.evidence_id}" for s in wave)
        print(f"\n  Wave {i + 1}  [{ids}]  — {len(wave)} step(s) in parallel")
        wave_start = time.time()

        wave_results = await asyncio.gather(*[_run_step(s, results) for s in wave])

        elapsed = time.time() - wave_start
        for eid, result in wave_results:
            results[eid] = result
            step = next(s for s in wave if s.evidence_id == eid)
            flag = "⚠" if isinstance(result, dict) and "error" in result else "✓"
            print(f"    {flag} #{eid}: {step.description}")
            print(f"       {result}")
        print(f"    ⏱  {elapsed:.2f}s")

    print(f"\n  Total execution: {time.time() - total_start:.2f}s")
    return results


# ── Sequential executor (for comparison) ──────────────────────────────────────

def execute_sequential(steps: list[PlanStep], results: dict) -> dict:
    t0 = time.time()
    for step in steps:
        fn = TOOL_REGISTRY.get(step.tool_name)
        if fn is None:
            print(f"  ✗ #{step.evidence_id}: unknown tool")
            continue
        resolved = {k: resolve_arg(v, results) for k, v in step.arguments.items()}
        result = fn(**resolved)
        results[step.evidence_id] = result
        print(f"  ✓ #{step.evidence_id}: {step.description}")
    print(f"  ⏱  {time.time() - t0:.2f}s")
    return results


# ── ReWOO Advanced orchestrator ───────────────────────────────────────────────

async def run_rewoo_advanced(task: str, policy_config: dict) -> str:

    # ── Phase 1: Plan ──────────────────────────────────────────────────────────
    print("\n" + "═" * 64)
    print("PHASE 1 — PLAN  (1 LLM call, haiku)")
    print("═" * 64)

    planner = Agent(
        model=fast_model,
        system_prompt=PLANNER_PROMPT,
        tools=[],
        callback_handler=None,
    )
    raw = planner(f"Task: {task}", structured_output_model=ExecutionPlan)
    plan: ExecutionPlan = raw.structured_output

    print(f"Reasoning: {plan.reasoning[:160]}...")
    print(f"\nLLM-generated plan ({len(plan.steps)} steps):")
    for s in plan.steps:
        deps = extract_refs(s.arguments)
        dep_str = f" [needs {', '.join(f'#{d}' for d in sorted(deps))}]" if deps else " [independent]"
        print(f"  #{s.evidence_id}: {s.description}{dep_str}")

    # ── Policy Gate ────────────────────────────────────────────────────────────
    print("\n" + "─" * 64)
    print("POLICY GATE  — inspect + modify before any tool runs")
    print("─" * 64)

    policy_result = apply_policy(plan, policy_config)

    if policy_result.violations:
        for v in policy_result.violations:
            icon = {"block": "🚫", "inject": "💉", "modify": "✏️"}.get(v.severity, "•")
            print(f"  {icon} [{v.severity.upper()}] {v.rule}")
            print(f"     Reason: {v.description}")
            print(f"     Action: {v.action_taken}")
    else:
        print("  ✓ No policy violations found")

    if not policy_result.approved:
        print("\n❌ PLAN BLOCKED BY POLICY — aborting execution")
        return "Travel request rejected by corporate policy."

    plan = policy_result.plan
    print(f"\nFinal plan after policy ({len(plan.steps)} steps):")
    waves = plan_waves(plan.steps)
    for i, wave in enumerate(waves):
        ids = "  |  ".join(f"#{s.evidence_id} {s.tool_name}" for s in wave)
        print(f"  Wave {i + 1}: {ids}")

    # ── Phase 2: Execute (parallel waves) ─────────────────────────────────────
    print("\n" + "═" * 64)
    print("PHASE 2 — EXECUTE  (0 LLM calls — parallel waves)")
    print("═" * 64)

    results = {}
    await execute_parallel(waves, results)

    # ── Phase 3: Synthesize ────────────────────────────────────────────────────
    print("\n" + "═" * 64)
    print("PHASE 3 — SYNTHESIZE  (1 LLM call, sonnet)")
    print("═" * 64)

    # Include policy injections in the evidence summary so synthesizer knows
    policy_notes = "\n".join(
        f"  [compliance] {v.action_taken}"
        for v in policy_result.violations
        if v.severity == "inject"
    )
    evidence = "\n".join(f"  #{eid}: {res}" for eid, res in results.items())
    synthesis_prompt = (
        f"Task: {task}\n\n"
        f"Evidence gathered:\n{evidence}\n\n"
        + (f"Compliance actions taken:\n{policy_notes}\n\n" if policy_notes else "")
        + "Write a concise corporate travel brief."
    )

    synthesizer = Agent(
        model=model,
        system_prompt=SYNTHESIZER_PROMPT,
        tools=[],
        callback_handler=None,
    )
    final = synthesizer(synthesis_prompt)
    print(f"\n{final}")
    return str(final)


# ── Demo: blocked destination ─────────────────────────────────────────────────

async def demo_blocked(policy_config: dict) -> None:
    print("\n" + "═" * 64)
    print("DEMO: BLOCKED DESTINATION")
    print("═" * 64)
    blocked_task = "Book a business trip from SFO to Tehran for 3 days starting Feb 10."
    await run_rewoo_advanced(blocked_task, policy_config)


# ── Comparison: sequential vs parallel timing ──────────────────────────────────

def show_timing_comparison(plan: ExecutionPlan) -> None:
    print("\n" + "═" * 64)
    print("TIMING: sequential vs parallel (simulated 1s/tool)")
    print("═" * 64)
    waves = plan_waves(plan.steps)
    seq_time = len(plan.steps) * 1.0
    par_time = len(waves) * 1.0   # each wave takes max(tool_times) = 1s
    print(f"  Steps:       {len(plan.steps)}")
    print(f"  Waves:       {len(waves)}")
    print(f"  Sequential:  ~{seq_time:.0f}s  (one tool at a time)")
    print(f"  Parallel:    ~{par_time:.0f}s  ({len(waves)} waves × 1s max-per-wave)")
    print(f"  Speedup:     {seq_time / par_time:.1f}×")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    # Corporate travel policy
    policy_config = {
        "blocked_destinations":  ["Tehran", "Pyongyang", "Havana"],
        "max_hotel_per_night_usd": 300,
        "employee_citizenship":   "US",
    }

    task = (
        "Book a 5-day business trip from SFO to London starting January 20, 2025. "
        "Find the best flight, a hotel in central London, check the weather, "
        "get the USD/GBP exchange rate, and prepare a total budget in both currencies."
    )

    answer = await run_rewoo_advanced(task, policy_config)

    # Show what would have happened if blocked
    await demo_blocked(policy_config)

    # Show the timing math
    # (re-plan quickly with haiku just to get step count for the analysis)
    planner = Agent(model=fast_model, system_prompt=PLANNER_PROMPT, tools=[], callback_handler=None)
    raw = planner(f"Task: {task}", structured_output_model=ExecutionPlan)
    policy_result = apply_policy(raw.structured_output, policy_config)
    show_timing_comparison(policy_result.plan)

    print("\n" + "═" * 64)
    print("KEY TAKEAWAYS — what this iteration adds over rewoo.py")
    print("═" * 64)
    print("Policy gate:  the window between Phase 1 and Phase 2 is where")
    print("              you can BLOCK, INJECT, or MODIFY the plan with zero")
    print("              LLM involvement. ReAct has no equivalent moment.")
    print()
    print("Parallel:     wave detection collapses independent steps into")
    print("              concurrent execution. Critical for plans with many")
    print("              independent lookups (typical in research/retrieval tasks).")
    print()
    print("Compliance:   injected steps appear in synthesis evidence — the")
    print("              synthesizer 'knows' what compliance checks ran and")
    print("              can surface them in the output brief.")


if __name__ == "__main__":
    asyncio.run(main())
