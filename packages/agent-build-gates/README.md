# agent-build-gates

Quality gates for agent-built code. Three of them, all pure standard library, plus an optional fourth.

When an agent writes code at volume, the failure that costs most is not a bug. It is work that
looks complete and never touched the service it claims to demonstrate: a class that stands in for
a queue, a validator that returns `ALLOW` because the API was unreachable, a fallback chain whose
models never got called. Asking for honesty does not catch that. A script that fails the build does.

```bash
pip install agent-build-gates
```

## The gates

### `no-sim-check`

Flags substituted integrations: code that fabricates a success for a call it could have made.

```bash
no-sim-check $(git ls-files '*.py')
```

It looks for substitute-object vocabulary (`mock`, `stub`, `fake`, `dummy`, `hardcoded`), returns
that fabricate a result, "in production this would" deferrals, and a bare `return True` straight
out of an `except`. Two scoping rules keep the signal usable, both learned from classifying every
hit in a 275-file repo:

- **Identifier-aware boundaries.** A plain `\b` stops at underscores and CamelCase humps, so
  `class MockSQSQueue`, `mock_client` and `_simulate_human_response` are invisible to it while
  their docstrings trip it. This uses boundaries that break on both.
- **Prose is exempt.** The two vocabulary rules never fire on comments or docstrings, because a
  comment cannot fake an integration. Only code can. The deferral rule still reads comments, since
  a deferral comment is the marker for a call that was never made.

Escape a justified line with a trailing `# nosim:ok <reason>`.

The question the tool cannot answer for you, and the one that separates a real hit from noise:
**was a real call available and skipped?** A helper that genuinely raises to drive a recovery path
is fault injection and legitimate. Code that fabricates a success is not.

### `check-no-aws-ids`

Blocks AWS account identifiers from entering tracked `.md` and `.py` files: 12-digit account ids,
SSO admin profile strings, `sso_account` references, and ARNs carrying an account field. <!-- noaws:ok describing the patterns -->

```bash
check-no-aws-ids $(git ls-files '*.md' '*.py')   # explicit files
check-no-aws-ids                                  # every tracked .md/.py in the current repo
```

Paths resolve against your working directory, so it behaves the same installed from a wheel or
vendored into a repo. Extend the known-safe literals at the call site rather than editing the
module: `scan(files, allow=ALLOW | {"123456789012"})`. <!-- noaws:ok doc example -->

Escape a single line with `noaws:ok`, matched anywhere on it, so it works as `# noaws:ok reason`
in Python and `<!-- noaws:ok reason -->` in Markdown. Anything that must legitimately contain
account-shaped strings needs this: this gate's own tests, and documentation like the paragraph
above. The marker covers only its own line, never the rest of the file.

### `eval_harness`

Multi-run evaluation with confidence intervals and significance testing, so a single lucky run
cannot be reported as a result.

```python
from agent_build_gates import Case, run_suite, gate, wilson

cases = [Case("input text", expected="positive")]
correct = lambda out, case: 1.0 if case.expected in out.lower() else 0.0

result = run_suite(cases, my_run_fn, {"correct": correct}, n=5)
passed, reasons = gate(result, baseline=previous, min_quality=0.8, metric="correct")
```

`run_fn(input) -> (output, tokens)` is yours, so the harness never assumes a framework. `gate`
combines a quality floor, a cost ceiling and a permutation test against a frozen baseline, and
returns every reason it failed rather than the first. `wilson` gives the interval on the rate.

## `ship-gate`, behind an extra

`ship_gate` composes the harness into one auditable GO or NO-GO verdict over real agent runs, and
writes the verdict plus the underlying runs to JSON so the decision can be re-examined. It drives
a framework and it spends money, so it is optional:

```bash
pip install 'agent-build-gates[strands]'
```

Importing `agent_build_gates` never pulls that in. Import `agent_build_gates.ship_gate` directly
when you want it; without the extra it raises an ImportError naming the install command.

## Testing your gates

These gates are themselves tested, which is the point. A tripwire with no test proving it fires is
an unverified claim about the thing that verifies everything else. When this package's own
anti-simulation gate was finally given paired positive and negative controls, it turned out to be
wrong in both directions at once: it fired on comments describing deliberate fault injection, and
it missed the substituted classes it existed to catch. Fixing it took one repo from 133 reported
hits to 0 and surfaced nine real substituted integrations that had been invisible.

Measure the precision and recall of your own gates before you trust a green run.

## License

MIT.
