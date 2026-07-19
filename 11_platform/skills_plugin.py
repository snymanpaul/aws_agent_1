"""
Level 30: Skills Plugin — Progressive Disclosure for Agent Knowledge
=====================================================================
Strands SDK v1.30.x — three focused iterations.

Goal: load specialised instruction packages on-demand so agents stay lean
until they need domain expertise. Skills inject full instructions into context
only when the agent explicitly activates them.

Depends on: L28 (Plugin API), L15 (Context Management — why bloat matters)
Unlocks:    L31 (Workflow), L32 (A2A)

Three lifecycle phases:
  Discovery  — XML menu injected into system prompt (names + descriptions only)
  Activation — agent calls skills(skill_name=...) tool → full instructions loaded
  Execution  — agent follows instructions; active skill persists across turns

Skills vs Tools:
  Tools  = executable functions (read_file, send_email)
  Skills = instruction packages (how to review code, how to analyse a PDF)

vs L15 Context Management:
  L15 = manual context trimming (reactive)
  L30 = structural solution (proactive) — context stays lean until needed

Usage:
    uv run python 11_platform/skills_plugin.py

Architecture:
    Agent(plugins=[AgentSkills(skills=[...])])
         |
         v
    BeforeInvocationEvent
         |
    AgentSkills._on_before_invocation()
         |
    system_prompt += <available_skills>XML</available_skills>
         |
         v
    [LLM sees: skill names + descriptions only]
         |
         v
    LLM calls: skills(skill_name="pdf-processing")
         |
    AgentSkills.skills() tool
         |
    return full SKILL.md instructions
         |
         v
    [LLM now has full instructions — executes task]
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent, tool
from strands.vended_plugins.skills import AgentSkills, Skill
from tools import get_model

SKILLS_DIR = os.path.join(os.path.dirname(__file__), "skills")

model = get_model("haiku")


# =============================================================================
# Shared tools used across iterations
# =============================================================================

@tool
def read_file(path: str) -> str:
    """Read a file from the filesystem."""
    return f"[contents of {path}]"


@tool
def write_file(path: str, content: str) -> str:
    """Write content to a file."""
    return f"Written {len(content)} bytes to {path}"


# =============================================================================
# ITERATION 1: Inline Skill — minimal setup, understand the flow
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 1: Inline Skill — discovery → activation → execution")
print("=" * 70)
print("""
Skills are instruction packages defined as Skill(name, description, instructions).
AgentSkills(skills=[...]) wraps them as a Plugin.

Discovery:  XML block injected into system prompt — names + descriptions only.
Activation: agent calls skills(skill_name=...) → full instructions returned.
Execution:  agent follows instructions from the skill response.

The agent only loads instructions when it needs them.
The system prompt stays lean until activation.
""")

invoice_skill = Skill(
    name="invoice-processing",
    description="Extract line items, totals, and vendor info from invoice documents",
    instructions="""
# Invoice Processing Instructions

1. Identify the vendor name, invoice number, and invoice date (top of document)
2. Extract all line items: description, quantity, unit price, line total
3. Verify: sum of line totals should match the subtotal field
4. Note any taxes, discounts, or fees applied
5. Output a structured summary:
   - Vendor: ...
   - Invoice #: ...
   - Date: ...
   - Line items: [table]
   - Subtotal / Tax / Total
   - Payment terms (if stated)
""",
)

agent_inline = Agent(
    model=model,
    tools=[read_file],
    plugins=[AgentSkills(skills=[invoice_skill])],
    callback_handler=None,
)

result = agent_inline("Read and process the invoice at 'invoices/jan-2026.pdf'")
print(result)


# =============================================================================
# ITERATION 2: File-based Skills — SKILL.md on disk
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 2: File-based Skills — load from 11_platform/skills/")
print("=" * 70)
print("""
Skills stored as SKILL.md files in named directories:
  skills/pdf-processing/SKILL.md
  skills/data-analysis/SKILL.md
  skills/code-review/SKILL.md

AgentSkills(skills=["./skills/"]) scans the directory, loads all SKILL.md files.
Skill.from_directory() is called under the hood.

