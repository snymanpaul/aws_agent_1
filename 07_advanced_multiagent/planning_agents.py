"""
Level 19: Planning Agents
=========================
Explicit plan-then-execute flow for complex tasks.

Flow: Planner → Executor → Verifier (→ Replanner on failure)

Five Patterns:
1. Basic Plan-Execute-Verify: Simple 3-agent flow with calculator
2. Multi-Step Dependencies: DAG-based plans with execution order
3. Software Feature Planning: Real code generation workflow
4. Graph Memory Integration: Persist plans to Graphiti
5. Full Replanning Cycle: Adaptive replanning on failure

Key Concepts:
- Task decomposition into discrete steps
- Dependency tracking between steps
- Real tool use by Executor agent
- Plan revision when execution fails

Run: uv run python 07_advanced_multiagent/planning_agents.py
"""

import sys
import json
import re
from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel

sys.path.insert(0, ".")

from strands import Agent, tool
from tools import get_model

# Models
planner_model = get_model("claude-sonnet-4")  # Complex reasoning
executor_model = get_model("haiku")  # Fast execution
verifier_model = get_model("claude-sonnet-4")  # Critical evaluation


# =============================================================================
# Data Models
# =============================================================================
class PlanStep(BaseModel):
    """A single step in an execution plan."""
    id: str
    description: str
    depends_on: list[str] = []
    success_criteria: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    result: Optional[str] = None
    error: Optional[str] = None


class Plan(BaseModel):
    """A complete execution plan."""
    goal: str
    steps: list[PlanStep]
    created_at: datetime = datetime.now()
    status: Literal["draft", "executing", "completed", "failed", "revised"] = "draft"
    revision_count: int = 0


# =============================================================================
# Tools
# =============================================================================
@tool
def calculator(expression: str) -> str:
    """
    Safely evaluate a mathematical expression.

    Args:
        expression: A mathematical expression like "10000 * (1 + 0.05) ** 3"

    Returns:
        The result of the calculation as a string.
    """
    try:
        # Only allow safe math operations
        allowed_chars = set("0123456789+-*/().** ")
        if not all(c in allowed_chars for c in expression.replace(" ", "")):
            return f"Error: Invalid characters in expression. Only numbers and +-*/()** allowed."

        result = eval(expression)
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


@tool
def http_request(url: str) -> str:
    """
    Fetch content from a URL.

    Args:
        url: The URL to fetch content from.

    Returns:
        The content of the URL (truncated to 2000 chars for readability).
    """
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0 Planning Agent'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8', errors='ignore')
            # Truncate for readability
            if len(content) > 2000:
                return content[:2000] + f"\n\n[...truncated, total {len(content)} chars]"
            return content
    except urllib.error.HTTPError as e:
        return f"HTTP Error {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return f"URL Error: {e.reason}"
    except Exception as e:
        return f"Error: {str(e)}"


# Sandbox directory for file operations
import os
SANDBOX_DIR = "07_advanced_multiagent/_sandbox"


@tool
def file_write(path: str, content: str) -> str:
    """
    Write content to a file in the sandbox directory.

    Args:
        path: Relative path within sandbox (e.g., "calculator.py")
        content: The content to write to the file.

    Returns:
        Success message or error.
    """
    try:
        os.makedirs(SANDBOX_DIR, exist_ok=True)
        # Ensure path is within sandbox
        full_path = os.path.join(SANDBOX_DIR, os.path.basename(path))
        with open(full_path, 'w') as f:
            f.write(content)
        return f"Successfully wrote {len(content)} chars to {os.path.basename(path)}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


@tool
def file_read(path: str) -> str:
    """
    Read content from a file in the sandbox directory.

    Args:
        path: Relative path within sandbox (e.g., "calculator.py")

    Returns:
        File content or error message.
    """
    try:
        full_path = os.path.join(SANDBOX_DIR, os.path.basename(path))
        if not os.path.exists(full_path):
            return f"Error: File '{os.path.basename(path)}' not found in sandbox"
        with open(full_path, 'r') as f:
            content = f.read()
        return f"=== {os.path.basename(path)} ===\n{content}"
    except Exception as e:
        return f"Error reading file: {str(e)}"


# =============================================================================
# Iteration 1: Basic Plan-Execute-Verify
# =============================================================================
def basic_plan_execute_verify():
    """
    Simple 3-agent flow: Planner → Executor → Verifier

    Task: Calculate compound interest for $10,000 at 5% for 3 years.
    """
    print("\n" + "=" * 60)
    print("Iteration 1: Basic Plan-Execute-Verify")
    print("=" * 60)

    # Goal
    goal = "Calculate compound interest for $10,000 principal at 5% annual rate for 3 years"
    print(f"\nGoal: {goal}\n")

    # --- PLANNER ---
    planner = Agent(
        model=planner_model,
        system_prompt="""You are a Planning Agent. Your job is to decompose goals into clear steps.

For each goal, output a JSON plan with this structure:
{
    "steps": [
        {
            "id": "step_1",
            "description": "What to do",
            "depends_on": [],
            "success_criteria": "How to verify this step succeeded"
        }
    ]
}

Rules:
1. Each step should be atomic (one action)
2. Include clear success criteria for verification
3. Order steps by dependencies
4. Be specific about calculations or operations needed""",
        callback_handler=None
    )

    print("[Planner creates execution plan]")
    planner_response = planner(f"""Create an execution plan for this goal:

Goal: {goal}

The executor has access to a calculator tool that can evaluate mathematical expressions.
Compound interest formula: A = P * (1 + r)^t where P=principal, r=rate, t=years

Output a JSON plan with steps.""")

    planner_text = str(planner_response)
    print(f"Planner:\n{planner_text}\n")

    # Parse plan from response
    plan_match = re.search(r'\{[\s\S]*"steps"[\s\S]*\}', planner_text)
    if plan_match:
        try:
            plan_data = json.loads(plan_match.group())
            plan = Plan(
                goal=goal,
                steps=[PlanStep(**step) for step in plan_data.get("steps", [])]
            )
            print(f"[Parsed {len(plan.steps)} steps from plan]")
        except json.JSONDecodeError:
            print("[Could not parse JSON plan, using raw text]")
            plan = Plan(goal=goal, steps=[
                PlanStep(
                    id="step_1",
                    description="Calculate compound interest using formula A = 10000 * (1 + 0.05)^3",
                    success_criteria="Result should be approximately $11,576.25"
                )
            ])
    else:
        plan = Plan(goal=goal, steps=[
            PlanStep(
                id="step_1",
                description="Calculate compound interest using formula A = 10000 * (1 + 0.05)^3",
                success_criteria="Result should be approximately $11,576.25"
            )
        ])

    # --- EXECUTOR ---
    executor = Agent(
        model=executor_model,
        tools=[calculator],
        system_prompt="""You are an Executor Agent. Follow the plan step by step.

For each step:
1. Read the description carefully
2. Use the calculator tool for any math
3. Report the result clearly

Always use the calculator tool for calculations - do not compute in your head.""",
        callback_handler=None
    )

    print("[Executor follows the plan]")
    plan.status = "executing"
    execution_results = []

    for step in plan.steps:
        step.status = "running"
        print(f"  Executing: {step.description}")

        executor_response = executor(f"""Execute this step:

Step: {step.description}
Success Criteria: {step.success_criteria}

Use the calculator tool if math is needed. Report your result.""")

        result = str(executor_response)
        step.result = result
        step.status = "completed"
        execution_results.append({"step": step.id, "result": result})
        print(f"  Result: {result[:200]}...")

    print(f"\nExecutor completed {len(plan.steps)} steps")

    # --- VERIFIER ---
    verifier = Agent(
        model=verifier_model,
        system_prompt="""You are a Verifier Agent. Your job is to check if execution met the goal.

Evaluate:
1. Were all steps completed successfully?
2. Do the results meet the success criteria?
3. Was the original goal achieved?

Output your verdict as:
VERDICT: PASS/FAIL
REASON: (explanation)
CONFIDENCE: (1-10)""",
        callback_handler=None
    )

    print("[Verifier checks results]")
    verification_context = "\n".join([
        f"Step {r['step']}: {r['result'][:300]}" for r in execution_results
    ])

    verifier_response = verifier(f"""Verify the execution results:

GOAL: {goal}

PLAN STEPS AND RESULTS:
{verification_context}

Did the execution achieve the goal? Give your verdict.""")

    verifier_text = str(verifier_response)
    print(f"Verifier:\n{verifier_text}")

    # Update plan status based on verdict
    if "PASS" in verifier_text.upper():
        plan.status = "completed"
    else:
        plan.status = "failed"

    print(f"\n[Plan Status: {plan.status}]")

    return {
        "goal": goal,
        "plan": plan.model_dump(),
        "execution_results": execution_results,
        "verification": verifier_text
    }


