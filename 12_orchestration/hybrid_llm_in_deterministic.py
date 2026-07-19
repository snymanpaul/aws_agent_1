"""
Level 46b: LLM Embedded in Deterministic Code

L46 showed: LLM routes → deterministic pipelines.
L46b shows: deterministic code → LLM calls at specific points.

These are the two directions of the LLM/deterministic boundary.
Understanding both is necessary to architect real production systems.

The fundamental problem:
  LLM outputs are non-deterministic (same prompt → different output each time).
  Production code needs predictable structure, error handling, and testability.
  You cannot just call llm("do the thing") and trust the result.

Three patterns that solve this:

  Pattern 1 — LLM as typed function
    Wrap every LLM call to return a schema-validated dataclass, not a raw string.
    Retry on malformed output. Fall back on persistent failure.
    From the caller's perspective: it's a function that might fail, just like an API.

  Pattern 2 — Confidence-gated routing
    LLM returns a confidence score alongside its answer.
    Deterministic code branches on confidence: process / review / reject.
    LLM uncertainty becomes a first-class signal, not a hidden failure mode.

  Pattern 3 — LLM at decision points only
    Minimize LLM surface area. Use LLM for judgment (classify, assess, validate).
    Use deterministic code for everything else (pre-checks, routing, storage, counting).
    The deterministic scaffolding drives the flow. LLM fills judgment slots.

Key insight:
  Treat LLM calls like external API calls.
  They can fail. They need retries. Their output must be validated.
  The surrounding code must handle all outcomes, including "LLM was wrong".
"""
import json
import re
import sys
import os
from dataclasses import dataclass, field
from typing import Literal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from strands import Agent
from tools import get_model

model = get_model("haiku")


# ── Typed output schemas ────────────────────────────────────────────────────────
# Every LLM call returns one of these, never a raw string.
# If the LLM output can't be parsed into this schema, that's an error to handle.

@dataclass
class Classification:
    category: str   # technical | business | legal | personal | unknown
    confidence: float  # 0.0–1.0
    reason: str

    def is_confident(self, threshold: float = 0.70) -> bool:
        return self.confidence >= threshold


@dataclass
class QualityAssessment:
    score: int           # 1–10
    passes: bool
    issues: list[str] = field(default_factory=list)
    recommendation: str = "process"   # process | review | reject


@dataclass
class PipelineResult:
    doc_id: str
    status: str                        # processed | flagged | rejected
    category: str
    quality_score: int
    notes: list[str] = field(default_factory=list)


# ── Pattern 1: LLM as typed function with retry ────────────────────────────────
# The caller never sees a raw string. It gets a typed dataclass or an exception.
# This is what makes an LLM call behave like a deterministic function call.

CLASSIFY_SCHEMA = """{
  "category": "technical|business|legal|personal|unknown",
  "confidence": 0.0-1.0,
  "reason": "one sentence explaining the classification"
}"""

QUALITY_SCHEMA = """{
  "score": 1-10,
  "passes": true|false,
  "issues": ["issue1", "issue2"],
  "recommendation": "process|review|reject"
}"""


def _call_llm_with_schema(prompt: str, max_retries: int = 3) -> dict:
    """
    Call LLM and extract a JSON object from the response.
    Retries with stricter prompt on parse failure.
    Raises ValueError if all retries fail.
    """
    agent = Agent(model=model, callback_handler=None)
    last_error = None

    for attempt in range(max_retries):
        if attempt > 0:
            prompt = (
                f"Attempt {attempt + 1}. Previous response was invalid: {last_error}.\n"
                f"You MUST return ONLY a JSON object. No explanation. No markdown.\n\n"
                + prompt
            )

        raw = str(agent(prompt))

        try:
            # LLMs sometimes wrap JSON in ```json ... ```
            m = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
            if not m:
                raise ValueError(f"no JSON object in response: {raw[:120]!r}")
            return json.loads(m.group(0))
        except (json.JSONDecodeError, ValueError) as e:
            last_error = str(e)
            print(f"    [retry {attempt+1}/{max_retries}] {e}")

    raise ValueError(f"LLM returned unparseable output after {max_retries} attempts: {last_error}")


