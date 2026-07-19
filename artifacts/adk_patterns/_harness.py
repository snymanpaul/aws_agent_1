"""Audit harness: multi-run reproducibility + token-cost accounting.

This repo's own rule (observations.jsonl:608,640): "LLMs are non-deterministic — never rely on a
single run." So every pattern exposes trial() -> {ok, signal, tokens, note}, and audit() runs it N
times, asserting (a) it passes every run, (b) the `signal` (a reproducibility fingerprint:
execution order, routing, verdict) is identical across runs, and reporting token cost (the gate is paid).
"""


def _usage_total(u) -> int:
    if u is None:
        return 0
    if isinstance(u, dict):
        return int(u.get("totalTokens", 0) or 0)
    return int(getattr(u, "totalTokens", 0) or 0)


def tokens_of(result) -> int:
    """Total tokens for a Graph/Swarm/Agent result (best-effort across result types)."""
    direct = getattr(result, "accumulated_usage", None)
    if direct is not None:
        return _usage_total(direct)
    metrics = getattr(result, "metrics", None)            # AgentResult.metrics.accumulated_usage
    if metrics is not None:
        return _usage_total(getattr(metrics, "accumulated_usage", None))
    return 0


def _slug(label: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in label.split("—")[0]).strip("_").lower()


def audit(label: str, trial, n: int = 3, trace_dir: str = "traces") -> dict:
    """Run trial() n times; report pass-rate, reproducibility, mean tokens, and write a per-run
    execution trace (JSONL) for audit. trial(rec) instruments its agents with the recorder."""
    from _trace import TraceRecorder

    oks, signals, toks, notes, traces = [], [], [], [], []
    for k in range(n):
        rec = TraceRecorder()
        try:
            r = trial(rec)                                  # trial attaches rec via _trace.instrument(...)
            oks.append(bool(r["ok"]))
            signals.append(r["signal"])
            toks.append(int(r.get("tokens", 0)))
            notes.append(r.get("note", ""))
        except Exception as e:                              # a throwing trial is a failed run
            oks.append(False)
            signals.append(f"EXC:{type(e).__name__}:{str(e)[:80]}")
            toks.append(0)
            notes.append("exception")
        path = rec.dump(f"{trace_dir}/{_slug(label)}_run{k + 1}.jsonl")
        traces.append((path, rec.summary()))
    all_pass = all(oks)
    reproducible = len(set(signals)) == 1
    mean_tok = round(sum(toks) / len(toks)) if toks else 0
    print(f"\n#### {label}")
    print(f"   passed     : {sum(oks)}/{n}")
    print(f"   reproducible: {reproducible}  (unique signals: {len(set(signals))})")
    print(f"   signal      : {signals[0]}")
    if not reproducible:
        for i, s in enumerate(signals):
            print(f"       run{i+1}: {s}")
    print(f"   tokens (mean): {mean_tok}   last: {notes[-1]}")
    print(f"   trace        : {traces[-1][0]}  ({traces[-1][1]})")
    return {"label": label, "all_pass": all_pass, "reproducible": reproducible,
            "mean_tokens": mean_tok, "n": n, "trace_events": traces[-1][1]}