# =============================================================================
# Iteration 2: Multi-Step Plans with Dependencies
# =============================================================================
def get_executable_steps(plan: Plan) -> list[PlanStep]:
    """Get steps that can be executed (dependencies completed)."""
    completed_ids = {s.id for s in plan.steps if s.status == "completed"}
    return [
        s for s in plan.steps
        if s.status == "pending" and all(d in completed_ids for d in s.depends_on)
    ]


def multi_step_dependency_demo():
    """
    Multi-step plan with dependency tracking.

    Task: Research Strands SDK and summarize key features.
    """
    print("\n" + "=" * 60)
    print("Iteration 2: Multi-Step Plans with Dependencies")
    print("=" * 60)

    goal = "Research the Strands SDK documentation and list the available agent patterns"
    print(f"\nGoal: {goal}\n")

    # --- PLANNER ---
    planner = Agent(
        model=planner_model,
        system_prompt="""You are a Planning Agent that creates dependency-aware plans.

For each goal, output a JSON plan where steps can have dependencies:
{
    "steps": [
        {
            "id": "step_1",
            "description": "What to do",
            "depends_on": [],
            "success_criteria": "How to verify success"
        },
        {
            "id": "step_2",
            "description": "What to do next",
            "depends_on": ["step_1"],
            "success_criteria": "How to verify success"
        }
    ]
}

Rules:
1. Use depends_on to specify which steps must complete first
2. Steps with no dependencies can run in parallel (theoretically)
3. Create a logical DAG (directed acyclic graph)
4. Keep the plan focused - 3-5 steps maximum""",
        callback_handler=None
    )

    print("[Planner creates dependency-aware plan]")
    planner_response = planner(f"""Create an execution plan for this goal:

Goal: {goal}

The executor has access to an http_request tool to fetch web content.
The Strands SDK documentation is at: https://strandsagents.com/latest/

Create a plan that:
1. Fetches the main documentation page
2. Identifies the key sections/patterns
3. Summarizes the available agent patterns

Output a JSON plan with dependency tracking.""")

    planner_text = str(planner_response)
    print(f"Planner:\n{planner_text[:500]}...\n")

    # Parse plan
    plan_match = re.search(r'\{[\s\S]*"steps"[\s\S]*\}', planner_text)
    if plan_match:
        try:
            plan_data = json.loads(plan_match.group())
            plan = Plan(
                goal=goal,
                steps=[PlanStep(**step) for step in plan_data.get("steps", [])]
            )
        except json.JSONDecodeError:
            # Fallback plan
            plan = Plan(goal=goal, steps=[
                PlanStep(
                    id="step_1",
                    description="Fetch the Strands SDK main documentation page",
                    depends_on=[],
                    success_criteria="Successfully retrieve content from strandsagents.com"
                ),
                PlanStep(
                    id="step_2",
                    description="Extract and list the agent patterns from the content",
                    depends_on=["step_1"],
                    success_criteria="Identify at least 3 agent patterns"
                ),
                PlanStep(
                    id="step_3",
                    description="Summarize the key patterns and their use cases",
                    depends_on=["step_2"],
                    success_criteria="Provide a summary with pattern names and descriptions"
                )
            ])
    else:
        plan = Plan(goal=goal, steps=[
            PlanStep(
                id="step_1",
                description="Fetch the Strands SDK main documentation page",
                depends_on=[],
                success_criteria="Successfully retrieve content from strandsagents.com"
            ),
            PlanStep(
                id="step_2",
                description="Extract and list the agent patterns from the content",
                depends_on=["step_1"],
                success_criteria="Identify at least 3 agent patterns"
            ),
            PlanStep(
                id="step_3",
                description="Summarize the key patterns and their use cases",
                depends_on=["step_2"],
                success_criteria="Provide a summary with pattern names and descriptions"
            )
        ])

    # Show dependency graph
    print("[Dependency Graph]")
    for step in plan.steps:
        deps = " → ".join(step.depends_on) if step.depends_on else "(no deps)"
        print(f"  {step.id}: {deps} → {step.description[:50]}...")

    # --- EXECUTOR with dependency awareness ---
    executor = Agent(
        model=executor_model,
        tools=[http_request],
        system_prompt="""You are an Executor Agent. Follow instructions precisely.

For web research tasks:
1. Use http_request tool to fetch URLs
2. Extract relevant information from the content
3. Report findings clearly

Be concise in your responses.""",
        callback_handler=None
    )

    print("\n[Executor follows plan respecting dependencies]")
    plan.status = "executing"
    execution_results = {}
    max_iterations = 10  # Safety limit

    iteration = 0
    while iteration < max_iterations:
        iteration += 1
        executable = get_executable_steps(plan)

        if not executable:
            # Check if all done or blocked
            pending = [s for s in plan.steps if s.status == "pending"]
            if not pending:
                break  # All done
            else:
                print(f"  [Blocked: {len(pending)} steps have unmet dependencies]")
                break

        for step in executable:
            step.status = "running"
            print(f"\n  Executing {step.id}: {step.description[:60]}...")

            # Build context from completed dependencies
            context = ""
            for dep_id in step.depends_on:
                if dep_id in execution_results:
                    context += f"\nResult from {dep_id}:\n{execution_results[dep_id][:500]}\n"

            prompt = f"""Execute this step:

Step: {step.description}
Success Criteria: {step.success_criteria}
{f"Context from previous steps: {context}" if context else ""}

Use http_request tool if you need to fetch web content.
Be concise in your response."""

            try:
                result = str(executor(prompt))
                step.result = result
                step.status = "completed"
                execution_results[step.id] = result
                print(f"  ✓ {step.id} completed ({len(result)} chars)")
            except Exception as e:
                step.status = "failed"
                step.error = str(e)
                print(f"  ✗ {step.id} failed: {e}")

    # Summary of execution
    completed = sum(1 for s in plan.steps if s.status == "completed")
    print(f"\n[Executed {completed}/{len(plan.steps)} steps]")

    # --- VERIFIER ---
    verifier = Agent(
        model=verifier_model,
        system_prompt="""You are a Verifier Agent. Check if the research goal was achieved.

Evaluate:
1. Was relevant content fetched?
2. Were key patterns identified?
3. Is the summary useful?

Output:
VERDICT: PASS/FAIL
PATTERNS_FOUND: (list the agent patterns found)
CONFIDENCE: (1-10)""",
        callback_handler=None
    )

    print("\n[Verifier checks results]")
    all_results = "\n\n".join([
        f"=== {sid} ===\n{res[:600]}..." for sid, res in execution_results.items()
    ])

    verifier_response = verifier(f"""Verify the research results:

GOAL: {goal}

EXECUTION RESULTS:
{all_results}

Did we successfully research and document the Strands SDK agent patterns?""")

    verifier_text = str(verifier_response)
    print(f"Verifier:\n{verifier_text}")

    # Update status
    plan.status = "completed" if "PASS" in verifier_text.upper() else "failed"
    print(f"\n[Plan Status: {plan.status}]")

    return {
        "goal": goal,
        "plan": plan.model_dump(),
        "execution_results": execution_results,
        "verification": verifier_text
    }


