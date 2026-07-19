"""
Level 46c: LLM as Planner, Deterministic as Executor — Safe Op Vocabulary

The deepest integration pattern: LLM decides WHAT operations to run,
deterministic code defines the safe space those operations can occupy.

The core insight — three ways to integrate LLMs into deterministic code,
ordered by safety surface:

  1. LLM writes code → validate → run           (dangerous: LLM can write anything)
  2. LLM fills slots in schema → validate → run  (L46b: typed output, still open-ended)
  3. LLM selects+configures from op vocabulary → validate+repair → run  ← THIS LEVEL

Pattern 3 is "safe by construction": the LLM cannot produce an invalid operation
type because the type doesn't exist. It can only configure what's defined.
This is the same principle as parameterized SQL queries vs. string concatenation.

Architecture:
  [LLM] plan_generator      — selects + configures ops from typed vocabulary
  [DET] plan_parser         — maps raw JSON to typed Op dataclasses
  [DET] plan_validator      — structural + semantic + safety checks
  [DET] plan_repairer       — auto-fix common LLM mistakes (wrong field names etc.)
  [DET] plan_executor       — runs each op; calls LLM only for EnrichOp steps
  [DET] audit_trail         — records before/after for every op on every record

Compare with ReWOO (L41):
  ReWOO: LLM generates arbitrary tool calls (any tool, open args) → 2-LLM-call loop
  L46c:  LLM selects from constrained vocabulary → validate+repair → single-pass exec
  Difference: safety surface and predictability, not capability
"""
import json
import re
import sys
import os
from copy import deepcopy
from dataclasses import dataclass, field, asdict
from typing import Any, Literal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent
from tools import get_model

model = get_model("haiku")


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — Operation Vocabulary
# Every op is a typed dataclass. LLM cannot invent new op types.
# Safety is structural: if the op type doesn't exist, the LLM can't use it.
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class FilterOp:
    """Keep only records where field matches condition. Drops non-matching rows."""
    op: str = "filter"
    field: str = ""
    operator: str = "eq"          # eq | ne | contains | not_empty | is_empty
    value: str = ""


@dataclass
class NormalizeOp:
    """String transformation on a field. Pure deterministic."""
    op: str = "normalize"
    field: str = ""
    transform: str = "strip"      # strip | lowercase | uppercase | title_case


@dataclass
class ValidateOp:
    """Check a constraint on a field. On failure: drop the record or flag it."""
    op: str = "validate"
    field: str = ""
    rule: str = "not_empty"       # not_empty | is_number | is_positive | is_email
    on_fail: str = "flag"         # flag | drop


@dataclass
class EnrichOp:
    """LLM generates a new field value per record from source fields."""
    op: str = "enrich"
    target_field: str = ""
    source_fields: list[str] = field(default_factory=list)
    instruction: str = ""         # what the LLM should produce


# Map op name → dataclass constructor
OP_REGISTRY: dict[str, type] = {
    "filter":    FilterOp,
    "normalize": NormalizeOp,
    "validate":  ValidateOp,
    "enrich":    EnrichOp,
}


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — Plan Generation (LLM)
# LLM receives: dataset schema + op vocabulary + user request
# LLM returns: JSON array of op specifications
# If unparseable: retry up to 3 times with error feedback
# ══════════════════════════════════════════════════════════════════════════════

PLAN_PROMPT_TEMPLATE = """\
You are a data pipeline planner. Generate a sequence of operations to fulfill the user request.

AVAILABLE OPERATIONS (use only these, no others):
  filter    — keep rows where field matches condition
              fields: field (str), operator (eq|ne|contains|not_empty|is_empty), value (str)
  normalize — apply string transform to a field
              fields: field (str), transform (strip|lowercase|uppercase|title_case)
  validate  — check a constraint; on_fail: flag (keep+mark) or drop (remove row)
              fields: field (str), rule (not_empty|is_number|is_positive|is_email), on_fail (flag|drop)
  enrich    — LLM generates a new field per record using source_fields as context
              fields: target_field (str), source_fields (list[str]), instruction (str)

DATASET SCHEMA (available fields): {schema_fields}

USER REQUEST: {user_request}

Return ONLY a JSON array. Each element has an "op" key matching one of the operation names above.
Example: [{{"op":"normalize","field":"email","transform":"lowercase"}}, ...]
No explanation. No markdown. Just the JSON array.
"""


