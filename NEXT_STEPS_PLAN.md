# Next Steps

**Status (2026-07-18):** L1 to L93 complete, cross-model validated, repo published publicly with the
README as the front door. Prior plan items (cross-model validation, doc fixes, public README, push to
`main`) are done; the record lives in `.claude/learnings/reflections/` and git history.

## Open items (in priority order)

1. **Operationalize the quality gates.** Wire `tools/no_sim_check.py` and `uv run pytest` into
   pre-commit and CI (GitHub Actions) so the anti-simulation bar is enforced on every push, not run
   by hand. `ship_gate.py` stays manual (it spends money) but should be a documented release step.

2. **Meta-eval: judge reliability at the ambiguous boundary.** L52 showed judges are reliable on
   clear-cut cases; the ambiguous middle is its known weak spot. Build a graded-ambiguity dataset and
   measure where judge agreement collapses.

3. **Memory safety and privacy evals.** L89 covered tool-result injection only. Extend to memory
   poisoning (adversarial writes that corrupt later recall), PII handling in extracted LTM records,
   and tenant isolation across memory stores.

## On demand

- Cloud ADOT online-eval (extends L34/F2 to continuous production sampling).
- Package the eval harness for external use.
