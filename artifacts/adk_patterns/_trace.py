"""Per-run observability: an audit-grade execution trace for any pattern.

Strands native hooks (no external collector needed). A single TraceRecorder is attached to every
Agent in a graph/swarm (walking .nodes[*].executor) and records, in order:
  - invoke.start / invoke.end   (per agent = per node execution boundary)
  - tool.start (name + input) / tool.end (status + result text)   -- each tool call + result
Each record carries a sequence number and a relative timestamp (ms). Dump to JSONL = the audit
artifact you attach to a gate decision and diff across runs.

For an OTel span tree instead, set STRANDS_OTEL=1 (see note at bottom) — mirrors 08_production/observability.py.

NOTE on reasoning capture: model-call reasoning/thinking is provider-gated; Gemini via the OpenAI-compat
proxy does not surface a separate reasoning trace, so this records the tool/node/result trace (the
auditable actions), not hidden chain-of-thought. That matches the architecture doc's Q5 caveat.
"""

import json
import os
import time

from strands.hooks import (
    HookProvider, HookRegistry,
    BeforeInvocationEvent, AfterInvocationEvent,
    BeforeToolCallEvent, AfterToolCallEvent,
)


def _agent_name(event) -> str:
    a = getattr(event, "agent", None)
    return getattr(a, "name", None) or "agent"


def _result_text(result) -> str:
    """Pull readable text out of a ToolResult dict, truncated."""
    try:
        parts = [c.get("text", "") for c in result.get("content", []) if isinstance(c, dict)]
        txt = " ".join(p for p in parts if p)
        status = result.get("status", "")
        return f"[{status}] {txt}"[:160]
    except Exception:
        return str(result)[:160]


class TraceRecorder(HookProvider):
    def __init__(self):
        self.events: list[dict] = []
        self._t0 = time.monotonic()

    def _rec(self, kind: str, **fields):
        self.events.append({"seq": len(self.events),
                            "ms": round((time.monotonic() - self._t0) * 1000),
                            "evt": kind, **fields})

    def register_hooks(self, registry: HookRegistry, **_):
        registry.add_callback(BeforeInvocationEvent, lambda e: self._rec("invoke.start", agent=_agent_name(e)))
        registry.add_callback(AfterInvocationEvent, lambda e: self._rec("invoke.end", agent=_agent_name(e)))
        registry.add_callback(BeforeToolCallEvent, lambda e: self._rec(
            "tool.start", agent=_agent_name(e),
            tool=e.tool_use.get("name"), input=e.tool_use.get("input")))
        registry.add_callback(AfterToolCallEvent, lambda e: self._rec(
            "tool.end", agent=_agent_name(e),
            tool=e.tool_use.get("name"), result=_result_text(getattr(e, "result", {}) or {})))

    # --- summary + persistence ---
    def tool_calls(self) -> int:
        return sum(1 for e in self.events if e["evt"] == "tool.start")

    def summary(self) -> str:
        kinds = {}
        for e in self.events:
            kinds[e["evt"]] = kinds.get(e["evt"], 0) + 1
        return f"{len(self.events)} events ({self.tool_calls()} tool calls)"

    def dump(self, path: str) -> str:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            for e in self.events:
                f.write(json.dumps(e) + "\n")
        return path


def instrument(obj, rec: "TraceRecorder | None"):
    """Attach `rec` to every Agent reachable from obj (Agent / Graph / Swarm / nested). No-op if rec is None."""
    if rec is None or obj is None:
        return obj
    hooks = getattr(obj, "hooks", None)
    if hooks is not None and hasattr(hooks, "add_hook"):
        try:
            hooks.add_hook(rec)
        except Exception:
            pass
    nodes = getattr(obj, "nodes", None)
    if isinstance(nodes, dict):                       # Graph / Swarm
        for n in nodes.values():
            instrument(getattr(n, "executor", None), rec)
    return obj


# OTel span tree (optional): call this once before building agents to export to an OTLP collector
# (e.g. Jaeger on :4317). Mirrors 08_production/observability.py.
def enable_otel(service_name: str = "adk-patterns"):
    from strands.telemetry import StrandsTelemetry
    t = StrandsTelemetry()
    t.setup_otlp_exporter()
    return t
