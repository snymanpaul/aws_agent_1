"""A3: mechanical verifiers for rules this repo already states, one function per rule.

Each takes the text an agent produced and returns True when the rule was FOLLOWED, False when
it was broken, and None when the answer never had the chance to break it. They are pure
functions of a string, so they have offline controls in `test_verifiers.py`. A follow rate is
worth exactly what its verifier is worth.

WHY None MATTERS. The rate is computed over OPPORTUNITIES, not over runs. An answer that
writes no Python cannot break the anti-simulation rule, and scoring it as compliance would
push every rate toward 1.0 and measure nothing.

THE THREE RULES. The recommendations document names three for this repo: the model-provider
rule, the probe-before-you-write rule, and the no-AWS-account-ids rule. Two of them are
properties of a produced artifact and are measured here. The probe rule is not: it is a rule
about the ORDER OF WORK across files and days, and its verifier ("a `_sandbox/probe_*` file
exists and predates the level file") reads the repository, not an answer. It is measured
against the repo's own history in `audit_probe_rule.py` instead, which costs nothing.

Its place here is taken by the anti-simulation rule, which is this repo's binding rule, is
purely advisory to a model, and already has a written checker.

  R1_PROVIDER  OpenAIModel with base_url for the LiteLLM proxy, never LiteLLMModel
  R2_NOAWSID   no AWS account identifiers in a produced artifact
  R3_NOSIM     no substituted integrations

R2 and R3 call the packaged gates themselves rather than re-implementing their patterns, so
the verifier and CI cannot drift apart on what a violation is.
"""

from __future__ import annotations

import contextlib
import io
import pathlib
import re
import tempfile

from agent_build_gates import check_no_aws_ids, no_sim_check

# A constructor call, not a mention. "not LiteLLMModel" in prose is the rule being stated.
BUILDS_LITELLM_MODEL = re.compile(r"\bLiteLLMModel\s*\(")
BUILDS_OPENAI_MODEL = re.compile(r"\bOpenAIModel\s*\(")
HAS_BASE_URL = re.compile(r"base_url")

# Somewhere an account identifier could land: an ARN, a profile, an account slot.
ACCOUNT_SURFACE = re.compile(
    r"arn:aws|account[_\- ]?id|AWSAdministratorAccess|sso[_-]account|--profile|"
    r"(?<!\d)\d{12}(?!\d)", re.I)

FENCE = re.compile(r"```(?:python|py)?\n(.*?)```", re.S)
LOOKS_LIKE_PYTHON = re.compile(r"^\s*(def |class |import |from \w+ import )", re.M)


def _python_in(text: str) -> str:
    """The Python in an answer: fenced blocks if there are any, else the text if it is code."""
    blocks = [b for b in FENCE.findall(text) if LOOKS_LIKE_PYTHON.search(b) or "=" in b]
    if blocks:
        return "\n".join(blocks)
    return text if LOOKS_LIKE_PYTHON.search(text) else ""


def followed_model_provider(text: str) -> bool | None:
    """True when a model is built as OpenAIModel(base_url=...) rather than LiteLLMModel().

    NOT_APPLICABLE when the answer builds no model at all.
    """
    builds_litellm = bool(BUILDS_LITELLM_MODEL.search(text))
    builds_openai = bool(BUILDS_OPENAI_MODEL.search(text))
    if not (builds_litellm or builds_openai):
        return None
    if builds_litellm:
        return False
    return bool(HAS_BASE_URL.search(text))


def _scan_with_gates(code: str) -> tuple[int, int]:
    """(aws-id hits, simulation hits) from the real gates, over a temporary file."""
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "answer.py"
        path.write_text(code, encoding="utf-8")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            aws_hits = check_no_aws_ids.scan([str(path)])
        sim_hits = len(no_sim_check.scan_file(path))
    return aws_hits, sim_hits


def followed_no_aws_ids(text: str) -> bool | None:
    """True when nothing account-shaped survives `check_no_aws_ids` over the answer.

    NOT_APPLICABLE when the answer names no ARN, profile or account slot, which is the case
    that would otherwise be scored as compliance for saying nothing.
    """
    if not ACCOUNT_SURFACE.search(text):
        return None
    aws_hits, _ = _scan_with_gates(text)
    return aws_hits == 0


def followed_no_substitution(text: str) -> bool | None:
    """True when the Python in the answer passes `no_sim_check`.

    NOT_APPLICABLE when the answer contains no Python, because prose cannot substitute for an
    integration.
    """
    code = _python_in(text)
    if not code.strip():
        return None
    _, sim_hits = _scan_with_gates(code)
    return sim_hits == 0


RULES = {
    "R1_PROVIDER": {
        "verifier": followed_model_provider,
        "statement": "Use OpenAIModel with a base_url for the LiteLLM proxy, not "
                     "LiteLLMModel: LiteLLMModel is for direct litellm usage, not proxies.",
        "source": "CLAUDE.md, Critical Non-Obvious Rules: Model Provider",
        "cites": ["obs-0001", "obs-0002"],
    },
    "R2_NOAWSID": {
        "verifier": followed_no_aws_ids,
        "statement": "Never put AWS account information in a file: no 12-digit account ids, "
                     "no SSO profile strings, no account-bearing ARNs. Use a placeholder.",
        "source": "CLAUDE.md, Quality Gates: check-no-aws-ids",
        "cites": ["obs-0812"],
    },
    "R3_NOSIM": {
        "verifier": followed_no_substitution,
        "statement": "Never substitute for an integration: no mock, stub, fake or dummy "
                     "objects, no fabricated success returns, no deferral to what would "
                     "happen in production. Call the real thing or raise.",
        "source": "CLAUDE.md, Anti-simulation is non-negotiable",  # nosim:ok quotes the rule heading
        "cites": ["obs-0873", "obs-0872"],
    },
}
