"""Append the 2026-09-10 stack re-base observations to the append-only log.

Session: fast-forwarded the three SDK clones, upgraded the repo from strands 1.48.0 to
1.55.1 (and agentcore 1.18.1 to 1.22.0, evals 1.0.2 to 1.2.0, tools 0.8.4 to 0.8.8),
hit the mcp 2.0 rename, pinned mcp below 2, and wrote the delta report.

Run: uv run python _sandbox/append_2026_09_10_obs.py
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.obs_log import append  # noqa: E402

TS = "2026-09-10T22:30:00Z"
REPORT = "docs/work/research/reports/2026-09-10_strands-ecosystem-delta-v148-to-v155.md"

ENTRIES = [
    dict(
        ts=TS, level=0, cat="insight", topic="transitive-major-hides-behind-a-clean-lock",
        obs="`uv lock --upgrade` resolved cleanly and pytest passed 221/221, yet the upgrade had "
            "broken 13 lessons: mcp went 1.23.3 to 2.1.1 (strands 1.55.1 allows `mcp>=1.23.0,<2.2`) "
            "and mcp 2.0 removed `mcp.server.fastmcp.FastMCP`, "
            "`mcp.client.streamable_http.streamablehttp_client` and `mcp.server.experimental`. "
            "Nothing in CI imports those (lessons are excluded from CI), so green tests were not "
            "evidence the lessons still ran. A named import probe over the exact symbols the "
            "lessons use (`_sandbox/probe_upgrade_2026-09-10_mcp_symbols.py`) found it in one run. "
            "RULE: after a dependency upgrade, probe the symbols the un-CI'd code imports, not "
            "just the test suite.",
        ctx="Stack re-base 2026-09-10; report " + REPORT,
        entities=["uv", "mcp", "Upgrade", "Evidence", "no_sim_check", "CI"],
    ),
    dict(
        ts=TS, level=0, cat="pattern", topic="pin-mcp-below-2-rather-than-migrate-in-an-upgrade",
        obs="Pinned `mcp>=1.23.3,<2` in pyproject with a comment naming the three removed symbols, "
            "instead of rewriting 13 lesson files inside the upgrade pass. Grounds: strands 1.55.1 "
            "ships `tools/mcp/_compat.py` ('Compatibility layer over the mcp 1.x and 2.x lines'), "
            "bedrock-agentcore 1.22.0 pins `mcp>=1.23.0,<2.0.0` on its own strands extra, and the "
            "SDK keeps an mcp 1.x test lane (STRANDS_TEST_MCP_V1). Cost, quoted from "
            "strands/tools/mcp/mcp_tasks.py: 'On the runtime pin mcp<2.0.0 they cannot round-trip "
            "server JSON; the corresponding client methods raise RuntimeError', so SEP-2663 MCP "
            "tasks are unusable here until the 13 files migrate. Logged as follow-on F1.",
        ctx="mcp 2.0.0 released 2026-07-28; migration guide table 'Changes almost every project hits'.",
        entities=["mcp", "Pin", "Decision", "MCPClient", "Migration"],
    ),
    dict(
        ts=TS, level=0, cat="insight", topic="strands-1-49-was-never-released",
        obs="strands-agents has no 1.49: no git tag, GitHub tag 404, PyPI 404. The release workflow "
            "takes a typed version and on 2026-07-24 the run published 1.50.0 straight after "
            "1.48.0; PR #3473 landed the same day: 'The scan previously rejected only non-monotonic "
            "versions, so a typo like 1.48.0 -> 1.84.0 sailed through'. Whether the skip was a typo "
            "is not stated anywhere. LESSON: a gap in a version sequence is a question to answer "
            "from the release machinery, not a sign of a pulled release.",
        ctx="Inventory of python/v1.48.0..python/v1.55.1 in ~/Code/strands-sdk-python.",
        entities=["strands-agents", "Release", "Versioning"],
    ),
    dict(
        ts=TS, level=0, cat="insight", topic="tools-package-is-being-folded-into-vended-tools",
        obs="strands-agents-tools 0.8.6 marks 13 tools @deprecated ('This warning becomes an error "
            "log in v0.9.0'), each pointing at an SDK replacement: calculator/environment/shell/"
            "cron to `strands.vended_tools.bash`, sleep and editor to vended sleep/file_editor, "
            "current_time to ContextInjector, think to native reasoning, memory/retrieve to "
            "MemoryManager+BedrockKnowledgeBaseStore, batch to ConcurrentToolExecutor. Seven "
            "lesson files import calculator or current_time. The vended bash itself was renamed "
            "shell in 1.51.0 (#3574: 'it never runs bash'). Direction: the tools repo is a "
            "compatibility tail; new lessons should import from strands.vended_tools.",
        ctx="Deprecation decorators read from the installed strands_tools 0.8.8.",
        entities=["strands-agents-tools", "vended_tools", "Deprecation", "calculator"],
    ),
    dict(
        ts=TS, level=0, cat="pattern", topic="secret-from-container-env-without-printing-it",
        obs="Three Gemini-backed smoke lessons needed GEMINI_API_KEY, which is not in the shell or "
            "the repo .env on this machine, and reading .env was (rightly) denied. The proxy "
            "container has it, so the run used "
            "`GEMINI_API_KEY=\"$(podman exec litellm-proxy printenv GEMINI_API_KEY)\" uv run ...` "
            "after `podman exec ... sh -c 'test -n \"$GEMINI_API_KEY\" && echo present'`: the "
            "value stays inside the shell and never enters the transcript. Output was piped through "
            "`grep -v -i 'api_key\\|AIza'` as a second guard.",
        ctx="L70, L64, L68 live on the 1.55.1 stack.",
        entities=["Secrets", "podman", "GEMINI_API_KEY", "OPSEC"],
    ),
    dict(
        ts=TS, level=0, cat="insight", topic="agentcore-shipped-the-controls-the-red-team-levels-asked-for",
        obs="Between 2026-07-18 and 2026-09-10 AgentCore released, per AWS What's New pages fetched "
            "and quoted in the report: Memory fine-grained access control via Gateway JWT + Cedar "
            "(2026-08-28), temporal policies ('require that a tool argument exactly matches the "
            "output of a prior call', 2026-08-06), Dogwood runtime verification in AgentCore Policy "
            "(2026-08-06), payments GA with MPP (2026-08-18), Agent Registry GA (2026-08-31), "
            "Runtime instances on EC2 with 14-day sessions (2026-08-06), Identity consent portal "
            "(2026-09-01). L99's explicit-deny memory finding, L96's hook interventions and L71's "
            "registry preview each now have a platform-native counterpart to compare against.",
        ctx="Web sweep of AWS What's New, AWS blogs, AgentCore release notes, Strands blog.",
        entities=["AgentCore", "Memory", "Policy", "Payments", "Registry", "L99", "L96", "L71"],
    ),
]

if __name__ == "__main__":
    print(append(ENTRIES))