This is the recommended pattern for production — skills live in version
control alongside the agent code, not hardcoded in the Python file.
""")

# Show what gets loaded
loaded = Skill.from_directory(SKILLS_DIR)
print(f"Skills loaded from disk: {[s.name for s in loaded]}")
print()

agent_file = Agent(
    model=model,
    tools=[read_file, write_file],
    plugins=[AgentSkills(skills=[SKILLS_DIR])],
    callback_handler=None,
)

print("-" * 50)
print("2A: PDF task — agent should activate pdf-processing skill")
print("-" * 50)
result = agent_file("Read the file 'reports/q4-2025.pdf' and extract all tables and key facts from it.")
print(result)

print("\n" + "-" * 50)
print("2B: Code task — agent should activate code-review skill")
print("-" * 50)
result = agent_file("Read 'src/auth.py' and do a thorough code review of it.")
print(result)


# =============================================================================
# ITERATION 3: Multi-domain agent — progressive disclosure at scale
# =============================================================================
print("\n" + "=" * 70)
print("ITERATION 3: Multi-domain agent — progressive disclosure vs context bloat")
print("=" * 70)
print("""
Without skills: a multi-domain agent needs ALL domain instructions in the
system prompt upfront. 3 skills x ~300 tokens each = 900 tokens per call,
even when only one domain is needed.

With skills: system prompt carries only names + descriptions (~60 tokens total).
Full instructions (~300 tokens) loaded only for the active skill.

This is the structural solution to the context bloat problem from L15.
""")

# Mix: one inline skill + two file-based skills
excel_skill = Skill(
    name="excel-analysis",
    description="Parse and analyse Excel spreadsheets: pivot tables, formulas, named ranges",
    instructions="""
# Excel Analysis Instructions

1. Read the file and identify all sheets by name
2. For the primary data sheet:
   - List all column names and inferred data types
   - Identify any pivot tables or named ranges
   - Note formulas used and their purpose
3. Check for hidden rows/columns or protected sheets
4. Output: sheet inventory, column schema, key formulas, data summary
""",
)

multi_skills = AgentSkills(skills=[
    SKILLS_DIR,       # loads pdf-processing, data-analysis, code-review
    excel_skill,      # inline skill mixed in
])

agent_multi = Agent(
    model=model,
    tools=[read_file, write_file],
    plugins=[multi_skills],
    system_prompt="You are a versatile analyst. Use the available skills to handle any task.",
    callback_handler=None,
)

print(f"Total skills registered: {len(multi_skills.get_available_skills())}")
print(f"Skill names: {[s.name for s in multi_skills.get_available_skills()]}")
print()

print("-" * 50)
print("3A: Data analysis task")
print("-" * 50)
result = agent_multi("Analyse the dataset in 'data/sales-2025.csv' and tell me the top 3 insights.")
print(result)

print("\n" + "-" * 50)
print("3B: Show activated skills tracked in agent state")
print("-" * 50)
# Run one more task to see skill tracking
result = agent_multi("Read 'src/payments.py' and review it for security issues.")
print(result)

# Show what skills were activated across the session
activated = multi_skills.get_activated_skills(agent_multi)
print(f"\nSkills activated this session: {activated}")


print("\n" + "=" * 70)
print("L30 COMPLETE — Key Takeaways")
print("=" * 70)
print("""
1. Skills Plugin (AgentSkills)
   • Plugin subclass — registered via plugins=[AgentSkills(skills=[...])]
   • skills= accepts: Skill instances, paths to skill dirs, paths to parent dirs (mixed)
   • Injects XML discovery block into system prompt before each invocation

2. Three phases
   • Discovery:  <available_skills> XML in system prompt (lean — names + descriptions only)
   • Activation: agent calls skills(skill_name=...) tool → full instructions returned
   • Execution:  agent follows skill instructions; activation tracked in agent.state

3. SKILL.md file format
   • YAML frontmatter: name (required), description (required), allowed_tools, compatibility
   • Markdown body: the full instructions injected on activation
   • Directory name must match the skill name field

4. Skills vs Tools
   • Tools  = executable functions registered via tools=[...]
   • Skills = instruction packages registered via plugins=[AgentSkills(...)]
   • Skills can reference allowed_tools to declare their expected tool dependencies

5. vs L15 Context Management
   • L15 = reactive trimming of a bloated context
   • L30 = structural prevention — context starts lean, grows only when needed
   • At 4+ domains, skills save hundreds of tokens per call
""")