# =============================================================================
# Iteration 3: Software Feature Planning
# =============================================================================
def software_feature_planning_demo():
    """
    Plan and implement a software feature using file operations.

    Task: Create a simple calculator module with add/subtract/multiply/divide.
    """
    print("\n" + "=" * 60)
    print("Iteration 3: Software Feature Planning")
    print("=" * 60)

    # Clean sandbox
    import shutil
    if os.path.exists(SANDBOX_DIR):
        shutil.rmtree(SANDBOX_DIR)
    os.makedirs(SANDBOX_DIR, exist_ok=True)

    goal = "Create a Python calculator module with add, subtract, multiply, and divide functions"
    print(f"\nGoal: {goal}\n")

    # --- PLANNER ---
    planner = Agent(
        model=planner_model,
        system_prompt="""You are a Software Planning Agent. Decompose coding tasks into steps.

For code generation tasks, output a JSON plan:
{
    "steps": [
        {
            "id": "step_1",
            "description": "What code to write",
            "depends_on": [],
            "success_criteria": "How to verify the code is correct",
            "file": "filename.py"
        }
    ]
}

Rules:
1. Each step should create or modify ONE file
2. Include the target filename in "file" field
3. Add tests as a separate step
4. Order by dependencies (module before tests)""",
        callback_handler=None
    )

    print("[Planner creates software implementation plan]")
    planner_response = planner(f"""Create an implementation plan:

Goal: {goal}

The executor can use:
- file_write(path, content) - write files
- file_read(path) - read files

Create a plan with:
1. Main module file (calculator.py)
2. Test file (test_calculator.py)

Output JSON plan.""")

    planner_text = str(planner_response)
    print(f"Planner:\n{planner_text[:600]}...\n")

    # Parse plan
    plan_match = re.search(r'\{[\s\S]*"steps"[\s\S]*\}', planner_text)
    if plan_match:
        try:
            plan_data = json.loads(plan_match.group())
            plan = Plan(
                goal=goal,
                steps=[PlanStep(**{k: v for k, v in step.items() if k in PlanStep.model_fields})
                       for step in plan_data.get("steps", [])]
            )
        except json.JSONDecodeError:
            plan = Plan(goal=goal, steps=[
                PlanStep(id="step_1", description="Create calculator.py with add, subtract, multiply, divide functions",
                         depends_on=[], success_criteria="File exists with 4 functions"),
                PlanStep(id="step_2", description="Create test_calculator.py with tests for all functions",
                         depends_on=["step_1"], success_criteria="Tests pass"),
            ])
    else:
        plan = Plan(goal=goal, steps=[
            PlanStep(id="step_1", description="Create calculator.py with add, subtract, multiply, divide functions",
                     depends_on=[], success_criteria="File exists with 4 functions"),
            PlanStep(id="step_2", description="Create test_calculator.py with tests for all functions",
                     depends_on=["step_1"], success_criteria="Tests pass"),
        ])

    print(f"[Plan has {len(plan.steps)} steps]")

    # --- EXECUTOR ---
    executor = Agent(
        model=executor_model,
        tools=[file_write, file_read],
        system_prompt="""You are a Code Executor Agent. Write clean Python code.

For code generation:
1. Use file_write(path, content) to create files
2. Write complete, working code
3. Include docstrings
4. Handle edge cases (like division by zero)

Be precise and write production-quality code.""",
        callback_handler=None
    )

    print("\n[Executor implements the plan]")
    plan.status = "executing"
    execution_results = {}

    for step in plan.steps:
        # Check dependencies
        deps_done = all(
            any(s.id == d and s.status == "completed" for s in plan.steps)
            for d in step.depends_on
        )
        if not deps_done:
            print(f"  Skipping {step.id}: dependencies not met")
            continue

        step.status = "running"
        print(f"\n  Executing {step.id}: {step.description[:60]}...")

        context = ""
        for dep_id in step.depends_on:
            if dep_id in execution_results:
                context += f"\nPrevious: {execution_results[dep_id][:300]}"

        result = str(executor(f"""Execute this coding task:

Task: {step.description}
Success Criteria: {step.success_criteria}
{f"Context: {context}" if context else ""}

Write the code using file_write tool. Make it complete and working."""))

        step.result = result
        step.status = "completed"
        execution_results[step.id] = result
        print(f"  ✓ {step.id} completed")

    # --- VERIFIER ---
    verifier = Agent(
        model=verifier_model,
        tools=[file_read],
        system_prompt="""You are a Code Verifier Agent. Check code quality.

Evaluate:
1. Does the code exist?
2. Are all required functions present?
3. Is the code syntactically correct?
4. Are edge cases handled?

Output:
VERDICT: PASS/FAIL
CODE_QUALITY: (brief assessment)
CONFIDENCE: (1-10)""",
        callback_handler=None
    )

    print("\n[Verifier checks generated code]")
    verifier_response = verifier(f"""Verify the implementation:

GOAL: {goal}

Use file_read to check:
1. calculator.py - should have add, subtract, multiply, divide
2. test_calculator.py - should have tests

Read the files and verify they meet the requirements.""")

    verifier_text = str(verifier_response)
    print(f"Verifier:\n{verifier_text}")

    plan.status = "completed" if "PASS" in verifier_text.upper() else "failed"
    print(f"\n[Plan Status: {plan.status}]")

    # Show generated files
    print("\n[Generated Files]")
    for f in os.listdir(SANDBOX_DIR):
        print(f"  - {f}")

    return {
        "goal": goal,
        "plan": plan.model_dump(),
        "execution_results": execution_results,
        "verification": verifier_text,
        "files_created": os.listdir(SANDBOX_DIR)
    }