def classify_document(text: str) -> Classification:
    """
    LLM call wrapped as a typed function.
    Returns Classification — never a raw string.
    """
    prompt = (
        f"Classify this document. Return ONLY a JSON object matching this schema:\n"
        f"{CLASSIFY_SCHEMA}\n\n"
        f"Document:\n{text[:600]}"
    )
    try:
        d = _call_llm_with_schema(prompt)
        confidence = max(0.0, min(1.0, float(d.get("confidence", 0.5))))
        category = d.get("category", "unknown")
        if category not in ("technical", "business", "legal", "personal", "unknown"):
            category = "unknown"
        return Classification(category=category, confidence=confidence,
                              reason=d.get("reason", ""))
    except ValueError:
        return Classification(category="unknown", confidence=0.0,
                              reason="classification failed — fallback")


def assess_quality(text: str) -> QualityAssessment:
    """
    LLM quality gate wrapped as typed function.
    Score 1–10: 8–10 = process, 5–7 = review, 1–4 = reject.
    """
    prompt = (
        f"Assess document quality. Return ONLY a JSON object matching this schema:\n"
        f"{QUALITY_SCHEMA}\n\n"
        f"Rules: passes=true if score>=6. recommendation: process(8-10), "
        f"review(5-7), reject(1-4). issues=[] if none.\n\n"
        f"Document:\n{text[:500]}"
    )
    try:
        d = _call_llm_with_schema(prompt)
        score = max(1, min(10, int(d.get("score", 5))))
        rec = d.get("recommendation", "review")
        if rec not in ("process", "review", "reject"):
            rec = "review"
        return QualityAssessment(
            score=score,
            passes=bool(d.get("passes", score >= 6)),
            issues=list(d.get("issues", [])),
            recommendation=rec,
        )
    except ValueError:
        return QualityAssessment(score=5, passes=False,
                                 issues=["quality check failed — fallback"], recommendation="review")


# ── Pattern 2 + 3: Deterministic pipeline with LLM at decision points ──────────
# The pipeline drives the flow. LLM fills two slots: classify and quality_gate.
# Every branch is determined by deterministic code acting on typed LLM output.

CONFIDENCE_FLOOR = 0.60   # below this → flag for human review, skip quality check
MIN_LENGTH       = 50     # deterministic pre-check, no LLM needed


def process_document(doc_id: str, text: str) -> PipelineResult:
    """
    Deterministic pipeline: LLM calls are at exactly two points.

    Flow:
      [1] Deterministic: length pre-check
      [2] LLM: classify (typed, retried, fallback)
      [3] Deterministic: confidence gate → flag/continue
      [4] LLM: quality assessment (typed, retried, fallback)
      [5] Deterministic: recommendation gate → process/flag/reject
    """
    notes: list[str] = []

    # ── [1] Deterministic pre-check ────────────────────────────────────────────
    if len(text.strip()) < MIN_LENGTH:
        return PipelineResult(doc_id, "rejected", "unknown", 0,
                              [f"pre-check failed: text too short ({len(text.strip())} chars)"])
    if len(text) > 10_000:
        text = text[:10_000]
        notes.append("text truncated to 10k chars")

    # ── [2] LLM classification ─────────────────────────────────────────────────
    print(f"  [2] classifying {doc_id!r}...")
    clf = classify_document(text)
    notes.append(f"category={clf.category}, confidence={clf.confidence:.2f}")

    # ── [3] Confidence gate (deterministic logic on LLM output) ───────────────
    # Pattern 2: LLM uncertainty → deterministic routing decision
    if not clf.is_confident(CONFIDENCE_FLOOR):
        return PipelineResult(doc_id, "flagged", clf.category, 0,
                              notes + [f"low confidence ({clf.confidence:.2f} < {CONFIDENCE_FLOOR})"])

    # ── [4] LLM quality assessment ─────────────────────────────────────────────
    print(f"  [4] assessing quality of {doc_id!r}...")
    qa = assess_quality(text)
    if qa.issues:
        notes.append(f"quality score={qa.score}/10, issues: {'; '.join(qa.issues)}")
    else:
        notes.append(f"quality score={qa.score}/10, no issues")

    # ── [5] Recommendation gate (deterministic logic on LLM output) ───────────
    # Pattern 3: LLM decision → deterministic routing
    if qa.recommendation == "reject":
        return PipelineResult(doc_id, "rejected", clf.category, qa.score,
                              notes + ["rejected by quality gate"])
    if qa.recommendation == "review":
        return PipelineResult(doc_id, "flagged", clf.category, qa.score,
                              notes + ["flagged by quality gate for review"])

    return PipelineResult(doc_id, "processed", clf.category, qa.score, notes)


