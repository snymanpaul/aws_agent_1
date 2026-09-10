"""Assert the strands 1.55.1 surface named in the release feed exists at RUNTIME.

Modelled on _sandbox/probe_l94_v148_surface.py. Every check prints PASS/FAIL with the
observed value and the script exits non-zero on any FAIL.

Run: uv run python _sandbox/probe_upgrade_2026-09-10_surface.py
"""

import importlib
import importlib.metadata as md
import inspect

FAILS: list[str] = []


def check(name: str, ok: bool, detail: str) -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    if not ok:
        FAILS.append(name)


def has(mod: str, *names: str) -> tuple[bool, str]:
    try:
        m = importlib.import_module(mod)
    except Exception as exc:  # noqa: BLE001
        return False, f"import failed: {exc!r}"
    missing = [n for n in names if not hasattr(m, n)]
    return not missing, f"{mod}: {'all present' if not missing else 'missing ' + str(missing)}"


print("== installed versions ==")
for pkg in ("strands-agents", "strands-agents-tools", "strands-agents-evals",
            "bedrock-agentcore", "mcp", "a2a-sdk"):
    print(f"  {pkg} == {md.version(pkg)}")

# 1.52 model routing: ModelRouter accepted via Agent(model=)
check("routing.ModelRouter", *has("strands.models.routing", "ModelRouter"))
check("routing.strategies", *has("strands.models.routing",
                                 "ClassifierStrategy", "FallbackStrategy", "RoutingStrategy"))
from strands.agent.agent import Agent  # noqa: E402

model_ann = str(inspect.signature(Agent.__init__).parameters["model"].annotation)
check("Agent.model accepts ModelRouter", "ModelRouter" in model_ann, model_ann)

# 1.55.1 background tasks on Agent
params = inspect.signature(Agent.__init__).parameters
check("Agent.background_tasks param", "background_tasks" in params,
      str(params.get("background_tasks", "absent")))
check("background_tasks.config", *has("strands.background_tasks", "BackgroundTasksConfig"))

# 1.53 context manager offloading strategies (public entry: Agent(context_manager=...))
check("Agent.context_manager param", "context_manager" in params,
      str(params.get("context_manager", "absent")))
check("context strategies", *has("strands._context_manager.strategies.offload",
                                 "SummarizeStrategy", "TruncateStrategy", "DropStrategy"))
check("vended ContextOffloader", *has("strands.vended_plugins.context_offloader", "ContextOffloader"))

# 1.54 FileMemoryStore (+ BedrockKnowledgeBaseStore still shipped)
check("vended FileMemoryStore", *has("strands.vended_memory_stores.file_memory_store", "FileMemoryStore"))
check("vended BedrockKnowledgeBaseStore",
      *has("strands.vended_memory_stores.bedrock_knowledge_base", "BedrockKnowledgeBaseStore"))

# 1.51 SnapshotSessionManager
check("session.SnapshotSessionManager", *has("strands.session", "SnapshotSessionManager"))

# 1.50 to 1.55 vended tools: sleep, stop, http_request, web_fetch, notebook
vt_ok, vt_detail = has("strands.vended_tools")
import strands.vended_tools as vt  # noqa: E402

vt_names = sorted(n for n in dir(vt) if not n.startswith("_"))
# web_fetch is lazy-loaded through module __getattr__ (needs the web-fetch extra);
# stop moved to experimental in 1.50 (afe34d4a9). Probe both where they live.
try:
    getattr(vt, "web_fetch")
    vt_names.append("web_fetch")
except Exception as exc:  # noqa: BLE001
    print(f"note  web_fetch lazy import failed: {exc!r}")
try:
    from strands.experimental.tools import stop as _stop  # noqa: F401
    vt_names.append("stop")
except Exception as exc:  # noqa: BLE001
    print(f"note  experimental stop import failed: {exc!r}")
want = ["sleep", "stop", "http_request", "web_fetch", "notebook"]
present = [w for w in want if any(w in n for n in vt_names)]
check("vended_tools new tools", len(present) == len(want), f"present={present} exports={vt_names}")

# 1.55 MCP SEP-2663 tasks support
check("mcp tasks module", *has("strands.tools.mcp.mcp_tasks"))

# 1.53 audio content blocks
check("types.media audio", *has("strands.types.media", "AudioContent", "AudioSource"))

# skills plugin (commit scope skills-py)
check("vended skills", *has("strands.vended_plugins.skills", "AgentSkills", "Skill"))

# 1.52 middleware stages
mw_ok, mw_detail = has("strands._middleware")
import strands._middleware as mw  # noqa: E402

mw_names = [n for n in dir(mw) if "Stage" in n]
check("middleware stages", bool(mw_names), f"exports={mw_names}")

print()
print("FAILS:", FAILS or "none")
raise SystemExit(1 if FAILS else 0)