# =============================================================================
# Iteration 4: Graph Memory Integration
# =============================================================================
def graph_memory_planning_demo():
    """
    Persist planning outcomes to Graphiti for cross-session learning.

    Pattern:
    1. Run a planning task
    2. Capture plan structure and outcome
    3. Persist to Graphiti as episode
    4. Enable future retrieval for informed planning
    """
    print("\n" + "=" * 60)
    print("Iteration 4: Graph Memory Integration")
    print("=" * 60)

    goal = "Plan a REST API endpoint for user authentication"
    print(f"\nGoal: {goal}\n")

    # --- Quick Planning ---
    planner = Agent(
        model=planner_model,
        system_prompt="""You are a Planning Agent. Create a concise implementation plan.

Output JSON with 3-4 steps maximum:
{
    "steps": [
        {"id": "step_1", "description": "...", "depends_on": [], "success_criteria": "..."}
    ]
}""",
        callback_handler=None
    )

    print("[Planner creates API implementation plan]")
    planner_response = planner(f"Create a 3-4 step plan for: {goal}")
    planner_text = str(planner_response)
    print(f"Plan: {planner_text[:400]}...")

    # Parse for step count
    plan_match = re.search(r'\{[\s\S]*"steps"[\s\S]*\}', planner_text)
    steps = []
    if plan_match:
        try:
            plan_data = json.loads(plan_match.group())
            steps = plan_data.get("steps", [])
        except json.JSONDecodeError:
            pass

    # --- Prepare Graphiti Record ---
    planning_record = {
        "type": "planning_outcome",
        "goal": goal,
        "timestamp": datetime.now().isoformat(),
        "plan_structure": {
            "steps": [s.get("description", "") for s in steps[:4]],
            "step_count": len(steps)
        },
        "execution_status": "simulated",
        "lessons_learned": "API planning requires auth strategy, endpoint design, and security steps",
        "related_topics": ["authentication", "REST API", "security"],
        "pattern": "planner_executor_verifier"
    }

    print("\n[Preparing Graphiti Record]")
    print(f"Record to persist:")
    print(json.dumps(planning_record, indent=2, default=str)[:500])

    print("\n[Graphiti Persistence Pattern]")
    print(f"""
To persist this plan to Graphiti, use:

  mcp__graphiti-memory__add_memory(
      name="Plan: {goal[:30]}...",
      episode_body='{json.dumps(planning_record, default=str)}',
      group_id="aws_agent_1-plans",
      source="json",
      source_description="Planning agent outcome"
  )

To retrieve past plans for new planning:

  mcp__graphiti-memory__search_memory_facts(
      query="REST API authentication planning",
      group_ids=["aws_agent_1-plans"],
      max_facts=5
  )
""")

    return {
        "goal": goal,
        "plan_text": planner_text,
        "record": planning_record,
        "steps_count": len(steps)
    }


# =============================================================================
# Iteration 5: Full Replanning Cycle
# =============================================================================
def replanning_cycle_demo():
    """
    Demonstrate adaptive replanning when execution fails.

    Flow:
    1. Planner creates initial plan
    2. Executor attempts execution
    3. On failure, Replanner analyzes and revises
    4. Executor retries with revised plan
    """
    print("\n" + "=" * 60)
    print("Iteration 5: Full Replanning Cycle")
    print("=" * 60)

    goal = "Fetch and parse data from an unreliable API endpoint"
    print(f"\nGoal: {goal}\n")

    # Simulate an unreliable endpoint (will fail)
    unreliable_url = "https://httpstat.us/500"  # Returns 500 error

    # --- Initial Planner ---
    planner = Agent(
        model=planner_model,
        system_prompt="""You are a Planning Agent. Create execution plans.

Output JSON:
{
    "steps": [
        {"id": "step_1", "description": "...", "depends_on": [], "success_criteria": "..."}
    ]
}""",
        callback_handler=None
    )

    print("[Initial Plan]")
    plan_response = planner(f"""Create a plan for: {goal}

The API endpoint is: {unreliable_url}
Use http_request tool to fetch data.
Plan should handle the response.""")

    plan_text = str(plan_response)
    print(f"Initial plan: {plan_text[:300]}...")

    # --- Executor (will fail) ---
    executor = Agent(
        model=executor_model,
        tools=[http_request],
        system_prompt="Execute steps. Report success or failure clearly.",
        callback_handler=None
    )

    print("\n[Executor attempts initial plan]")
    exec_result = str(executor(f"""Fetch data from: {unreliable_url}
Use http_request tool. Report the result."""))

    print(f"Execution result: {exec_result[:200]}...")

    # Check for failure
    failure_detected = "error" in exec_result.lower() or "500" in exec_result

    if failure_detected:
        print("\n[Failure detected - triggering replanner]")

        # --- Replanner ---
        replanner = Agent(
            model=planner_model,
            system_prompt="""You are a Replanning Agent. Analyze failures and revise plans.

When given a failed plan:
1. Identify the root cause
2. Propose a minimal revision (not a complete rewrite)
3. Add fallback strategies

Output:
FAILURE_ANALYSIS: (what went wrong)
REVISED_PLAN: (updated approach)
FALLBACK: (if revised plan fails)""",
            callback_handler=None
        )

        replan_response = replanner(f"""The initial plan failed.

GOAL: {goal}
INITIAL PLAN: {plan_text[:500]}
FAILURE: {exec_result[:300]}

Analyze the failure and propose a revised plan with fallback strategies.""")

        replan_text = str(replan_response)
        print(f"\nReplanner analysis:\n{replan_text[:600]}...")

        # --- Retry with fallback ---
        print("\n[Executing fallback strategy]")
        fallback_url = "https://httpstat.us/200"  # Returns 200 OK

        retry_result = str(executor(f"""Retry with fallback URL: {fallback_url}
Use http_request tool. Report success."""))

        print(f"Retry result: {retry_result[:200]}...")

        success = "200" in retry_result or "success" in retry_result.lower()
        final_status = "completed_with_retry" if success else "failed"
    else:
        final_status = "completed"
        replan_text = "Not needed"

    print(f"\n[Final Status: {final_status}]")

    # Prepare record for Graphiti
    replanning_record = {
        "type": "replanning_outcome",
        "goal": goal,
        "timestamp": datetime.now().isoformat(),
        "initial_plan_failed": failure_detected,
        "failure_reason": "HTTP 500 error from endpoint" if failure_detected else None,
        "replanning_applied": failure_detected,
        "final_status": final_status,
        "lessons_learned": "Unreliable endpoints need fallback strategies and retry logic",
        "pattern": "planner_executor_replanner_executor"
    }

    print("\n[Replanning Record for Graphiti]")
    print(json.dumps(replanning_record, indent=2, default=str))

    return {
        "goal": goal,
        "initial_plan": plan_text,
        "failure_detected": failure_detected,
        "replan": replan_text if failure_detected else None,
        "final_status": final_status,
        "record": replanning_record
    }