def generate_plan(schema_fields: list[str], user_request: str,
                  max_retries: int = 3) -> list[dict]:
    """LLM generates a raw plan. Returns list of dicts (not yet validated)."""
    prompt = PLAN_PROMPT_TEMPLATE.format(
        schema_fields=", ".join(schema_fields),
        user_request=user_request,
    )
    agent = Agent(model=model, callback_handler=None)
    last_err = None

    for attempt in range(max_retries):
        if attempt > 0:
            prompt = (f"Attempt {attempt+1}. Previous error: {last_err}.\n"
                      f"Return ONLY a valid JSON array of op objects.\n\n") + prompt
        raw = str(agent(prompt))
        try:
            m = re.search(r'\[.*\]', raw, re.DOTALL)
            if not m:
                raise ValueError(f"no JSON array found in: {raw[:120]!r}")
            ops = json.loads(m.group(0))
            if not isinstance(ops, list):
                raise ValueError("expected a JSON array")
            return ops
        except (json.JSONDecodeError, ValueError) as e:
            last_err = str(e)
            print(f"    [planner] attempt {attempt+1}/{max_retries} failed: {e}")

    raise ValueError(f"plan generation failed after {max_retries} attempts: {last_err}")


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — Plan Parser, Validator, Repairer (Deterministic)
# Three separate passes before any execution touches real data.
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class PlanRepairLog:
    repairs: list[str] = field(default_factory=list)
    removals: list[str] = field(default_factory=list)

    def log_repair(self, msg: str):
        self.repairs.append(msg)
        print(f"    [repair] {msg}")

    def log_removal(self, msg: str):
        self.removals.append(msg)
        print(f"    [remove] {msg}")


def _fuzzy_field(name: str, known_fields: list[str]) -> str | None:
    """Case-insensitive field name lookup. Returns corrected name or None."""
    for f in known_fields:
        if f.lower() == name.lower():
            return f
    return None


def parse_and_repair_plan(raw_ops: list[dict], schema_fields: list[str],
                          ) -> tuple[list[Any], PlanRepairLog]:
    """
    Convert raw op dicts → typed Op dataclasses.
    Auto-repair common LLM mistakes:
      - wrong op name → skip
      - wrong field name → case-insensitive fix or skip
      - invalid enum value → substitute safe default
    Returns (typed_ops, repair_log). May return empty list if all ops invalid.
    """
    typed_ops: list[Any] = []
    log = PlanRepairLog()

    for i, raw in enumerate(raw_ops):
        op_name = raw.get("op", "").lower()

        if op_name not in OP_REGISTRY:
            log.log_removal(f"step {i+1}: unknown op {op_name!r} — removed")
            continue

        # Deep copy so we can mutate safely
        d = {k: v for k, v in raw.items() if k != "op"}

        # Fix field name references
        for field_key in ("field", "target_field"):
            if field_key in d and d[field_key]:
                fixed = _fuzzy_field(d[field_key], schema_fields)
                if fixed is None and field_key == "field":
                    log.log_removal(
                        f"step {i+1} ({op_name}): field {d[field_key]!r} not in schema — op removed")
                    d = None
                    break
                elif fixed and fixed != d[field_key]:
                    log.log_repair(
                        f"step {i+1} ({op_name}): field {d[field_key]!r} → {fixed!r}")
                    d[field_key] = fixed
        if d is None:
            continue

        # Fix source_fields in EnrichOp
        if op_name == "enrich" and "source_fields" in d:
            fixed_sources = []
            for sf in d["source_fields"]:
                f_fixed = _fuzzy_field(sf, schema_fields)
                if f_fixed:
                    fixed_sources.append(f_fixed)
                else:
                    log.log_repair(
                        f"step {i+1} (enrich): source field {sf!r} not found — dropped from sources")
            d["source_fields"] = fixed_sources

        # Safety check: validate ops can only flag/drop
        if op_name == "validate":
            if d.get("on_fail") not in ("flag", "drop"):
                log.log_repair(
                    f"step {i+1} (validate): invalid on_fail={d.get('on_fail')!r} → 'flag'")
                d["on_fail"] = "flag"

        try:
            typed_ops.append(OP_REGISTRY[op_name](op=op_name, **d))
        except TypeError as e:
            log.log_removal(f"step {i+1} ({op_name}): constructor error {e} — removed")

    return typed_ops, log


