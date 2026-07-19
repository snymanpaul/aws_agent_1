"""L94 probe: assert the v1.48 surface exists at RUNTIME (not just in cloned source).

Checks the tracked-feature fates from the 2026-07-18 delta report §1 against the installed
packages. Every check prints PASS/FAIL with the observed value; exits non-zero on any FAIL.
"""

import importlib.metadata as md
import typing
import warnings

FAILS: list[str] = []


def check(name: str, ok: bool, detail: str) -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
    if not ok:
        FAILS.append(name)


print("== installed versions ==")
for pkg in ("strands-agents", "strands-agents-tools", "bedrock-agentcore", "strands-agents-evals"):
    print(f"  {pkg} == {md.version(pkg)}")

# 1. StopReason literals gained "checkpoint" and "cancelled"
from strands.types.event_loop import StopReason  # noqa: E402

literals = set(typing.get_args(StopReason))
check("stop_reason.checkpoint", "checkpoint" in literals, f"literals={sorted(literals)}")
check("stop_reason.cancelled", "cancelled" in literals, "present" if "cancelled" in literals else "absent")

# 2. AgentResult has a checkpoint field
from strands.agent.agent_result import AgentResult  # noqa: E402

has_ckpt = "checkpoint" in getattr(AgentResult, "__dataclass_fields__", {}) or hasattr(AgentResult, "checkpoint")
check("AgentResult.checkpoint", has_ckpt, f"fields={list(getattr(AgentResult, '__dataclass_fields__', {}))}")

# 3. Interventions: handler hook points + actions
from strands import interventions  # noqa: E402

handler_methods = [m for m in ("before_invocation", "before_tool_call", "after_tool_call",
                               "before_model_call", "after_model_call")
                   if hasattr(interventions.InterventionHandler, m)]
check("interventions.hooks", len(handler_methods) == 5, f"found={handler_methods}")
actions = [a for a in ("Proceed", "Deny", "Guide", "Confirm", "Transform") if hasattr(interventions, a)]
check("interventions.actions", len(actions) == 5, f"found={actions}")

# 4. Memory manager importable
from strands.memory import MemoryManager  # noqa: E402

check("memory.MemoryManager", MemoryManager is not None, repr(MemoryManager))

# 5. Storage protocol + impls
from strands import storage  # noqa: E402

impls = [i for i in ("InMemoryStorage", "LocalFileStorage", "S3Storage") if hasattr(storage, i)]
check("storage.protocol", hasattr(storage, "Storage") and len(impls) == 3, f"impls={impls}")

# 6. Sandbox namespace (Docker/Ssh impls live in submodules, not re-exported at top level)
from strands.sandbox import Sandbox  # noqa: E402
from strands.sandbox.docker import DockerSandbox  # noqa: E402
from strands.sandbox.ssh import SshSandbox  # noqa: E402

check("sandbox.namespace", all((Sandbox, DockerSandbox, SshSandbox)),
      "Sandbox + docker.DockerSandbox + ssh.SshSandbox importable")

# 7. experimental.steering deprecation shim (module __getattr__: warning fires on NAME ACCESS)
with warnings.catch_warnings(record=True) as caught:
    warnings.simplefilter("always")
    from strands.experimental import steering as _steering  # noqa: E402

    _ = _steering.SteeringHandler  # access triggers the shim
    dep = any(issubclass(w.category, DeprecationWarning) for w in caught)
check("steering.deprecated", dep, f"warnings={[str(w.message)[:60] for w in caught]}")

# 8. evals classic API intact at 1.0.2
import strands_evals  # noqa: E402

evals_names = [n for n in ("Experiment", "TracedHandler", "eval_task") if hasattr(strands_evals, n)]
check("evals.classic_api", len(evals_names) == 3, f"found={evals_names}")

print(f"\n{'ALL PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}")
raise SystemExit(1 if FAILS else 0)