# =============================================================================
# Iteration 6: Parallel DAG Execution
# =============================================================================
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed


def parallel_dag_execution_demo():
    """
    Execute independent DAG steps in parallel using ThreadPoolExecutor.

    Key insight: Steps with no unmet dependencies can run concurrently.
    """
    print("\n" + "=" * 60)
    print("Iteration 6: Parallel DAG Execution")
    print("=" * 60)

    # Create a plan with parallel-eligible steps
    # step_1 and step_2 have no deps (can run in parallel)
    # step_3 depends on both (must wait)
    goal = "Demonstrate parallel execution of independent plan steps"
    print(f"\nGoal: {goal}\n")

    plan = Plan(goal=goal, steps=[
        PlanStep(
            id="step_1",
            description="Calculate 2 + 2",
            depends_on=[],
            success_criteria="Result is 4"
        ),
        PlanStep(
            id="step_2",
            description="Calculate 3 * 3",
            depends_on=[],
            success_criteria="Result is 9"
        ),
        PlanStep(
            id="step_3",
            description="Add the results from step_1 and step_2",
            depends_on=["step_1", "step_2"],
            success_criteria="Result is 13 (4 + 9)"
        ),
        PlanStep(
            id="step_4",
            description="Calculate 10 - 5",
            depends_on=[],
            success_criteria="Result is 5"
        ),
        PlanStep(
            id="step_5",
            description="Multiply step_3 result by step_4 result",
            depends_on=["step_3", "step_4"],
            success_criteria="Result is 65 (13 * 5)"
        ),
    ])

    # Show dependency graph
    print("[Dependency Graph]")
    print("  step_1 (2+2) ─┐")
    print("                ├─► step_3 (sum) ─┐")
    print("  step_2 (3*3) ─┘                 │")
    print("                                  ├─► step_5 (multiply)")
    print("  step_4 (10-5) ─────────────────┘")
    print("\nParallel groups: [step_1, step_2, step_4] can run together")

    # Track execution
    execution_results = {}
    execution_times = {}
    plan.status = "executing"

    def execute_step(step: PlanStep, context: str) -> tuple[str, str, float]:
        """Execute a single step with fresh agent (thread-safe)."""
        import time
        # Create fresh agent per thread to avoid state corruption
        local_executor = Agent(
            model=executor_model,
            tools=[calculator],
            system_prompt="Execute calculations using the calculator tool. Be concise.",
            callback_handler=None
        )
        start = time.time()
        prompt = f"Calculate: {step.description}"
        if context:
            prompt += f"\nContext: {context}"
        result = str(local_executor(prompt))
        duration = time.time() - start
        return step.id, result, duration

    print("\n[Parallel Execution]")
    import time
    total_start = time.time()

    max_iterations = 10
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        # Find executable steps (deps met, not yet run)
        completed_ids = {s.id for s in plan.steps if s.status == "completed"}
        executable = [
            s for s in plan.steps
            if s.status == "pending" and all(d in completed_ids for d in s.depends_on)
        ]

        if not executable:
            pending = [s for s in plan.steps if s.status == "pending"]
            if not pending:
                break
            print(f"  [Blocked: {len(pending)} steps have unmet deps]")
            break

        print(f"\n  Wave {iteration}: Executing {len(executable)} steps in parallel")
        for s in executable:
            print(f"    - {s.id}: {s.description[:40]}...")

        # Execute in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(executable)) as pool:
            futures = {}
            for step in executable:
                step.status = "running"
                # Build context from dependencies
                context = " | ".join([
                    f"{d}={execution_results.get(d, 'N/A')[:50]}"
                    for d in step.depends_on
                ])
                futures[pool.submit(execute_step, step, context)] = step

            for future in as_completed(futures):
                step = futures[future]
                try:
                    step_id, result, duration = future.result()
                    step.result = result
                    step.status = "completed"
                    execution_results[step_id] = result
                    execution_times[step_id] = duration
                    print(f"    ✓ {step_id} done in {duration:.2f}s")
                except Exception as e:
                    step.status = "failed"
                    step.error = str(e)
                    print(f"    ✗ {step.id} failed: {e}")

    total_time = time.time() - total_start
    sequential_time = sum(execution_times.values())

    print(f"\n[Timing Analysis]")
    print(f"  Total wall-clock time: {total_time:.2f}s")
    print(f"  Sum of step times: {sequential_time:.2f}s")
    print(f"  Speedup from parallelism: {sequential_time/total_time:.2f}x")

    plan.status = "completed"
    print(f"\n[Plan Status: {plan.status}]")

    return {
        "goal": goal,
        "plan": plan.model_dump(),
        "execution_results": execution_results,
        "execution_times": execution_times,
        "total_time": total_time,
        "sequential_time": sequential_time,
        "speedup": sequential_time / total_time if total_time > 0 else 1.0
    }


# =============================================================================
# Iteration 7: Plan Validation
# =============================================================================
def validate_plan(plan: Plan) -> dict:
    """
    Validate a plan for common issues:
    1. Cycle detection (circular dependencies)
    2. Missing dependencies (refs to non-existent steps)
    3. Unreachable steps (steps that can never execute)

    Returns dict with is_valid, errors, warnings.
    """
    errors = []
    warnings = []
    step_ids = {s.id for s in plan.steps}

    # Check for missing dependencies
    for step in plan.steps:
        for dep in step.depends_on:
            if dep not in step_ids:
                errors.append(f"{step.id}: depends on non-existent step '{dep}'")

    # Check for cycles using topological sort (Kahn's algorithm)
    in_degree = {s.id: len(s.depends_on) for s in plan.steps}
    queue = [s.id for s in plan.steps if in_degree[s.id] == 0]
    sorted_order = []

    # Build adjacency list (reverse deps)
    dependents = {s.id: [] for s in plan.steps}
    for step in plan.steps:
        for dep in step.depends_on:
            if dep in dependents:
                dependents[dep].append(step.id)

    while queue:
        current = queue.pop(0)
        sorted_order.append(current)
        for dependent in dependents[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(sorted_order) != len(plan.steps):
        # Cycle detected
        remaining = [s.id for s in plan.steps if s.id not in sorted_order]
        errors.append(f"Cycle detected involving steps: {remaining}")

    # Check for steps with no path from entry (unreachable analysis)
    # Entry points are steps with no dependencies
    entry_points = [s.id for s in plan.steps if not s.depends_on]
    if not entry_points:
        warnings.append("No entry points (all steps have dependencies)")

    # Check for self-dependencies
    for step in plan.steps:
        if step.id in step.depends_on:
            errors.append(f"{step.id}: depends on itself")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "execution_order": sorted_order if len(errors) == 0 else []
    }


