"""Split LEARNING_PLAN.md + the agentic-memory addendum into docs/levels/, one file per lesson.

Modes:
  extract   — write docs/levels/LNN-slug.md for L1-56 (from LEARNING_PLAN.md) and
              L78-87 (from LEARNING_PLAN_agentic_memory_evals.md, F1->L80, F2->L84);
              print a manifest of level -> filename.
  verify    — re-read the generated files, strip the added headers, concatenate the
              bodies and byte-compare against the original source sections.
  rewrite   — rewrite LEARNING_PLAN.md (drop detail blocks, add pointer, link table
              rows) and slim the addendum. Run only after verify passes.

Usage: uv run python _sandbox/split_learning_plan.py extract|verify|rewrite
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "LEARNING_PLAN.md"
ADDENDUM = ROOT / "LEARNING_PLAN_agentic_memory_evals.md"
OUT = ROOT / "docs" / "levels"
REFL = ROOT / ".claude" / "learnings" / "reflections"

# Code file per level, from the tier tables in LEARNING_PLAN.md.
CODE = {
    1: "01_basics/hello_agent.py", 2: "01_basics/agent_with_tools.py",
    3: "01_basics/custom_tools.py", 4: "02_intermediate/system_prompts.py",
    5: "02_intermediate/sessions.py", 6: "03_multi_agent/agents_as_tools.py",
    7: "03_multi_agent/swarm_example.py", 8: "03_multi_agent/graph_workflow.py",
    9: "04_production/mcp_integration.py", 10: "04_production/agentcore_deploy.py",
    11: "05_advanced/reflection_pattern.py", 12: "05_advanced/structured_outputs.py",
    13: "05_advanced/rag_integration.py", 14: "06_memory/longterm_memory.py",
    15: "06_memory/context_management.py", 16: "06_memory/unified_memory.py",
    17: "06_memory/graph_memory_benchmark.py", 18: "07_advanced_multiagent/debate_pattern.py",
    19: "07_advanced_multiagent/planning_agents.py", 20: "07_advanced_multiagent/meta_agents.py",
    21: "08_production/observability.py", 22: "08_production/safety_guardrails.py",
    23: "08_production/error_recovery.py", 24: "09_cutting_edge/tool_synthesis.py",
    25: "09_cutting_edge/self_improving.py", 26: "09_cutting_edge/research_agent.py",
    27: "10_production/l27agentcore/src/main.py", 28: "11_platform/sdk_advances.py",
    29: "11_platform/steering.py", 30: "11_platform/skills_plugin.py",
    31: "11_platform/workflow_pattern.py", 32: "11_platform/a2a_protocol.py",
    33: "11_platform/agentcore_policy.py", 34: "11_platform/agentcore_evaluations.py",
    35: "11_platform/evals_sdk.py", 36: "11_platform/bidi_streaming.py",
    37: "11_platform/ltm_streaming.py", 38: "11_platform/ai_functions.py",
    39: "11_platform/typescript/agent.ts", 40: "11_platform/edge_strands.py",
    41: "12_orchestration/rewoo.py", 42: "12_orchestration/reflexion.py",
    43: "12_orchestration/agent_sops.py", 44: "12_orchestration/agui_protocol.py",
    45: "12_orchestration/s3_vectors_rag.py", 46: "12_orchestration/hybrid_dag_graph.py",
    47: "12_orchestration/hitl_checkpoints.py", 48: "12_orchestration/durable_execution.py",
    49: "12_orchestration/evals_harness.py", 50: "12_orchestration/toxic_flow.py",
    51: "13_quality/evals_methodology.py", 52: "13_quality/auto_evaluator_reliability.py",
    53: "13_quality/context_engineering.py", 54: "13_quality/prompt_management.py",
    55: "13_quality/slm_routing.py", 56: "13_quality/secure_mcp.py",
    78: "06_memory/shared_agent_memory.py", 79: "06_memory/cross_session_memory.py",
    80: "14_agentcore_platform/ltm_filtered_retrieval.py", 81: "06_memory/long_horizon_memory.py",
    82: "13_state_persistence/durable_multiagent_resume.py", 83: "13_quality/trajectory_eval.py",
    84: "13_quality/goal_success_eval.py", 85: "13_quality/eval_significance.py",
    86: "tools/eval_harness.py", 87: "06_memory/memory_value_capstone.py",
}

REFL_EXCEPTIONS = {  # level -> reflection filename (naming varies)
    **{n: "levels-1-5-reflection.md" for n in range(1, 6)},
    23: "L23_error_recovery.md", 24: "L24_tool_synthesis.md",
    25: "L25_self_improving.md", 26: "L26_research_agent.md",
    **{n: "level-78-87-reflection.md" for n in range(78, 88)},
}


def slugify(title: str, maxlen: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:maxlen].rstrip("-")


def reflection_for(n: int) -> str | None:
    if n in REFL_EXCEPTIONS:
        name = REFL_EXCEPTIONS[n]
        return name if (REFL / name).exists() else None
    for p in sorted(REFL.glob(f"level-{n}-*.md")):
        return p.name
    return None


def header(n: int, title: str) -> str:
    lines = [f"# L{n:02d}: {title}", ""]
    if n in CODE:
        lines.append(f"**Code:** `{CODE[n]}`")
    refl = reflection_for(n)
    if refl:
        lines.append(f"**Reflection:** [`{refl}`](../../.claude/learnings/reflections/{refl})")
    lines.append("")
    return "\n".join(lines)


def split_sections(text: str, pattern: str) -> dict[int, tuple[str, str]]:
    """Return {level: (title, verbatim_body)} for sections opened by `pattern` headings.

    A section runs from its heading line to the next '### ' or '## ' heading.
    """
    out: dict[int, tuple[str, str]] = {}
    matches = list(re.finditer(pattern, text, flags=re.M))
    boundaries = [m.start() for m in re.finditer(r"^#{2,3} ", text, flags=re.M)] + [len(text)]
    for m in matches:
        n = int(m.group("n"))
        title = m.group("title").strip()
        end = min(b for b in boundaries if b > m.start())
        out[n] = (title, text[m.start():end])
    return out


def gather() -> dict[int, tuple[str, str]]:
    plan = PLAN.read_text()
    sections = split_sections(plan, r"^### Level (?P<n>\d+): (?P<title>.+)$")
    addendum = ADDENDUM.read_text()
    add_secs = split_sections(addendum, r"^### L(?P<n>\d+) — (?P<title>.+)$")
    # Foundations F1/F2 fold into L80/L84 (the levels that depend on them).
    fm = {
        80: re.search(r"^### F1 — .+?(?=^### )", addendum, flags=re.M | re.S),
        84: re.search(r"^### F2 — .+?(?=^---)", addendum, flags=re.M | re.S),
    }
    for n, m in fm.items():
        if m and n in add_secs:
            title, body = add_secs[n]
            add_secs[n] = (title, body.rstrip() + "\n\n## Foundation prerequisite\n\n" + m.group(0).rstrip() + "\n")
    sections.update(add_secs)
    return sections


def filename(n: int, title: str) -> str:
    return f"L{n:02d}-{slugify(title)}.md"


def extract() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for n, (title, body) in sorted(gather().items()):
        path = OUT / filename(n, title)
        path.write_text(header(n, title) + "\n" + body.rstrip() + "\n")
        print(f"L{n:02d}\t{path.relative_to(ROOT)}")


def verify() -> None:
    """Bodies in the generated files must be byte-identical to the source sections."""
    bad = 0
    for n, (title, body) in sorted(gather().items()):
        path = OUT / filename(n, title)
        if not path.exists():
            print(f"MISSING {path}")
            bad += 1
            continue
        text = path.read_text()
        marker = body.splitlines()[0]  # the original '### Level N:' / '### LNN —' heading line
        idx = text.find(marker)
        if idx < 0 or text[idx:].rstrip() != body.rstrip():
            print(f"MISMATCH L{n:02d} ({path.name})")
            bad += 1
    print("VERIFY:", "FAIL" if bad else "OK", f"({len(gather())} sections)")
    sys.exit(1 if bad else 0)


def link_tables(text: str, manifest: dict[int, str]) -> str:
    def repl(m: re.Match) -> str:
        n = int(m.group(1))
        if n in manifest:
            return f"| [{n}](docs/levels/{manifest[n]}) |"
        return m.group(0)
    return re.sub(r"^\| (\d+) \|", repl, text, flags=re.M)


def rewrite() -> None:
    manifest = {n: filename(n, t) for n, (t, _) in gather().items()}
    # add hand-assembled files (L57-77, L88-93) present on disk to the manifest
    for p in OUT.glob("L*.md"):
        n = int(p.name[1:3])
        manifest.setdefault(n, p.name)

    plan = PLAN.read_text()
    # Drop block 1: '## Level Details' .. before '## Local Development Setup'
    plan = re.sub(r"^## Level Details\n.*?(?=^## Local Development Setup)", "", plan, flags=re.M | re.S)
    # Drop block 2: '## Level Details — Proposed L41\+' .. before '## Reflection Workflow'
    plan = re.sub(r"^## Level Details — Proposed L41\+\n.*?(?=^## Reflection Workflow)", "", plan, flags=re.M | re.S)
    pointer = ("\n**Per-level detail:** one file per lesson in [`docs/levels/`](docs/levels/) "
               "(`L01` – `L93`). Level numbers in the tables below link to them.\n")
    plan = plan.replace("## Progress Tracker\n", "## Progress Tracker\n" + pointer, 1)
    plan = link_tables(plan, manifest)
    PLAN.write_text(plan)

    addendum = ADDENDUM.read_text()
    table = ["## Per-level detail (moved to docs/levels/)", ""]
    table.append("| Level | File |")
    table.append("|-------|------|")
    for n in range(78, 94):
        if n in manifest:
            table.append(f"| L{n} | [`docs/levels/{manifest[n]}`](docs/levels/{manifest[n]}) |")
    table_md = "\n".join(table) + "\n\n"
    addendum = re.sub(r"^## FOUNDATION \(do first\)\n.*?(?=^## Suggested execution order)",
                      table_md, addendum, flags=re.M | re.S)
    ADDENDUM.write_text(addendum)
    print("rewrote", PLAN.name, "and", ADDENDUM.name)


if __name__ == "__main__":
    {"extract": extract, "verify": verify, "rewrite": rewrite}[sys.argv[1]]()