def validate_plan(ops: list[Any]) -> list[str]:
    """
    Final safety checks on the typed plan.
    Returns a list of blocking errors (empty = plan is safe to execute).
    """
    errors = []
    if not ops:
        errors.append("plan is empty after parsing/repair")
    enrich_count = sum(1 for op in ops if isinstance(op, EnrichOp))
    if enrich_count > 3:
        errors.append(f"too many EnrichOps ({enrich_count}): max 3 allowed (cost control)")
    for i, op in enumerate(ops):
        if isinstance(op, EnrichOp) and not op.instruction:
            errors.append(f"step {i+1}: EnrichOp has empty instruction")
    return errors


# ══════════════════════════════════════════════════════════════════════════════
# LAYER 4 — Plan Executor (Deterministic + LLM inside EnrichOp only)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class RecordState:
    data: dict
    flags: list[str] = field(default_factory=list)
    dropped: bool = False


@dataclass
class StepAudit:
    step: int
    op: str
    summary: str
    records_before: int
    records_after: int
    changes: list[str] = field(default_factory=list)


def _apply_filter(states: list[RecordState], op: FilterOp) -> tuple[list[RecordState], StepAudit]:
    before = sum(1 for s in states if not s.dropped)
    kept = dropped_ids = []
    changes = []

    for s in states:
        if s.dropped:
            continue
        val = str(s.data.get(op.field, ""))
        match = {
            "eq":        val == op.value,
            "ne":        val != op.value,
            "contains":  op.value.lower() in val.lower(),
            "not_empty": bool(val.strip()),
            "is_empty":  not bool(val.strip()),
        }.get(op.operator, False)

        if not match:
            s.dropped = True
            changes.append(f"  dropped id={s.data.get('id','?')} [{op.field}={val!r} failed {op.operator}={op.value!r}]")

    after = sum(1 for s in states if not s.dropped)
    audit = StepAudit(0, "filter",
                      f"filter {op.field} {op.operator} {op.value!r}: {before-after} rows dropped",
                      before, after, changes)
    return states, audit


def _apply_normalize(states: list[RecordState], op: NormalizeOp) -> tuple[list[RecordState], StepAudit]:
    transforms = {
        "strip":      str.strip,
        "lowercase":  str.lower,
        "uppercase":  str.upper,
        "title_case": str.title,
    }
    fn = transforms.get(op.transform, str.strip)
    changes = []
    for s in states:
        if s.dropped:
            continue
        old = str(s.data.get(op.field, ""))
        new = fn(old)
        if old != new:
            s.data[op.field] = new
            changes.append(f"  id={s.data.get('id','?')}: {old!r} → {new!r}")

    n = sum(1 for s in states if not s.dropped)
    audit = StepAudit(0, "normalize",
                      f"normalize {op.field} ({op.transform}): {len(changes)} changes",
                      n, n, changes)
    return states, audit