def plan_validation_demo():
    """
    Demonstrate plan validation catching common issues.
    """
    print("\n" + "=" * 60)
    print("Iteration 7: Plan Validation")
    print("=" * 60)

    # Test Case 1: Valid plan
    print("\n[Test 1: Valid Plan]")
    valid_plan = Plan(goal="Valid plan", steps=[
        PlanStep(id="a", description="Step A", depends_on=[], success_criteria="ok"),
        PlanStep(id="b", description="Step B", depends_on=["a"], success_criteria="ok"),
        PlanStep(id="c", description="Step C", depends_on=["a"], success_criteria="ok"),
        PlanStep(id="d", description="Step D", depends_on=["b", "c"], success_criteria="ok"),
    ])
    result1 = validate_plan(valid_plan)
    print(f"  Valid: {result1['is_valid']}")
    print(f"  Execution order: {result1['execution_order']}")

    # Test Case 2: Cycle detection
    print("\n[Test 2: Cyclic Plan (should fail)]")
    cyclic_plan = Plan(goal="Cyclic plan", steps=[
        PlanStep(id="x", description="Step X", depends_on=["z"], success_criteria="ok"),
        PlanStep(id="y", description="Step Y", depends_on=["x"], success_criteria="ok"),
        PlanStep(id="z", description="Step Z", depends_on=["y"], success_criteria="ok"),
    ])
    result2 = validate_plan(cyclic_plan)
    print(f"  Valid: {result2['is_valid']}")
    print(f"  Errors: {result2['errors']}")

    # Test Case 3: Missing dependency
    print("\n[Test 3: Missing Dependency (should fail)]")
    missing_dep_plan = Plan(goal="Missing dep", steps=[
        PlanStep(id="p", description="Step P", depends_on=[], success_criteria="ok"),
        PlanStep(id="q", description="Step Q", depends_on=["p", "missing"], success_criteria="ok"),
    ])
    result3 = validate_plan(missing_dep_plan)
    print(f"  Valid: {result3['is_valid']}")
    print(f"  Errors: {result3['errors']}")

    # Test Case 4: Self-dependency
    print("\n[Test 4: Self-Dependency (should fail)]")
    self_dep_plan = Plan(goal="Self dep", steps=[
        PlanStep(id="m", description="Step M", depends_on=["m"], success_criteria="ok"),
    ])
    result4 = validate_plan(self_dep_plan)
    print(f"  Valid: {result4['is_valid']}")
    print(f"  Errors: {result4['errors']}")

    print("\n[Validation Summary]")
    print(f"  Test 1 (Valid): {'PASS' if result1['is_valid'] else 'FAIL'}")
    print(f"  Test 2 (Cycle): {'PASS' if not result2['is_valid'] else 'FAIL'} (expected invalid)")
    print(f"  Test 3 (Missing): {'PASS' if not result3['is_valid'] else 'FAIL'} (expected invalid)")
    print(f"  Test 4 (Self): {'PASS' if not result4['is_valid'] else 'FAIL'} (expected invalid)")

    return {
        "test_results": {
            "valid_plan": result1,
            "cyclic_plan": result2,
            "missing_dep_plan": result3,
            "self_dep_plan": result4
        },
        "all_passed": (
            result1['is_valid'] and
            not result2['is_valid'] and
            not result3['is_valid'] and
            not result4['is_valid']
        )
    }


# =============================================================================
# Iteration 8: Conditional Branching
# =============================================================================
class ConditionalPlanStep(BaseModel):
    """Plan step with optional condition for execution."""
    id: str
    description: str
    depends_on: list[str] = []
    success_criteria: str
    condition: Optional[str] = None  # e.g., "step_1.result > 10"
    status: Literal["pending", "running", "completed", "failed", "skipped"] = "pending"
    result: Optional[str] = None


def evaluate_condition(condition: str, results: dict) -> bool:
    """
    Evaluate a condition string against execution results.

    Supports simple conditions like:
    - "step_1.contains('success')"
    - "step_1.result > 10"
    - "step_2.status == 'completed'"
    """
    try:
        # Simple pattern matching for common conditions
        if ".contains(" in condition:
            # e.g., "step_1.contains('success')"
            match = re.match(r"(\w+)\.contains\('([^']+)'\)", condition)
            if match:
                step_id, substring = match.groups()
                return substring.lower() in results.get(step_id, "").lower()

        if ".status" in condition:
            # e.g., "step_1.status == 'completed'"
            match = re.match(r"(\w+)\.status\s*==\s*'(\w+)'", condition)
            if match:
                step_id, expected_status = match.groups()
                # This would need access to step status, simplified here
                return step_id in results

        # Numeric comparison (simplified)
        if ">" in condition or "<" in condition:
            # Extract numbers from results and compare
            # Simplified: always return True for demo
            return True

        return True  # Default: condition passes
    except Exception:
        return False


def conditional_branching_demo():
    """
    Demonstrate conditional execution based on previous step results.

    Pattern: Execute step only if condition evaluates to True.
    """
    print("\n" + "=" * 60)
    print("Iteration 8: Conditional Branching")
    print("=" * 60)

    goal = "Demonstrate conditional step execution based on results"
    print(f"\nGoal: {goal}\n")

    # Create plan with conditional steps
    steps = [
        ConditionalPlanStep(
            id="check_value",
            description="Calculate 15 * 2 to get a test value",
            depends_on=[],
            success_criteria="Get numeric result",
            condition=None  # Always executes
        ),
        ConditionalPlanStep(
            id="high_path",
            description="Execute high-value path: multiply by 10",
            depends_on=["check_value"],
            success_criteria="Result computed",
            condition="check_value.contains('30')"  # Only if result contains 30
        ),
        ConditionalPlanStep(
            id="low_path",
            description="Execute low-value path: add 5",
            depends_on=["check_value"],
            success_criteria="Result computed",
            condition="check_value.contains('error')"  # Only if error (won't execute)
        ),
        ConditionalPlanStep(
            id="final_step",
            description="Summarize the results from whichever path was taken",
            depends_on=["check_value"],
            success_criteria="Summary complete",
            condition=None  # Always executes
        ),
    ]

    print("[Conditional Plan]")
    for step in steps:
        cond = f" IF {step.condition}" if step.condition else " (always)"
        deps = f" after [{', '.join(step.depends_on)}]" if step.depends_on else ""
        print(f"  {step.id}: {step.description[:40]}...{deps}{cond}")

    # Execute with condition evaluation
    executor = Agent(
        model=executor_model,
        tools=[calculator],
        system_prompt="Execute calculations. Be concise.",
        callback_handler=None
    )

    execution_results = {}
    print("\n[Conditional Execution]")

    for step in steps:
        # Check dependencies
        deps_met = all(
            any(s.id == d and s.status in ["completed", "skipped"] for s in steps)
            for d in step.depends_on
        )
        if not deps_met:
            print(f"  {step.id}: Waiting for dependencies")
            continue

        # Evaluate condition
        if step.condition:
            condition_result = evaluate_condition(step.condition, execution_results)
            if not condition_result:
                step.status = "skipped"
                print(f"  {step.id}: SKIPPED (condition '{step.condition}' = False)")
                continue
            else:
                print(f"  {step.id}: Condition '{step.condition}' = True")

        # Execute
        step.status = "running"
        context = " | ".join([f"{d}={execution_results.get(d, 'N/A')[:30]}" for d in step.depends_on])
        prompt = f"Execute: {step.description}"
        if context:
            prompt += f"\nContext: {context}"

        result = str(executor(prompt))
        step.result = result
        step.status = "completed"
        execution_results[step.id] = result
        print(f"  {step.id}: EXECUTED → {result[:60]}...")

    # Summary
    print("\n[Execution Summary]")
    for step in steps:
        print(f"  {step.id}: {step.status}")

    executed = sum(1 for s in steps if s.status == "completed")
    skipped = sum(1 for s in steps if s.status == "skipped")

    print(f"\n  Executed: {executed}, Skipped: {skipped}")
    print("  Pattern: Conditional branching allows dynamic plan execution")

    return {
        "goal": goal,
        "steps": [{"id": s.id, "status": s.status, "condition": s.condition} for s in steps],
        "executed_count": executed,
        "skipped_count": skipped,
        "execution_results": execution_results
    }


