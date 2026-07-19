"""
Probe: Does Agent.structured_output work with a system_prompt + no tools?
Need to confirm the planner agent can return a Pydantic model cleanly.
"""
from pydantic import BaseModel
from strands import Agent
from strands.models.openai import OpenAIModel
from tools import get_model

model = get_model("haiku")

class PlanStep(BaseModel):
    evidence_id: str      # "E1", "E2", etc.
    description: str
    tool_name: str
    arguments: dict[str, str]  # values may be "#E1" style references

class ExecutionPlan(BaseModel):
    reasoning: str
    steps: list[PlanStep]

planner = Agent(
    model=model,
    system_prompt="You are a planner. Given a task and a list of available tools, "
                  "produce a step-by-step execution plan. Do NOT execute tools yourself. "
                  "Just plan. Use #E1, #E2, ... as evidence IDs. "
                  "If a later step needs the result of an earlier step, "
                  "use '#E{n}' as the argument value.",
    tools=[],
    callback_handler=None,
)

task = "Plan a 3-day trip from SFO to NYC on Dec 15. Find flights, hotels, weather, and total budget."
available_tools = ["search_flights(origin, destination, date)",
                   "search_hotels(city, checkin, checkout)",
                   "get_weather(city, date)",
                   "calculate_budget(flight_cost, hotel_cost, days)"]

prompt = f"Task: {task}\n\nAvailable tools:\n" + "\n".join(f"- {t}" for t in available_tools)

print("Requesting structured plan...")
result = planner.structured_output(ExecutionPlan, prompt)
print(f"\nReasoning: {result.reasoning}")
print(f"\nSteps ({len(result.steps)}):")
for step in result.steps:
    print(f"  #{step.evidence_id}: {step.description}")
    print(f"    tool={step.tool_name}, args={step.arguments}")
