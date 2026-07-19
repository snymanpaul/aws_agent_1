"""Probe: tools 0.7.0 security hardening — OFFLINE empirical verification (L22 Iter 13).

The three hardening changes the L22 extension will demonstrate are all testable
without a model, the LiteLLM proxy, or AWS:

  1. calculator AST sandbox  — parse_expression() validates the expression AST
     against an allowlist and rejects attribute-traversal sandbox escapes
     (e.g. (1).__class__.__bases__[0].__subclasses__()) before any eval.
  2. cron newline sanitization — _sanitize_cron_line() collapses CR/LF so a
     single crontab line can't smuggle extra entries.
  3. use_aws redaction — redact_sensitive_values() replaces values of known
     secret keys with "**REDACTED**"; SENSITIVE_OPERATIONS gates consent even
     for non-mutating calls that disclose secrets.

    uv run python _sandbox/probe_l22_tool_security.py

Exit 0 iff every hardening behaves as expected.
"""

from __future__ import annotations

from strands_tools.calculator import parse_expression
from strands_tools.cron import _sanitize_cron_line
from strands_tools.use_aws import (
    SENSITIVE_OPERATIONS,
    SENSITIVE_RESPONSE_KEYS,
    redact_sensitive_values,
)

checks: list[tuple[str, bool, str]] = []


def expect(label: str, cond: bool, detail: str = "") -> None:
    checks.append((label, bool(cond), detail))


# --- 1. calculator AST sandbox --------------------------------------------
ESCAPE = "(1).__class__.__bases__[0].__subclasses__()"
try:
    parse_expression(ESCAPE)
    expect("calculator rejects sandbox escape", False, "NO ValueError raised — escape allowed!")
except ValueError as e:
    expect("calculator rejects sandbox escape", True, f"ValueError: {str(e)[:60]}")
except Exception as e:  # noqa: BLE001
    # Any rejection is acceptable, but ValueError is the documented contract.
    expect("calculator rejects sandbox escape", True, f"{type(e).__name__}: {str(e)[:50]}")

try:
    val = parse_expression("2 + 3 * 4")
    expect("calculator still evaluates real math", int(val) == 14, f"2+3*4 -> {val}")
except Exception as e:  # noqa: BLE001
    expect("calculator still evaluates real math", False, f"{type(e).__name__}: {e}")

# A second escape shape: dunder attribute access on a string literal.
try:
    parse_expression("''.__class__.__mro__")
    expect("calculator rejects __mro__ traversal", False, "allowed!")
except Exception as e:  # noqa: BLE001
    expect("calculator rejects __mro__ traversal", True, f"{type(e).__name__}")


# --- 2. cron newline-injection sanitization -------------------------------
malicious = "* * * * * /usr/bin/legit\n0 0 * * * /tmp/backdoor"
clean = _sanitize_cron_line(malicious)
expect(
    "cron collapses newline injection",
    "\n" not in clean and "\r" not in clean and "backdoor" in clean,
    f"{malicious!r} -> {clean!r}",
)


# --- 3. use_aws redaction + consent gating --------------------------------
fake_response = {
    "AccessKeyId": "AKIAIOSFODNN7EXAMPLE",
    "SecretAccessKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "Credentials": {"SessionToken": "FwoGZXIvYXdz...", "Expiration": "2026-06-01"},
    "UserName": "not-secret",
}
red = redact_sensitive_values(fake_response)
expect(
    "use_aws redacts SecretAccessKey",
    red.get("SecretAccessKey") == "**REDACTED**",
    f"-> {red.get('SecretAccessKey')}",
)
expect(
    "use_aws redacts nested SessionToken",
    red["Credentials"].get("SessionToken") == "**REDACTED**",
    f"-> {red['Credentials'].get('SessionToken')}",
)
expect(
    "use_aws preserves non-secret fields",
    red.get("UserName") == "not-secret",
    f"-> {red.get('UserName')}",
)
expect(
    "use_aws defines sensitive-operation consent set",
    len(SENSITIVE_OPERATIONS) > 0,
    f"{len(SENSITIVE_OPERATIONS)} ops, e.g. {sorted(SENSITIVE_OPERATIONS)[:3]}",
)
expect(
    "use_aws defines redacted-key set",
    len(SENSITIVE_RESPONSE_KEYS) > 0,
    f"{len(SENSITIVE_RESPONSE_KEYS)} keys, e.g. {sorted(SENSITIVE_RESPONSE_KEYS)[:3]}",
)


# --- report ----------------------------------------------------------------
print(f"{'='*74}\nL22 tools-0.7.0 security hardening (offline)\n{'='*74}")
ok = 0
for label, passed, detail in checks:
    print(f"[{'PASS' if passed else 'FAIL'}] {label:<42} {detail}")
    ok += int(passed)
print(f"{'-'*74}\n{ok}/{len(checks)} checks passed")
if ok != len(checks):
    raise SystemExit("hardening verification FAILED")
print("ALL HARDENING VERIFIED — calculator AST sandbox, cron sanitize, use_aws redaction.")