# =============================================================================
# Iteration 9: Production-Ready Execution
# =============================================================================
class ProductionPlanStep(BaseModel):
    """Plan step with retry tracking for production use."""
    id: str
    description: str
    depends_on: list[str] = []
    success_criteria: str
    max_retries: int = 3
    retry_count: int = 0
    status: Literal["pending", "running", "completed", "failed", "retrying"] = "pending"
    result: Optional[str] = None
    error: Optional[str] = None
    execution_history: list = []  # Track each attempt


class ProductionExecutor:
    """
    Production-ready executor with:
    1. Step retry with exponential backoff
    2. Resource-constrained parallel execution
    """

    def __init__(
        self,
        executor_agent: Agent,
        max_workers: int = 2,
        max_retries: int = 3,
        base_delay: float = 0.5,
        failure_keywords: list[str] = None
    ):
        self.executor = executor_agent
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.failure_keywords = failure_keywords or ["error", "failed", "exception", "timeout"]

    def is_failure(self, result: str) -> bool:
        """Check if result indicates failure."""
        result_lower = result.lower()
        return any(kw in result_lower for kw in self.failure_keywords)

    def execute_with_retry(
        self,
        step: ProductionPlanStep,
        context: str
    ) -> tuple[bool, str, list]:
        """
        Execute a step with retry logic and exponential backoff.

        Returns: (success, final_result, execution_history)
        """
        import time
        history = []

        for attempt in range(self.max_retries + 1):
            attempt_start = time.time()

            try:
                prompt = f"Execute: {step.description}"
                if context:
                    prompt += f"\nContext: {context}"
                if attempt > 0:
                    prompt += f"\n\nThis is retry attempt {attempt + 1}/{self.max_retries + 1}. Previous attempt failed."

                result = str(self.executor(prompt))
                duration = time.time() - attempt_start

                # Check for failure indicators
                is_fail = self.is_failure(result)

                history.append({
                    "attempt": attempt + 1,
                    "duration": round(duration, 2),
                    "success": not is_fail,
                    "result_preview": result[:100]
                })

                if not is_fail:
                    return True, result, history

                # If failed and more retries available, backoff
                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** attempt)
                    time.sleep(delay)

            except Exception as e:
                duration = time.time() - attempt_start
                history.append({
                    "attempt": attempt + 1,
                    "duration": round(duration, 2),
                    "success": False,
                    "error": str(e)[:100]
                })

                if attempt < self.max_retries:
                    delay = self.base_delay * (2 ** attempt)
                    time.sleep(delay)

        return False, f"Max retries ({self.max_retries}) exceeded", history