# ── Test documents — chosen to exercise all pipeline paths ─────────────────────

DOCUMENTS = [
    (
        "doc-001",
        """Vector databases store high-dimensional embeddings for semantic search.
        HNSW (Hierarchical Navigable Small World) graphs enable approximate nearest
        neighbour search at sub-millisecond latency. Key parameters: M (graph connectivity),
        ef_construction (index-time search depth), ef (query-time search depth).
        Recall vs latency tradeoff is controlled by ef. Production deployments
        typically target 95%+ recall at p99 < 10ms.""",
    ),
    (
        "doc-002",
        # Very short — fails pre-check before any LLM call
        "Meeting tomorrow at 3pm.",
    ),
    (
        "doc-003",
        """Q4 revenue projections indicate 23% YoY growth driven by enterprise
        contract renewals. APAC expansion contributed $4.2M incremental ARR.
        Churn rate improved from 8.3% to 6.1% following the onboarding redesign.
        Sales cycle compressed by 12 days on average. Pipeline coverage ratio
        stands at 3.1x for Q1. Board presentation scheduled for the 15th.""",
    ),
    (
        "doc-004",
        # Deliberately minimal — likely hits quality gate
        "Notes from call: discussed things. Will follow up later. Action items TBD.",
    ),
    (
        "doc-005",
        """Force majeure clause 12.4(b) exempts performance obligations arising
        from circumstances beyond reasonable control including acts of God, war,
        pandemic, regulatory changes, and infrastructure failures. Liability cap
        under section 18 is limited to fees paid in the prior 12-month period.
        Governing law: Delaware. Dispute resolution: binding arbitration AAA rules.""",
    ),
]


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("L46b: LLM Embedded in Deterministic Code")
    print("3 patterns: typed output | confidence gate | quality gate")
    print("=" * 60)

    results: list[PipelineResult] = []

    for doc_id, text in DOCUMENTS:
        print(f"\n{'─' * 60}")
        print(f"[{doc_id}] {text[:60].strip()!r}...")
        result = process_document(doc_id, text)
        results.append(result)
        status_icon = {"processed": "✓", "flagged": "?", "rejected": "✗"}.get(result.status, "?")
        print(f"  {status_icon} status={result.status}, category={result.category}, "
              f"quality={result.quality_score}/10")
        for note in result.notes:
            print(f"    • {note}")

    # Deterministic aggregation over LLM-processed results
    print(f"\n{'=' * 60}")
    print(f"Batch summary:")
    processed = [r for r in results if r.status == "processed"]
    flagged   = [r for r in results if r.status == "flagged"]
    rejected  = [r for r in results if r.status == "rejected"]
    print(f"  processed : {len(processed)} — {[r.doc_id for r in processed]}")
    print(f"  flagged   : {len(flagged)}  — {[r.doc_id for r in flagged]}")
    print(f"  rejected  : {len(rejected)} — {[r.doc_id for r in rejected]}")
    if processed:
        avg_quality = sum(r.quality_score for r in processed) / len(processed)
        print(f"  avg quality (processed docs): {avg_quality:.1f}/10")

    print(f"""
{'=' * 60}
Key patterns:

  Pattern 1 — LLM as typed function
    classify_document() and assess_quality() return dataclasses.
    Caller never sees a raw string. Every field is validated.
    _call_llm_with_schema() retries with stricter prompt on parse failure.
    Fallback dataclass returned when all retries fail.

  Pattern 2 — Confidence-gated routing
    Classification returns confidence (0.0-1.0).
    Deterministic code: if confidence < {CONFIDENCE_FLOOR} → flag, skip quality.
    LLM uncertainty is a first-class signal, not a silent failure.

  Pattern 3 — LLM at decision points only
    Pre-check (length) happens before any LLM call — cheap, deterministic.
    LLM called exactly twice per document (classify + quality).
    All routing logic is in deterministic code acting on typed LLM output.
    Outer batch loop, aggregation, counting — all deterministic.

  The rule: deterministic code drives the flow.
             LLM fills judgment slots.
             Typed output is the contract between them.
""")
