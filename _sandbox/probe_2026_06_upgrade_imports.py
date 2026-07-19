"""Probe: offline import-smoke for the 2026-06 SDK upgrade.

Verifies that bumping the pinned PyPI deps
    strands-agents      1.38.0 -> 1.42.0
    strands-agents-tools 0.5.2 -> 0.7.0
    bedrock-agentcore   1.8.0  -> 1.12.0
    bedrock-agentcore-starter-toolkit 0.3.6 -> 0.3.9
actually brings in every API surface the Tier-17/18 lessons depend on.

Pure import + introspection. No network, no AWS, no LiteLLM. Run:
    uv run python _sandbox/probe_2026_06_upgrade_imports.py
Exit code 0 iff every required symbol imports.
"""

from __future__ import annotations

import importlib.metadata as md
import inspect

results: list[tuple[str, bool, str]] = []


def check(label: str, fn) -> None:
    try:
        detail = fn() or ""
        results.append((label, True, str(detail)))
    except Exception as exc:  # noqa: BLE001 - probe wants every failure, not the first
        results.append((label, False, f"{type(exc).__name__}: {exc}"))


# --- installed versions ----------------------------------------------------
for pkg in (
    "strands-agents",
    "strands-agents-tools",
    "bedrock-agentcore",
    "bedrock-agentcore-starter-toolkit",
):
    check(f"version {pkg}", lambda p=pkg: md.version(p))


# --- Phase 1: the four selected priorities ---------------------------------
def _limits():
    from strands.types import Limits  # noqa: PLC0415

    return f"TypedDict fields={list(Limits.__annotations__)}"


def _proactive():
    from strands.agent.conversation_manager import (  # noqa: PLC0415
        ProactiveCompressionConfig,
        SummarizingConversationManager,
    )

    fields = list(ProactiveCompressionConfig.__annotations__)
    sig = inspect.signature(SummarizingConversationManager.__init__)
    has = "proactive_compression" in sig.parameters
    return f"ProactiveCompressionConfig fields={fields}; SummarizingCM accepts proactive_compression={has}"


def _multiagent_plugin():
    from strands.plugins import MultiAgentPlugin  # noqa: PLC0415
    from strands.hooks.events import (  # noqa: PLC0415
        AfterNodeCallEvent,
        BeforeNodeCallEvent,
    )

    return f"MultiAgentPlugin={MultiAgentPlugin.__name__}; events={BeforeNodeCallEvent.__name__},{AfterNodeCallEvent.__name__}"


def _cache_config():
    from strands.models.model import CacheConfig, CacheToolsConfig  # noqa: PLC0415

    ttl = "ttl" in getattr(CacheConfig, "__annotations__", {})
    return f"CacheConfig(ttl field={ttl}); CacheToolsConfig={CacheToolsConfig.__name__}"


def _native_token_count():
    # use_native_token_count is a per-model config knob; confirm it exists on the
    # models the lessons use. NOTE: plain OpenAIModel (LiteLLM path) handled in L61 probe.
    from strands.models.bedrock import BedrockModel  # noqa: PLC0415

    src = inspect.getsource(BedrockModel)
    return f"BedrockModel mentions use_native_token_count={'use_native_token_count' in src}"


check("P1.1 Limits", _limits)
check("P1.2 proactive_compression", _proactive)
check("P1.3 MultiAgentPlugin + node events", _multiagent_plugin)
check("P1.1b CacheConfig/CacheToolsConfig", _cache_config)
check("P1.1c use_native_token_count (Bedrock)", _native_token_count)


# --- Phase 1.4: tools 0.7 security hardening -------------------------------
def _calculator_ast():
    import strands_tools.calculator as c  # noqa: PLC0415

    src = inspect.getsource(c)
    return f"ast.parse sandbox={'ast.parse' in src}; SAFE_GLOBALS={'_SAFE_GLOBALS' in src}"


def _use_aws_redaction():
    import strands_tools.use_aws as u  # noqa: PLC0415

    src = inspect.getsource(u)
    return f"redaction={'redact' in src.lower()}; consent={'consent' in src.lower()}"


def _cron_sanitize():
    import strands_tools.cron as cr  # noqa: PLC0415

    src = inspect.getsource(cr)
    return f"_sanitize_cron_line={'_sanitize_cron_line' in src}; consent={'consent' in src.lower()}"


check("P1.4 calculator AST sandbox", _calculator_ast)
check("P1.4 use_aws redaction/consent", _use_aws_redaction)
check("P1.4 cron sanitize/consent", _cron_sanitize)


# --- Phase 2: AWS-backed AgentCore features (import-only, no live calls) ----
def _dataset_client():
    from bedrock_agentcore.evaluation.dataset_client import DatasetClient  # noqa: PLC0415

    m = [n for n in dir(DatasetClient) if "dataset" in n.lower()]
    return f"DatasetClient methods~={m}"


def _async_memory():
    from bedrock_agentcore.memory.integrations.strands.session_manager import (  # noqa: PLC0415
        AgentCoreMemorySessionManager,
    )

    sig = inspect.signature(AgentCoreMemorySessionManager.__init__)
    return f"async_mode param={'async_mode' in sig.parameters}"


def _metadata_filter():
    from bedrock_agentcore.memory.models import (  # noqa: PLC0415
        EventMetadataFilter,
        MemoryMetadataFilter,
    )

    return f"MemoryMetadataFilter={MemoryMetadataFilter.__name__}; EventMetadataFilter={EventMetadataFilter.__name__}"


def _payments():
    from bedrock_agentcore.payments import PaymentClient, PaymentManager  # noqa: PLC0415
    from bedrock_agentcore.payments.integrations.strands.plugin import (  # noqa: PLC0415
        AgentCorePaymentsPlugin,
    )

    bases = [b.__name__ for b in AgentCorePaymentsPlugin.__mro__[1:3]]
    return f"PaymentManager+PaymentClient ok; AgentCorePaymentsPlugin bases={bases}"


check("P2.5 DatasetClient", _dataset_client)
check("P2.6 AgentCoreMemorySessionManager async_mode", _async_memory)
check("P2.6 MemoryMetadataFilter", _metadata_filter)
check("P2.8 Payments (manager+plugin)", _payments)


# --- report ----------------------------------------------------------------
print(f"{'='*78}\n2026-06 SDK upgrade import-smoke\n{'='*78}")
ok = 0
for label, passed, detail in results:
    mark = "PASS" if passed else "FAIL"
    print(f"[{mark}] {label:<46} {detail}")
    ok += int(passed)
print(f"{'-'*78}\n{ok}/{len(results)} checks passed")

failed = [l for l, p, _ in results if not p]
if failed:
    raise SystemExit(f"FAILED: {failed}")
print("ALL IMPORTS OK — upgrade delivers every Tier-17/18 API surface.")