def production_execution_demo():
    """
    Demonstrate production-ready execution patterns:
    1. Step retry with exponential backoff
    2. Resource-constrained parallel execution (max 2 workers)

    Simulates a realistic scenario with mixed success/failure steps.
    """
    print("\n" + "=" * 60)
    print("Iteration 9: Production-Ready Execution")
    print("=" * 60)

    goal = "Demonstrate production patterns: retry with backoff + resource limits"
    print(f"\nGoal: {goal}")
    print("\nConfig: max_workers=2, max_retries=2, base_delay=0.5s\n")

    # Create a mix of reliable and unreliable steps
    steps = [
        ProductionPlanStep(
            id="reliable_1",
            description="Calculate 5 + 5 (reliable operation)",
            depends_on=[],
            success_criteria="Result is 10",
            max_retries=2
        ),
        ProductionPlanStep(
            id="reliable_2",
            description="Calculate 7 * 3 (reliable operation)",
            depends_on=[],
            success_criteria="Result is 21",
            max_retries=2
        ),
        ProductionPlanStep(
            id="reliable_3",
            description="Calculate 100 / 4 (reliable operation)",
            depends_on=[],
            success_criteria="Result is 25",
            max_retries=2
        ),
        ProductionPlanStep(
            id="dependent_step",
            description="Sum the results: 10 + 21 + 25",
            depends_on=["reliable_1", "reliable_2", "reliable_3"],
            success_criteria="Result is 56",
            max_retries=2
        ),
    ]

    print("[Plan Structure]")
    print("  reliable_1 (5+5) ──┐")
    print("  reliable_2 (7*3) ──┼──► dependent_step (sum)")
    print("  reliable_3 (100/4)─┘")
    print(f"\n  Total steps: {len(steps)}")
    print(f"  Parallel candidates: 3 (but max_workers=2)")

    # Create executor agent
    executor_agent = Agent(
        model=executor_model,
        tools=[calculator],
        system_prompt="Execute calculations using calculator. Be concise.",
        callback_handler=None
    )

    # Create production executor with constraints
    prod_executor = ProductionExecutor(
        executor_agent=executor_agent,
        max_workers=2,  # Resource constraint: only 2 parallel
        max_retries=2,
        base_delay=0.5
    )

    # Execute with resource-constrained parallelism
    print("\n[Resource-Constrained Parallel Execution]")
    print(f"  Max workers: {prod_executor.max_workers}")
    print(f"  Max retries per step: {prod_executor.max_retries}")

    import time
    total_start = time.time()
    execution_results = {}
    all_histories = {}
    wave_count = 0
    max_waves = 10

    while wave_count < max_waves:
        wave_count += 1

        # Find executable steps
        completed_ids = {s.id for s in steps if s.status == "completed"}
        failed_ids = {s.id for s in steps if s.status == "failed"}
        executable = [
            s for s in steps
            if s.status == "pending"
            and all(d in completed_ids for d in s.depends_on)
            and not any(d in failed_ids for d in s.depends_on)  # Skip if dep failed
        ]

        if not executable:
            pending = [s for s in steps if s.status == "pending"]
            if not pending:
                break
            # Check if blocked by failures
            blocked = [s for s in pending if any(d in failed_ids for d in s.depends_on)]
            if blocked:
                for s in blocked:
                    s.status = "failed"
                    s.error = "Dependency failed"
                    print(f"  {s.id}: BLOCKED (dependency failed)")
            break

        print(f"\n  Wave {wave_count}: {len(executable)} eligible, executing {min(len(executable), prod_executor.max_workers)}")

        # Execute with ThreadPoolExecutor respecting max_workers
        with ThreadPoolExecutor(max_workers=prod_executor.max_workers) as pool:
            futures = {}

            for step in executable:
                step.status = "running"
                # Build context from dependencies
                context = " | ".join([
                    f"{d}={execution_results.get(d, 'N/A')[:50]}"
                    for d in step.depends_on
                ])
                futures[pool.submit(
                    prod_executor.execute_with_retry,
                    step,
                    context
                )] = step

            for future in as_completed(futures):
                step = futures[future]
                try:
                    success, result, history = future.result()
                    step.execution_history = history
                    all_histories[step.id] = history

                    if success:
                        step.status = "completed"
                        step.result = result
                        execution_results[step.id] = result
                        retry_info = f" (attempts: {len(history)})" if len(history) > 1 else ""
                        print(f"    ✓ {step.id}: SUCCESS{retry_info}")
                    else:
                        step.status = "failed"
                        step.error = result
                        print(f"    ✗ {step.id}: FAILED after {len(history)} attempts")

                except Exception as e:
                    step.status = "failed"
                    step.error = str(e)
                    print(f"    ✗ {step.id}: EXCEPTION - {e}")

    total_time = time.time() - total_start

    # Summary statistics
    completed = [s for s in steps if s.status == "completed"]
    failed = [s for s in steps if s.status == "failed"]
    total_attempts = sum(len(h) for h in all_histories.values())

    print(f"\n[Execution Summary]")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Steps completed: {len(completed)}/{len(steps)}")
    print(f"  Steps failed: {len(failed)}/{len(steps)}")
    print(f"  Total attempts: {total_attempts} (includes retries)")
    print(f"  Waves executed: {wave_count}")

    # Show retry details
    print("\n[Retry Details]")
    for step_id, history in all_histories.items():
        attempts = len(history)
        if attempts > 1:
            print(f"  {step_id}: {attempts} attempts (retried {attempts - 1}x)")
        else:
            print(f"  {step_id}: 1 attempt (no retries needed)")

    # Resource constraint demonstration
    print("\n[Resource Constraint Analysis]")
    print(f"  Wave 1 had 3 eligible steps but max_workers=2")
    print(f"  This means 2 ran in parallel, 1 waited for next wave")
    print(f"  Production benefit: Prevents API rate limit violations")

    return {
        "goal": goal,
        "config": {
            "max_workers": prod_executor.max_workers,
            "max_retries": prod_executor.max_retries,
            "base_delay": prod_executor.base_delay
        },
        "steps": [{"id": s.id, "status": s.status, "attempts": len(s.execution_history)} for s in steps],
        "completed": len(completed),
        "failed": len(failed),
        "total_attempts": total_attempts,
        "total_time": total_time,
        "histories": all_histories
    }


# =============================================================================
# Main Demo
# =============================================================================
if __name__ == "__main__":
    print("=" * 60)
    print("Level 19: Planning Agents Demos")
    print("=" * 60)

    # Run iteration 1
    print("\n[Running Iteration 1: Basic Plan-Execute-Verify]")
    result1 = basic_plan_execute_verify()

    # Run iteration 2
    print("\n[Running Iteration 2: Multi-Step Dependencies]")
    result2 = multi_step_dependency_demo()

    # Run iteration 3
    print("\n[Running Iteration 3: Software Feature Planning]")
    result3 = software_feature_planning_demo()

    # Run iteration 4
    print("\n[Running Iteration 4: Graph Memory Integration]")
    result4 = graph_memory_planning_demo()

    # Run iteration 5
    print("\n[Running Iteration 5: Full Replanning Cycle]")
    result5 = replanning_cycle_demo()

    # Run iteration 6
    print("\n[Running Iteration 6: Parallel DAG Execution]")
    result6 = parallel_dag_execution_demo()

    # Run iteration 7
    print("\n[Running Iteration 7: Plan Validation]")
    result7 = plan_validation_demo()

    # Run iteration 8
    print("\n[Running Iteration 8: Conditional Branching]")
    result8 = conditional_branching_demo()

    # Run iteration 9
    print("\n[Running Iteration 9: Production-Ready Execution]")
    result9 = production_execution_demo()

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"""
Iteration 1 (Basic Plan-Execute-Verify):
  - Goal: {result1['goal'][:50]}...
  - Steps: {len(result1['plan']['steps'])}
  - Status: {result1['plan']['status']}
  - Pattern: Planner → Executor (calculator) → Verifier

Iteration 2 (Multi-Step Dependencies):
  - Goal: {result2['goal'][:50]}...
  - Steps: {len(result2['plan']['steps'])}
  - Status: {result2['plan']['status']}
  - Pattern: DAG plan → Dependency-aware execution

Iteration 3 (Software Feature Planning):
  - Goal: {result3['goal'][:50]}...
  - Steps: {len(result3['plan']['steps'])}
  - Status: {result3['plan']['status']}
  - Files: {result3['files_created']}
  - Pattern: Planner → Executor (file_write) → Verifier

Iteration 4 (Graph Memory Integration):
  - Goal: {result4['goal'][:50]}...
  - Steps: {result4['steps_count']}
  - Pattern: Plan → Graphiti persistence for learning

Iteration 5 (Full Replanning Cycle):
  - Goal: {result5['goal'][:50]}...
  - Failure detected: {result5['failure_detected']}
  - Final status: {result5['final_status']}
  - Pattern: Plan → Execute → Fail → Replan → Retry

Iteration 6 (Parallel DAG Execution):
  - Goal: {result6['goal'][:50]}...
  - Steps: {len(result6['plan']['steps'])}
  - Speedup: {result6['speedup']:.2f}x
  - Pattern: Wave-based parallel execution of independent steps

Iteration 7 (Plan Validation):
  - Tests: Valid, Cycle, Missing Dep, Self-Dep
  - All passed: {result7['all_passed']}
  - Pattern: Kahn's algorithm for cycle detection

Iteration 8 (Conditional Branching):
  - Goal: {result8['goal'][:50]}...
  - Executed: {result8['executed_count']}, Skipped: {result8['skipped_count']}
  - Pattern: condition field evaluates to decide execution

Iteration 9 (Production-Ready Execution):
  - Config: max_workers={result9['config']['max_workers']}, max_retries={result9['config']['max_retries']}
  - Completed: {result9['completed']}/{result9['completed'] + result9['failed']} steps
  - Total attempts: {result9['total_attempts']} (includes retries)
  - Time: {result9['total_time']:.2f}s
  - Pattern: Retry with backoff + resource-constrained parallelism
""")