def _apply_validate(states: list[RecordState], op: ValidateOp) -> tuple[list[RecordState], StepAudit]:
    import re as _re
    rules = {
        "not_empty":  lambda v: bool(v.strip()),
        "is_number":  lambda v: bool(_re.match(r'^-?\d+(\.\d+)?$', v.strip())),
        "is_positive":lambda v: (lambda n: n is not None and n > 0)(
                                    next((float(x) for x in [_re.sub(r'[^\d.-]','',v)] if x), None)),
        "is_email":   lambda v: bool(_re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', v.strip())),
    }
    check = rules.get(op.rule, lambda v: True)
    changes = []
    before = sum(1 for s in states if not s.dropped)

    for s in states:
        if s.dropped:
            continue
        val = str(s.data.get(op.field, ""))
        if not check(val):
            if op.on_fail == "drop":
                s.dropped = True
                changes.append(f"  dropped id={s.data.get('id','?')}: {op.field}={val!r} failed {op.rule}")
            else:
                flag = f"{op.field}_invalid"
                s.flags.append(flag)
                changes.append(f"  flagged id={s.data.get('id','?')}: {op.field}={val!r} failed {op.rule}")

    after = sum(1 for s in states if not s.dropped)
    audit = StepAudit(0, "validate",
                      f"validate {op.field} ({op.rule}, on_fail={op.on_fail}): {len(changes)} violations",
                      before, after, changes)
    return states, audit


def _apply_enrich(states: list[RecordState], op: EnrichOp) -> tuple[list[RecordState], StepAudit]:
    """LLM generates a value per record. Only LLM point in the executor."""
    active = [s for s in states if not s.dropped]
    changes = []

    for s in active:
        context = {f: s.data.get(f, "") for f in op.source_fields}
        context_str = ", ".join(f"{k}={v!r}" for k, v in context.items())

        agent = Agent(model=model, callback_handler=None)
        prompt = (
            f"Record context: {context_str}\n\n"
            f"Task: {op.instruction}\n\n"
            f"Respond with ONLY the value for field '{op.target_field}'. "
            f"One sentence maximum. No explanation."
        )
        result = str(agent(prompt)).strip()
        s.data[op.target_field] = result
        changes.append(f"  id={s.data.get('id','?')}: {op.target_field}={result!r}")

    n = len(active)
    audit = StepAudit(0, "enrich",
                      f"enrich → {op.target_field} ({n} LLM calls, instruction: {op.instruction[:50]!r})",
                      n, n, changes)
    return states, audit


def execute_plan(ops: list[Any], records: list[dict]) -> tuple[list[dict], list[StepAudit]]:
    """
    Run each op in sequence against the record set.
    EnrichOp is the only point where LLM is called.
    Returns (final_records, audit_trail).
    """
    states = [RecordState(data=deepcopy(r)) for r in records]
    audit_trail: list[StepAudit] = []

    EXECUTORS = {
        "filter":    _apply_filter,
        "normalize": _apply_normalize,
        "validate":  _apply_validate,
        "enrich":    _apply_enrich,
    }

    for i, op in enumerate(ops):
        states, audit = EXECUTORS[op.op](states, op)
        audit.step = i + 1
        audit_trail.append(audit)
        print(f"  [step {i+1}] {audit.summary}")

    final = [
        {**s.data, "_flags": s.flags} if s.flags else s.data
        for s in states if not s.dropped
    ]
    return final, audit_trail


# ══════════════════════════════════════════════════════════════════════════════
# Dataset + requests
# ══════════════════════════════════════════════════════════════════════════════

DATASET = [
    {"id": 1, "name": "john SMITH",   "email": "JOHN@EXAMPLE.COM",  "company": "Acme Corp",   "status": "active",   "revenue": "45000"},
    {"id": 2, "name": "jane doe",     "email": "not-an-email",       "company": "",            "status": "inactive", "revenue": ""},
    {"id": 3, "name": "BOB JONES",    "email": "bob@widgets.io",     "company": "Widgets Inc", "status": "active",   "revenue": "-500"},
    {"id": 4, "name": "Alice Brown",  "email": "alice@startup.co",   "company": "Startup Co",  "status": "active",   "revenue": "120000"},
    {"id": 5, "name": "charlie wilson","email":"charlie@bigcorp.com", "company": "Big Corp",    "status": "churned",  "revenue": "89000"},
]

SCHEMA_FIELDS = list(DATASET[0].keys())

REQUESTS = [
    (
        "prepare for quarterly review",
        "Fix name and email formatting, keep only active customers, "
        "validate revenue is a positive number (flag don't drop), "
        "and add a one-sentence customer_summary for each record.",
    ),
    (
        "build contact list",
        "Normalize all names to title case, validate emails (drop invalid), "
        "filter out inactive and churned accounts, "
        "add a short outreach_note field suggesting a conversation opener based on company and revenue.",
    ),
]


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("L46c: LLM as Planner, Deterministic as Executor")
    print("Constrained op vocabulary — safe by construction")
    print("=" * 60)

    for label, request in REQUESTS:
        print(f"\n{'═' * 60}")
        print(f"Request: {label!r}")
        print(f"  {request}")
        print(f"{'═' * 60}")

        # ── Phase 1: LLM generates plan ───────────────────────────────────────
        print("\n[1] Generating plan...")
        try:
            raw_ops = generate_plan(SCHEMA_FIELDS, request)
            print(f"    LLM returned {len(raw_ops)} raw ops: "
                  f"{[op.get('op','?') for op in raw_ops]}")
        except ValueError as e:
            print(f"    FATAL: {e}")
            continue

        # ── Phase 2: Parse + repair ───────────────────────────────────────────
        print("\n[2] Parsing and repairing plan...")
        typed_ops, repair_log = parse_and_repair_plan(raw_ops, SCHEMA_FIELDS)
        if repair_log.repairs or repair_log.removals:
            print(f"    repairs={len(repair_log.repairs)}, removals={len(repair_log.removals)}")
        else:
            print(f"    plan clean — no repairs needed")
        print(f"    typed ops: {[type(op).__name__ for op in typed_ops]}")

        # ── Phase 3: Validate ─────────────────────────────────────────────────
        print("\n[3] Validating plan...")
        errors = validate_plan(typed_ops)
        if errors:
            print(f"    PLAN REJECTED: {errors}")
            continue
        print(f"    plan valid — {len(typed_ops)} ops approved for execution")

        # ── Phase 4: Execute ──────────────────────────────────────────────────
        print(f"\n[4] Executing plan ({len(DATASET)} records in)...")
        final_records, audit = execute_plan(typed_ops, DATASET)

        # ── Results ───────────────────────────────────────────────────────────
        print(f"\n[5] Results: {len(DATASET)} → {len(final_records)} records")
        for r in final_records:
            flags = r.pop("_flags", [])
            flag_str = f"  ⚑ {flags}" if flags else ""
            # Show only interesting fields
            display = {k: v for k, v in r.items()
                       if k not in ("id",) or True}
            print(f"  id={r['id']}: name={r.get('name','')!r}, "
                  f"status={r.get('status','')!r}, "
                  f"revenue={r.get('revenue','')!r}{flag_str}")
            # Show enriched fields
            enriched = {k: v for k, v in r.items()
                        if k not in SCHEMA_FIELDS and not k.startswith("_")}
            for k, v in enriched.items():
                print(f"    {k}: {v!r}")

        # ── Audit summary ─────────────────────────────────────────────────────
        print(f"\n[6] Audit trail:")
        for a in audit:
            detail = f" ({a.records_before}→{a.records_after})" if a.records_before != a.records_after else ""
            print(f"  step {a.step} [{a.op}]: {a.summary}{detail}")
            for change in a.changes[:3]:  # show first 3 changes per step
                print(change)
            if len(a.changes) > 3:
                print(f"  ... and {len(a.changes)-3} more")

    print(f"\n{'=' * 60}")
    print("""Key insight — three integration levels:

  Level 1 (dangerous):  LLM writes code → validate → run
    Risk: LLM can write anything. "Validate" is always incomplete.

  Level 2 (L46b):       LLM fills schema slots → validate typed output → run
    Risk: schema fields are still open strings. LLM can put anything in "instruction".

  Level 3 (this file):  LLM selects from op vocabulary → validate+repair → run
    Safety: LLM cannot invent op types. It can only configure pre-defined ops.
    Analogy: parameterized SQL vs. string concatenation.

  The boundary:
    LLM territory:  which ops, in what order, with what parameters
    DET territory:  what ops exist, what values are valid, how they execute
    Contract:       typed Op dataclasses — the shared language between layers
""")
